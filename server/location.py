"""Location configuration, validation, persistence, and environment layering.

Mirrors the state_machine.ConfigStore pattern:
- Thread-safe access via threading.Lock
- Stat caching via (st_mtime_ns, st_size)
- Atomic file saving via .tmp.<pid> rename with fallback to resolve_cache_dir()
- Layered environment variable overrides (TRACKER_*)
"""

import errno
import json
import math
import os
import threading
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any, Optional

CONFIG_VERSION = 1
DEFAULT_LATITUDE = 40.7371
DEFAULT_LONGITUDE = -74.0305
DEFAULT_LOCATION_NAME = "Hoboken City Hall"
DEFAULT_ADDRESS = "Hoboken City Hall"
DEFAULT_CITY = "Hoboken"
DEFAULT_STATE = "NJ"
DEFAULT_ROUTE = "126"
DEFAULT_DESTINATION = "NYC PORT AUTHORITY"
DEFAULT_ENABLE_MICROMOBILITY = True
DEFAULT_MAX_WALK_MINUTES = 15
DEFAULT_CITIBIKE_MAX_STATIONS = 6

MAX_CONFIG_BYTES = 64 * 1024
MAX_NAME_LEN = 100
MAX_ADDRESS_LEN = 200
MAX_CITY_LEN = 100
MAX_STATE_LEN = 50
MAX_ROUTE_LEN = 20
MAX_DESTINATION_LEN = 100
MAX_WALK_MINUTES_LIMIT = 180
MAX_CITIBIKE_STATIONS_LIMIT = 30
MAX_STOPS_OVERRIDE_COUNT = 16

_TRUTHY = ("1", "true", "yes", "on")
_FALSY = ("0", "false", "no", "off")

_ALLOWED_KEYS = (
    "version",
    "latitude",
    "longitude",
    "location_name",
    "name",
    "address",
    "city",
    "state",
    "route",
    "destination",
    "enable_micromobility",
    "citibike_enabled",
    "max_walk_minutes",
    "citibike_max_stations",
    "stops_override",
)


class LocationConfigError(ValueError):
    """Raised when a location configuration is invalid."""


class LocationStorageError(LocationConfigError):
    """Raised when persisting location configuration to disk fails."""


def _is_read_only_error(err: OSError) -> bool:
    """Returns True if err indicates target is read-only or permission-denied."""
    if isinstance(err, PermissionError):
        return True
    if err.errno in (errno.EACCES, errno.EPERM, errno.EROFS):
        return True
    msg = str(err).lower()
    return "read-only" in msg or "permission denied" in msg


@dataclass(frozen=True)
class LocationConfig:
    """Validated location configuration for transit auto-discovery and dashboard rendering."""

    latitude: float = DEFAULT_LATITUDE
    longitude: float = DEFAULT_LONGITUDE
    location_name: str = DEFAULT_LOCATION_NAME
    address: str = DEFAULT_ADDRESS
    city: str = DEFAULT_CITY
    state: str = DEFAULT_STATE
    route: str = DEFAULT_ROUTE
    destination: str = DEFAULT_DESTINATION
    enable_micromobility: bool = DEFAULT_ENABLE_MICROMOBILITY
    max_walk_minutes: int = DEFAULT_MAX_WALK_MINUTES
    citibike_max_stations: int = DEFAULT_CITIBIKE_MAX_STATIONS
    stops_override: Optional[tuple[dict[str, Any], ...]] = None
    version: int = CONFIG_VERSION

    @property
    def name(self) -> str:
        """Alias for location_name."""
        return self.location_name

    @property
    def citibike_enabled(self) -> bool:
        """Alias for enable_micromobility."""
        return self.enable_micromobility

    def to_dict(self) -> dict[str, Any]:
        """JSON-serialisable view of the location configuration."""
        stops = (
            [dict(s) for s in self.stops_override]
            if self.stops_override is not None
            else None
        )
        return {
            "version": self.version,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "location_name": self.location_name,
            "name": self.location_name,
            "address": self.address,
            "city": self.city,
            "state": self.state,
            "route": self.route,
            "destination": self.destination,
            "enable_micromobility": self.enable_micromobility,
            "citibike_enabled": self.enable_micromobility,
            "max_walk_minutes": self.max_walk_minutes,
            "citibike_max_stations": self.citibike_max_stations,
            "stops_override": stops,
        }

    @classmethod
    def from_dict(
        cls, data: Any, base: Optional["LocationConfig"] = None
    ) -> "LocationConfig":
        """Deserializes and validates a dictionary into a LocationConfig."""
        return parse_location_config(data, base=base)


def default_location_config() -> LocationConfig:
    """Returns the built-in default LocationConfig (Hoboken City Hall, Hoboken, NJ)."""
    return LocationConfig()


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _check_keys(obj: Mapping[str, Any], allowed: tuple[str, ...], where: str) -> None:
    unknown = sorted(set(obj) - set(allowed))
    if unknown:
        raise LocationConfigError(f"{where}: unknown key(s) {', '.join(unknown)}")


def _as_dict(value: Any, where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise LocationConfigError(f"{where}: expected an object")
    return value


def _as_str(value: Any, max_len: int, where: str) -> str:
    if not isinstance(value, str):
        raise LocationConfigError(f"{where}: expected a string")
    stripped = value.strip()
    if not stripped:
        raise LocationConfigError(f"{where}: must not be empty")
    if len(stripped) > max_len:
        raise LocationConfigError(f"{where}: must be at most {max_len} characters")
    if any(ord(c) < 32 for c in stripped):
        raise LocationConfigError(f"{where}: contains unprintable characters")
    return stripped


def _as_float(value: Any, lo: float, hi: float, where: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise LocationConfigError(f"{where}: expected a number")
    val = float(value)
    if math.isnan(val) or math.isinf(val):
        raise LocationConfigError(f"{where}: must be a finite number")
    if not (lo <= val <= hi):
        raise LocationConfigError(f"{where} must be between {lo} and {hi}")
    return val


def _as_int(value: Any, lo: int, hi: int, where: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise LocationConfigError(f"{where}: expected an integer")
    if not (lo <= value <= hi):
        raise LocationConfigError(f"{where} must be between {lo} and {hi}")
    return value


def _as_bool(value: Any, where: str) -> bool:
    if not isinstance(value, bool):
        raise LocationConfigError(f"{where}: expected true or false")
    return value


def _parse_stops_override(
    value: Any, where: str
) -> Optional[tuple[dict[str, Any], ...]]:
    if value is None:
        return None
    if not isinstance(value, list):
        raise LocationConfigError(f"{where}: expected a list or null")
    if len(value) > MAX_STOPS_OVERRIDE_COUNT:
        raise LocationConfigError(
            f"{where}: at most {MAX_STOPS_OVERRIDE_COUNT} stops are allowed"
        )
    stops: list[dict[str, Any]] = []
    for i, item in enumerate(value):
        item_where = f"{where}[{i}]"
        if isinstance(item, str):
            clean_id = item.strip()
            if not clean_id:
                raise LocationConfigError(f"{item_where}: stop ID must not be empty")
            stops.append({"id": clean_id})
        elif isinstance(item, dict):
            if "id" not in item:
                raise LocationConfigError(f"{item_where}: missing required 'id' key")
            stop_id = str(item["id"]).strip()
            if not stop_id:
                raise LocationConfigError(f"{item_where}.id: must not be empty")
            stop_dict: dict[str, Any] = {"id": stop_id}
            if "name" in item:
                stop_dict["name"] = _as_str(
                    item["name"], MAX_NAME_LEN, f"{item_where}.name"
                )
            if "walk_min" in item:
                stop_dict["walk_min"] = _as_int(
                    item["walk_min"],
                    1,
                    MAX_WALK_MINUTES_LIMIT,
                    f"{item_where}.walk_min",
                )
            if "distance_m" in item:
                stop_dict["distance_m"] = _as_int(
                    item["distance_m"], 0, 50000, f"{item_where}.distance_m"
                )
            if "subtitle" in item:
                stop_dict["subtitle"] = _as_str(
                    item["subtitle"], MAX_NAME_LEN, f"{item_where}.subtitle"
                )
            if "direction" in item:
                stop_dict["direction"] = _as_str(
                    item["direction"], MAX_NAME_LEN, f"{item_where}.direction"
                )
            stops.append(stop_dict)
        else:
            raise LocationConfigError(
                f"{item_where}: expected stop ID string or object"
            )
    return tuple(stops)


def parse_location_config(
    data: Any, base: Optional[LocationConfig] = None
) -> LocationConfig:
    """Validates a decoded location configuration document and merges it onto base."""
    base = base or default_location_config()
    obj = _as_dict(data, "config")
    _check_keys(obj, _ALLOWED_KEYS, "config")

    version = obj.get("version", CONFIG_VERSION)
    if version != CONFIG_VERSION or isinstance(version, bool):
        raise LocationConfigError(
            f"config.version: only version {CONFIG_VERSION} is supported"
        )

    latitude = (
        _as_float(obj["latitude"], -90.0, 90.0, "latitude")
        if "latitude" in obj
        else base.latitude
    )
    longitude = (
        _as_float(obj["longitude"], -180.0, 180.0, "longitude")
        if "longitude" in obj
        else base.longitude
    )

    # Name and aliases
    if "location_name" in obj:
        loc_name = _as_str(obj["location_name"], MAX_NAME_LEN, "location_name")
    elif "name" in obj:
        loc_name = _as_str(obj["name"], MAX_NAME_LEN, "name")
    else:
        loc_name = base.location_name

    address = (
        _as_str(obj["address"], MAX_ADDRESS_LEN, "address")
        if "address" in obj
        else base.address
    )
    city = _as_str(obj["city"], MAX_CITY_LEN, "city") if "city" in obj else base.city
    state = (
        _as_str(obj["state"], MAX_STATE_LEN, "state") if "state" in obj else base.state
    )
    route = (
        _as_str(obj["route"], MAX_ROUTE_LEN, "route") if "route" in obj else base.route
    )
    destination = (
        _as_str(obj["destination"], MAX_DESTINATION_LEN, "destination")
        if "destination" in obj
        else base.destination
    )

    # Micromobility toggle and aliases
    if "enable_micromobility" in obj:
        enable_micro = _as_bool(obj["enable_micromobility"], "enable_micromobility")
    elif "citibike_enabled" in obj:
        enable_micro = _as_bool(obj["citibike_enabled"], "citibike_enabled")
    else:
        enable_micro = base.enable_micromobility

    max_walk = (
        _as_int(obj["max_walk_minutes"], 1, MAX_WALK_MINUTES_LIMIT, "max_walk_minutes")
        if "max_walk_minutes" in obj
        else base.max_walk_minutes
    )
    citibike_max = (
        _as_int(
            obj["citibike_max_stations"],
            0,
            MAX_CITIBIKE_STATIONS_LIMIT,
            "citibike_max_stations",
        )
        if "citibike_max_stations" in obj
        else base.citibike_max_stations
    )

    stops_override = (
        _parse_stops_override(obj["stops_override"], "stops_override")
        if "stops_override" in obj
        else base.stops_override
    )

    return replace(
        base,
        latitude=latitude,
        longitude=longitude,
        location_name=loc_name,
        address=address,
        city=city,
        state=state,
        route=route,
        destination=destination,
        enable_micromobility=enable_micro,
        max_walk_minutes=max_walk,
        citibike_max_stations=citibike_max,
        stops_override=stops_override,
        version=CONFIG_VERSION,
    )


# ---------------------------------------------------------------------------
# Environment Variable Layering
# ---------------------------------------------------------------------------


def _env(env: Mapping[str, str], name: str) -> str:
    return str(env.get(name, "") or "").strip()


def apply_env_overrides(
    cfg: LocationConfig, env: Mapping[str, str]
) -> tuple[LocationConfig, list[str]]:
    """Applies TRACKER_* environment variables on top of cfg."""
    warnings: list[str] = []
    updates: dict[str, Any] = {}

    lat_str = _env(env, "TRACKER_LATITUDE")
    if lat_str:
        try:
            val = float(lat_str)
            if math.isnan(val) or math.isinf(val) or not (-90.0 <= val <= 90.0):
                warnings.append(
                    f"TRACKER_LATITUDE {lat_str!r} outside -90..90; ignored"
                )
            else:
                updates["latitude"] = val
        except ValueError:
            warnings.append(f"TRACKER_LATITUDE {lat_str!r} not a valid float; ignored")

    lon_str = _env(env, "TRACKER_LONGITUDE")
    if lon_str:
        try:
            val = float(lon_str)
            if math.isnan(val) or math.isinf(val) or not (-180.0 <= val <= 180.0):
                warnings.append(
                    f"TRACKER_LONGITUDE {lon_str!r} outside -180..180; ignored"
                )
            else:
                updates["longitude"] = val
        except ValueError:
            warnings.append(f"TRACKER_LONGITUDE {lon_str!r} not a valid float; ignored")

    name_str = _env(env, "TRACKER_LOCATION_NAME")
    if name_str:
        updates["location_name"] = name_str[:MAX_NAME_LEN]

    addr_str = _env(env, "TRACKER_ADDRESS")
    if addr_str:
        updates["address"] = addr_str[:MAX_ADDRESS_LEN]

    city_str = _env(env, "TRACKER_CITY")
    if city_str:
        updates["city"] = city_str[:MAX_CITY_LEN]

    state_str = _env(env, "TRACKER_STATE")
    if state_str:
        updates["state"] = state_str[:MAX_STATE_LEN]

    route_str = _env(env, "TRACKER_ROUTE")
    if route_str:
        updates["route"] = route_str[:MAX_ROUTE_LEN]

    dest_str = _env(env, "TRACKER_DESTINATION")
    if dest_str:
        updates["destination"] = dest_str[:MAX_DESTINATION_LEN]

    micro_str = _env(env, "TRACKER_ENABLE_MICROMOBILITY").lower()
    if micro_str:
        if micro_str in _TRUTHY:
            updates["enable_micromobility"] = True
        elif micro_str in _FALSY:
            updates["enable_micromobility"] = False
        else:
            warnings.append(
                f"TRACKER_ENABLE_MICROMOBILITY {micro_str!r} not boolean; ignored"
            )

    walk_str = _env(env, "TRACKER_MAX_WALK_MINUTES")
    if walk_str:
        try:
            walk_val = int(walk_str)
            if 1 <= walk_val <= MAX_WALK_MINUTES_LIMIT:
                updates["max_walk_minutes"] = walk_val
            else:
                warnings.append(
                    f"TRACKER_MAX_WALK_MINUTES {walk_str!r} outside 1..{MAX_WALK_MINUTES_LIMIT}; ignored"
                )
        except ValueError:
            warnings.append(
                f"TRACKER_MAX_WALK_MINUTES {walk_str!r} not integer; ignored"
            )

    stations_str = _env(env, "TRACKER_CITIBIKE_MAX_STATIONS")
    if stations_str:
        try:
            st_val = int(stations_str)
            if 0 <= st_val <= MAX_CITIBIKE_STATIONS_LIMIT:
                updates["citibike_max_stations"] = st_val
            else:
                warnings.append(
                    f"TRACKER_CITIBIKE_MAX_STATIONS {stations_str!r} outside 0..{MAX_CITIBIKE_STATIONS_LIMIT}; ignored"
                )
        except ValueError:
            warnings.append(
                f"TRACKER_CITIBIKE_MAX_STATIONS {stations_str!r} not integer; ignored"
            )

    if updates:
        cfg = replace(cfg, **updates)
    return cfg, warnings


# ---------------------------------------------------------------------------
# Loading & Store Implementation
# ---------------------------------------------------------------------------


def load_location_config(
    path: Optional[str], env: Mapping[str, str]
) -> tuple[LocationConfig, list[str]]:
    """Loads path (if exists) and applies env overrides. Returns (config, warnings)."""
    cfg = default_location_config()
    warnings: list[str] = []
    if path and os.path.exists(path):
        try:
            with open(path, "rb") as f:
                raw = f.read(MAX_CONFIG_BYTES + 1)
        except OSError as e:
            raise LocationConfigError(f"cannot read {path}: {e}") from e
        if len(raw) > MAX_CONFIG_BYTES:
            raise LocationConfigError(f"{path} is larger than {MAX_CONFIG_BYTES} bytes")
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as e:
            raise LocationConfigError(f"{path} is not valid JSON: {e}") from e
        cfg = parse_location_config(data, cfg)

    cfg, env_warnings = apply_env_overrides(cfg, env)
    warnings.extend(env_warnings)
    return cfg, warnings


class LocationConfigStore:
    """Thread-safe holder for active location config. Re-reads on file stat change."""

    def __init__(
        self,
        path: Optional[str] = None,
        env: Optional[Mapping[str, str]] = None,
        log: Any = print,
    ) -> None:
        self.env: Mapping[str, str] = dict(os.environ if env is None else env)
        if path is None:
            path = _env(self.env, "LOCATION_CONFIG")
            if not path:
                try:
                    from paths import resolve_location_config_path

                    path = resolve_location_config_path()
                except ImportError:
                    path = "/app/config/location.json"
        self.primary_path = path
        self.path = path
        self._log = log
        self._lock = threading.RLock()
        self._stamp: Any = object()  # Sentinel forcing first load
        self._config, _ = apply_env_overrides(default_location_config(), self.env)
        self.source = "built-in defaults"
        self.error = ""
        self.get()

    def _file_stamp(self) -> Optional[tuple[int, int]]:
        try:
            st = os.stat(self.path)
        except OSError:
            return None
        return (st.st_mtime_ns, st.st_size)

    def get(self) -> LocationConfig:
        stamp = self._file_stamp()
        with self._lock:
            if stamp == self._stamp:
                return self._config
            self._stamp = stamp
            if stamp is None:
                self._config, _ = apply_env_overrides(
                    default_location_config(), self.env
                )
                self.source = "built-in defaults"
                self.error = ""
                return self._config
            try:
                cfg, warnings = load_location_config(self.path, self.env)
            except LocationConfigError as e:
                self.error = str(e)
                self._log(
                    f"[Location] rejected {self.path}: {e}; keeping {self.source}."
                )
                return self._config
            self._config = cfg
            self.error = ""
            self.source = self.path
            for w in warnings:
                self._log(f"[Location] warning: {w}")
            self._log(f"[Location] loaded location configuration from {self.source}.")
            return self._config

    def save_config(
        self, data: dict[str, Any], target_path: Optional[str] = None
    ) -> tuple[LocationConfig, list[str]]:
        new_cfg = parse_location_config(data)
        dict_data = new_cfg.to_dict()
        raw = json.dumps(dict_data, indent=2).encode("utf-8") + b"\n"

        with self._lock:
            target = target_path or self.path
            written_path = target

            def _atomic_write(dest: str) -> None:
                parent = os.path.dirname(os.path.abspath(dest))
                os.makedirs(parent, exist_ok=True)
                tmp = (
                    dest
                    + f".tmp.{os.getpid()}.{threading.get_ident()}.{uuid.uuid4().hex[:8]}"
                )
                try:
                    with open(tmp, "wb") as f:
                        f.write(raw)
                        f.flush()
                        try:
                            os.fsync(f.fileno())
                        except OSError:
                            pass
                    os.replace(tmp, dest)
                finally:
                    if os.path.exists(tmp):
                        try:
                            os.remove(tmp)
                        except OSError:
                            pass

            try:
                _atomic_write(target)
            except OSError as err:
                if not _is_read_only_error(err):
                    raise LocationStorageError(
                        f"failed to write location to {target}: {err}"
                    ) from err
                try:
                    from paths import resolve_cache_dir

                    cache_dir = resolve_cache_dir()
                except ImportError:
                    cache_dir = os.environ.get("CACHE_DIR", "/app/cache")
                fallback = os.path.join(cache_dir, "location.json")
                if os.path.abspath(fallback) == os.path.abspath(target):
                    raise LocationStorageError(
                        f"failed to write location to {target}: {err}"
                    ) from err
                try:
                    _atomic_write(fallback)
                    written_path = fallback
                    self._log(
                        f"[Location] target {target} not writable ({err}); saved to {fallback}"
                    )
                except OSError as fallback_err:
                    raise LocationStorageError(
                        f"failed to write location to {target} ({err}) and fallback {fallback} ({fallback_err})"
                    ) from fallback_err

            self.path = written_path
            self.source = written_path
            self.error = ""
            self._stamp = self._file_stamp()
            cfg, warnings = apply_env_overrides(new_cfg, self.env)
            self._config = cfg
            for w in warnings:
                self._log(f"[Location] warning: {w}")
            self._log(
                f"[Location] saved and applied location configuration to {self.source}."
            )
            return self._config, warnings

    def reset_to_default(self) -> tuple[LocationConfig, list[str]]:
        return self.save_config(default_location_config().to_dict())

    def reset(self) -> None:
        """Resets in-memory state and reloads configuration."""
        with self._lock:
            if hasattr(self, "primary_path") and self.primary_path:
                self.path = self.primary_path
            self._stamp = object()
            self._config, _ = apply_env_overrides(default_location_config(), self.env)
            self.source = "built-in defaults"
            self.error = ""
        self.get()


# Module-level singleton
LOCATION_STORE = LocationConfigStore()


def get_location_config() -> LocationConfig:
    """Returns active LocationConfig from global LOCATION_STORE."""
    return LOCATION_STORE.get()


def save_location_config(
    data: dict[str, Any], target_path: Optional[str] = None
) -> LocationConfig:
    """Saves and applies location configuration in global LOCATION_STORE."""
    cfg, _ = LOCATION_STORE.save_config(data, target_path=target_path)
    return cfg


def reset_location_config() -> LocationConfig:
    """Resets global LOCATION_STORE to default Hoboken configuration."""
    cfg, _ = LOCATION_STORE.reset_to_default()
    return cfg
