"""Citi Bike GBFS station auto-discovery, 24-hour caching, pedestrian geometry, and name cleaning."""

from __future__ import annotations

import html
import json
import math
import os
import re
import threading
import time
import urllib.error
import urllib.request
import uuid
from typing import Any

from citibike import DEFAULT_STATIONS, StationConfig
from paths import resolve_cache_dir, resolve_data_dir
from version import VERSION

# Mean Earth radius in meters
EARTH_RADIUS_M = 6371000.0

# Pedestrian circuity multiplier accounting for urban street grid detour
CIRCUITY_MULTIPLIER = 1.25

# Standard urban pedestrian walking speed (meters per minute, 4.8 km/h ~ 3.0 mph)
WALK_SPEED_M_PER_MIN = 80.0

# Regional bounding box for NYC/NJ Citi Bike coverage area
METRO_LAT_MIN = 40.50
METRO_LAT_MAX = 41.05
METRO_LON_MIN = -74.20
METRO_LON_MAX = -73.65

# Upstream GBFS endpoint and cache defaults
GBFS_STATION_INFO_URL = "https://gbfs.citibikenyc.com/gbfs/en/station_information.json"
CACHE_FILENAME = "citibike_stations.json"
SEED_FILENAME = "citibike_stations_seed.json"
DEFAULT_TTL_SECONDS = 86400  # 24 hours
DEFAULT_HTTP_TIMEOUT = 5.0


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Computes great-circle distance in meters between two lat/lon coordinates."""
    if lat1 == lat2 and lon1 == lon2:
        return 0.0

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = (
        math.sin(dphi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))
    return EARTH_RADIUS_M * c


def pedestrian_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> int:
    """Computes pedestrian walking distance in meters with 1.25 circuity multiplier."""
    straight_m = haversine_distance(lat1, lon1, lat2, lon2)
    return int(round(straight_m * CIRCUITY_MULTIPLIER))


def calculate_walk_minutes(distance_m: int) -> int:
    """Computes walking minutes at 80 m/min speed, minimum 1 minute if distance > 0."""
    if distance_m <= 0:
        return 0
    return max(1, int(round(distance_m / WALK_SPEED_M_PER_MIN)))


def _ordinal(num: int) -> str:
    """Converts integer street number to English ordinal string (e.g. 9 -> 9th, 1 -> 1st)."""
    if 11 <= (num % 100) <= 13:
        return f"{num}th"
    rem = num % 10
    if rem == 1:
        return f"{num}st"
    if rem == 2:
        return f"{num}nd"
    if rem == 3:
        return f"{num}rd"
    return f"{num}th"


def _clean_leg(leg: str) -> tuple[str, bool]:
    """Cleans an intersection leg and indicates whether it is a numbered street."""
    s = leg.strip()
    if not s:
        return "", False

    m = re.match(
        r"^(W|E|N|S)?\s*(\d+)(?:st|nd|rd|th)?\s*(?:St|Street|Ave|Avenue|Pl|Place|Ct|Court|Rd|Road|Blvd|Dr|Drive|Way|Ter|Terrace)?$",
        s,
        re.IGNORECASE,
    )
    if m:
        prefix = m.group(1)
        num = int(m.group(2))
        ord_s = _ordinal(num)
        if prefix:
            return f"{prefix.upper()} {ord_s}", True
        return ord_s, True

    cleaned = re.sub(
        r"\s+(?:St|Street|Ave|Avenue)$", "", s, flags=re.IGNORECASE
    ).strip()
    return cleaned, False


def clean_station_name(full_name: str) -> str:
    """Formats verbose GBFS station name into a concise, readable intersection name."""
    if not full_name:
        return ""

    raw = html.unescape(full_name).strip()

    # Step 1: Strip landmark prefix if ' - ' is present
    if " - " in raw:
        parts = raw.split(" - ", 1)
        prefix_lower = parts[0].lower()
        # Preserve major transit hub names (e.g. "Hoboken Terminal")
        if "terminal" in prefix_lower or "path" in prefix_lower:
            raw = parts[0].strip()
        elif "&" in parts[1]:
            raw = parts[1].strip()
        elif "&" not in parts[0]:
            raw = parts[1].strip()
        else:
            raw = parts[0].strip()

    # Step 2: Non-intersection names (e.g. 'Grove St PATH', 'Journal Square')
    if "&" not in raw:
        return re.sub(
            r"\s+(?:St|Street|Ave|Avenue)$", "", raw, flags=re.IGNORECASE
        ).strip()

    # Step 3: Split intersection into legs
    sides = [p.strip() for p in raw.split("&", 1)]
    leg0, is_num0 = _clean_leg(sides[0])
    leg1, is_num1 = _clean_leg(sides[1])

    if not leg0:
        return leg1
    if not leg1:
        return leg0

    # Step 4: Canonical ordering: avenue/named street before numbered cross street
    if is_num0 and not is_num1:
        return f"{leg1} & {leg0}"
    return f"{leg0} & {leg1}"


def is_in_metro_area(lat: float, lon: float) -> bool:
    """Fast check whether coordinates fall within NYC/NJ Citi Bike operating region."""
    return (
        METRO_LAT_MIN <= lat <= METRO_LAT_MAX and METRO_LON_MIN <= lon <= METRO_LON_MAX
    )


def compute_bounding_box_deltas(
    user_lat: float, max_walk_minutes: int
) -> tuple[float, float]:
    """Calculates conservative (delta_lat, delta_lon) bounding box for candidate pre-filtering."""
    max_ped_m = (max_walk_minutes + 0.5) * WALK_SPEED_M_PER_MIN
    margin_m = (max_ped_m / CIRCUITY_MULTIPLIER) * 1.20

    delta_lat = margin_m / 111139.0
    cos_lat = max(0.1, math.cos(math.radians(user_lat)))
    delta_lon = margin_m / (111139.0 * cos_lat)
    return delta_lat, delta_lon


def select_closest_stations(
    stations_raw: list[dict[str, Any]],
    user_lat: float,
    user_lon: float,
    max_walk_minutes: int = 15,
    max_stations: int = 6,
) -> list[Any]:
    """Filters raw stations by bounding box and walk minutes, sorts by distance, and returns top stations."""
    if not stations_raw or max_stations <= 0 or max_walk_minutes <= 0:
        return []

    if not is_in_metro_area(user_lat, user_lon):
        return []

    delta_lat, delta_lon = compute_bounding_box_deltas(user_lat, max_walk_minutes)

    candidates: list[tuple[int, int, str, StationConfig]] = []

    for s in stations_raw:
        slat = s.get("lat")
        slon = s.get("lon")
        if slat is None or slon is None:
            continue

        try:
            slat_f = float(slat)
            slon_f = float(slon)
        except (ValueError, TypeError):
            continue

        # Coarse bounding box filter
        if abs(slat_f - user_lat) > delta_lat or abs(slon_f - user_lon) > delta_lon:
            continue

        dist_m = pedestrian_distance(user_lat, user_lon, slat_f, slon_f)
        walk_min = calculate_walk_minutes(dist_m)

        if walk_min <= max_walk_minutes:
            station_id = str(s.get("station_id") or "")
            full_name = str(s.get("name") or "")
            cleaned_name = clean_station_name(full_name)

            cfg: StationConfig = {
                "id": station_id,
                "name": cleaned_name,
                "full_name": full_name,
                "walk_min": walk_min,
                "distance_m": dist_m,
            }
            candidates.append((dist_m, walk_min, station_id, cfg))

    if not candidates:
        return []

    # Sort ascending by distance_m, then walk_min, then station_id
    candidates.sort(key=lambda item: (item[0], item[1], item[2]))

    return [item[3] for item in candidates[:max_stations]]


def extract_stations_from_doc(doc: Any) -> list[Any]:
    """Extracts station list from either raw GBFS document or compact schema."""
    if isinstance(doc, dict):
        if "stations" in doc and isinstance(doc["stations"], list):
            return doc["stations"]
        if "data" in doc and isinstance(doc["data"], dict):
            stations = doc["data"].get("stations")
            if isinstance(stations, list):
                return stations
    return []


def compact_station(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Projects raw station metadata onto essential 6 fields."""
    sid = raw.get("station_id")
    name = raw.get("name")
    lat = raw.get("lat")
    lon = raw.get("lon")
    if sid is None or name is None or lat is None or lon is None:
        return None
    try:
        lat_f = round(float(lat), 6)
        lon_f = round(float(lon), 6)
        capacity_i = int(raw.get("capacity", 0) or 0)
    except (ValueError, TypeError):
        return None

    return {
        "station_id": str(sid),
        "name": str(name),
        "short_name": str(raw.get("short_name") or ""),
        "lat": lat_f,
        "lon": lon_f,
        "capacity": capacity_i,
    }


def is_cache_fresh(cache_path: str, ttl_seconds: float = DEFAULT_TTL_SECONDS) -> bool:
    """Checks whether disk cache exists and was modified within ttl_seconds."""
    try:
        mtime = os.stat(cache_path).st_mtime
        return (time.time() - mtime) < ttl_seconds
    except OSError:
        return False


def atomic_write_json(path: str, data: dict[str, Any], log: Any = print) -> bool:
    """Writes JSON document to path atomically via thread-safe temp file rename."""
    parent = os.path.dirname(os.path.abspath(path))
    try:
        os.makedirs(parent, exist_ok=True)
    except OSError as e:
        log(f"[CitiBikeCatalog] failed to create cache directory {parent}: {e}")
        return False

    tmp_path = (
        path + f".tmp.{os.getpid()}.{threading.get_ident()}.{uuid.uuid4().hex[:8]}"
    )
    raw = json.dumps(data, separators=(",", ":")).encode("utf-8")
    try:
        with open(tmp_path, "wb") as f:
            f.write(raw)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
        os.replace(tmp_path, path)
        return True
    except OSError as e:
        log(f"[CitiBikeCatalog] failed to write cache to {path}: {e}")
        return False
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


def _default_stations_as_catalog() -> list[Any]:
    """Emergency built-in station catalog fallback derived from DEFAULT_STATIONS."""
    coords: dict[str, tuple[float, float, int, str]] = {
        "fadf00cf-d84a-49e8-9607-c67154915412": (
            40.748161,
            -74.032453,
            26,
            "HB501",
        ),
        "f417d8da-0f15-49b0-9e3c-3c3e55c2691d": (
            40.749985,
            -74.027150,
            24,
            "HB502",
        ),
        "655b0878-c22b-4f8c-8675-21bf30d1eebf": (
            40.751867,
            -74.030377,
            15,
            "HB505",
        ),
        "519824e4-69ba-4270-a395-17c204f328f8": (
            40.745984,
            -74.028199,
            21,
            "HB603",
        ),
        "21c4a77d-b1ae-4262-b143-087fd14a07b8": (
            40.745420,
            -74.033320,
            18,
            "HB303",
        ),
        "9d344652-976b-4c2d-bede-2ef19b0fbf13": (
            40.744398,
            -74.034501,
            18,
            "HB302",
        ),
    }
    res: list[dict[str, Any]] = []
    for s in DEFAULT_STATIONS:
        sid = s["id"]
        c = coords.get(sid, (40.7371, -74.0305, 20, ""))
        res.append(
            {
                "station_id": sid,
                "name": s.get("full_name", s["name"]),
                "short_name": c[3],
                "lat": c[0],
                "lon": c[1],
                "capacity": c[2],
            }
        )
    return res


class CitiBikeCatalog:
    """Manages Citi Bike station catalog with 24-hour TTL disk cache and offline seed."""

    def __init__(
        self,
        cache_dir: str | None = None,
        cache_path: str | None = None,
        seed_path: str | None = None,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        http_timeout: float = DEFAULT_HTTP_TIMEOUT,
        log: Any = print,
    ) -> None:
        self.cache_dir = cache_dir or resolve_cache_dir()
        self.cache_path = (
            cache_path
            if cache_path is not None
            else os.path.join(self.cache_dir, CACHE_FILENAME)
        )
        self.seed_path = (
            seed_path
            if seed_path is not None
            else os.path.join(resolve_data_dir(), SEED_FILENAME)
        )
        self.ttl_seconds = ttl_seconds
        self.http_timeout = http_timeout
        self._log = log
        self._lock = threading.Lock()
        self._cached_stations: list[dict[str, Any]] | None = None

    def invalidate_memory_cache(self) -> None:
        """Clears in-memory catalog, forcing next call to evaluate disk/network."""
        with self._lock:
            self._cached_stations = None

    def _read_file_stations(self, file_path: str) -> list[dict[str, Any]] | None:
        if not os.path.exists(file_path):
            return None
        try:
            with open(file_path, "rb") as f:
                doc = json.loads(f.read().decode("utf-8"))
            stations = extract_stations_from_doc(doc)
            if isinstance(stations, list) and len(stations) > 0:
                return stations
        except (OSError, ValueError, UnicodeDecodeError) as e:
            self._log(f"[CitiBikeCatalog] error reading {file_path}: {e}")
        return None

    def _fetch_live(self) -> list[Any]:
        req = urllib.request.Request(
            GBFS_STATION_INFO_URL,
            headers={
                "User-Agent": (f"TransitTracker/{VERSION} (Kindle Transit Display)"),
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=self.http_timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        stations_raw = extract_stations_from_doc(data)
        if not stations_raw:
            raise ValueError("GBFS station_information feed returned zero stations")
        compact: list[dict[str, Any]] = []
        for s in stations_raw:
            c = compact_station(s)
            if c is not None:
                compact.append(c)
        if not compact:
            raise ValueError("No valid stations found after compaction")
        compact.sort(key=lambda x: x["station_id"])
        payload = {
            "version": 1,
            "last_updated": int(time.time()),
            "ttl": self.ttl_seconds,
            "station_count": len(compact),
            "stations": compact,
        }
        atomic_write_json(self.cache_path, payload, log=self._log)
        return compact

    def get_stations(self, force_refresh: bool = False) -> list[Any]:
        """Returns station list following the 6-tier fallback sequence. Never raises."""
        with self._lock:
            # Tier 1: In-Memory Catalog
            if not force_refresh and self._cached_stations is not None:
                return self._cached_stations

            # Tier 2: Valid Disk Cache (< ttl_seconds)
            if not force_refresh and is_cache_fresh(self.cache_path, self.ttl_seconds):
                disk_stations = self._read_file_stations(self.cache_path)
                if disk_stations:
                    self._cached_stations = disk_stations
                    return disk_stations

            # Tier 3: Live Upstream GBFS Fetch
            try:
                live_stations = self._fetch_live()
                self._cached_stations = live_stations
                return live_stations
            except Exception as e:
                self._log(f"[CitiBikeCatalog] live GBFS fetch failed: {e}")

            # Tier 4: Stale Disk Cache (> 24h)
            if os.path.exists(self.cache_path):
                stale_stations = self._read_file_stations(self.cache_path)
                if stale_stations:
                    try:
                        age = int(time.time() - os.stat(self.cache_path).st_mtime)
                    except OSError:
                        age = 0
                    self._log(
                        f"[CitiBikeCatalog] Live GBFS fetch failed; serving stale disk cache (age {age}s)"
                    )
                    self._cached_stations = stale_stations
                    return stale_stations

            # Tier 5: Bundled Offline Seed Data
            if os.path.exists(self.seed_path):
                seed_stations = self._read_file_stations(self.seed_path)
                if seed_stations:
                    self._log(
                        f"[CitiBikeCatalog] Serving bundled offline seed data ({len(seed_stations)} stations)"
                    )
                    self._cached_stations = seed_stations
                    return seed_stations

            # Tier 6: Emergency Fallback Defaults
            self._log(
                "[CitiBikeCatalog] Seed data missing; emergency fallback to DEFAULT_STATIONS"
            )
            defaults = _default_stations_as_catalog()
            self._cached_stations = defaults
            return defaults


# Global default catalog singleton
CATALOG = CitiBikeCatalog()


def discover_citibike_stations(
    latitude: float,
    longitude: float,
    max_stations: int = 6,
    max_walk_minutes: int = 15,
    enable_micromobility: bool = True,
    force_refresh: bool = False,
    cache_path: str | None = None,
    seed_path: str | None = None,
    catalog: CitiBikeCatalog | None = None,
) -> list[Any]:
    """Discovers closest Citi Bike stations within walking threshold of coordinates.

    Returns [] if micro-mobility is disabled, coordinates are out of coverage,
    or no stations exist within max_walk_minutes.
    """
    if not enable_micromobility:
        return []

    if math.isnan(latitude) or math.isinf(latitude) or not (-90.0 <= latitude <= 90.0):
        raise ValueError(f"Invalid latitude: {latitude}")
    if (
        math.isnan(longitude)
        or math.isinf(longitude)
        or not (-180.0 <= longitude <= 180.0)
    ):
        raise ValueError(f"Invalid longitude: {longitude}")

    if max_stations <= 0 or max_walk_minutes <= 0:
        return []

    if not is_in_metro_area(latitude, longitude):
        return []

    if catalog is None:
        if cache_path is not None or seed_path is not None:
            active_catalog = CitiBikeCatalog(cache_path=cache_path, seed_path=seed_path)
        else:
            active_catalog = CATALOG
    else:
        active_catalog = catalog

    raw_stations = active_catalog.get_stations(force_refresh=force_refresh)
    return select_closest_stations(
        raw_stations,
        latitude,
        longitude,
        max_walk_minutes=max_walk_minutes,
        max_stations=max_stations,
    )
