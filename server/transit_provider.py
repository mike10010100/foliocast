"""Transit stop providers, dual-corridor auto-selection, and factory registry."""

from __future__ import annotations

import math
import threading
from abc import ABC, abstractmethod
from typing import Any, TypeVar, Union

from transit_catalog import (
    DEFAULT_STOPS,
    HOBOKEN_126_STOPS,
    BusStop,
    calculate_walk_minutes,
    get_stop_by_id,
    is_in_hoboken_bounds,
    pedestrian_distance,
)


class TransitStopProvider(ABC):
    """Abstract base class for municipal transit stop auto-selection."""

    @abstractmethod
    def resolve_stops(
        self,
        latitude: float,
        longitude: float,
        route: str = "126",
        overrides: list[Any] | None = None,
        fallback_to_default: bool = False,
    ) -> list[dict[str, Any]]:
        """Resolves active transit stops for coordinates and route.

        Args:
            latitude: User latitude (-90.0 to 90.0).
            longitude: User longitude (-180.0 to 180.0).
            route: Route designator (defaults to "126").
            overrides: Optional list of explicit user stop overrides.
            fallback_to_default: If True, returns DEFAULT_STOPS when out of bounds.

        Returns:
            List of resolved stop dictionaries containing id, name, line,
            direction, walk_min, distance_m, subtitle, corridor, lat, and lon.
        """
        pass


def _validate_coordinates(latitude: float, longitude: float) -> None:
    """Validates that latitude and longitude are valid finite floating-point numbers."""
    if (
        isinstance(latitude, bool)
        or not isinstance(latitude, (int, float))
        or math.isnan(latitude)
        or math.isinf(latitude)
        or not (-90.0 <= latitude <= 90.0)
    ):
        raise ValueError(f"Invalid latitude: {latitude}")
    if (
        isinstance(longitude, bool)
        or not isinstance(longitude, (int, float))
        or math.isnan(longitude)
        or math.isinf(longitude)
        or not (-180.0 <= longitude <= 180.0)
    ):
        raise ValueError(f"Invalid longitude: {longitude}")


def _format_stop_dict(stop: BusStop, distance_m: int, walk_min: int) -> dict[str, Any]:
    """Projects a catalog BusStop onto the resolved stop dictionary schema."""
    return {
        "id": str(stop.id),
        "name": str(stop.name),
        "subtitle": str(
            stop.subtitle or f"Stop #{stop.id} • via {stop.corridor.title()}"
        ),
        "walk_min": walk_min,
        "distance_m": distance_m,
        "line": str(stop.line),
        "direction": str(stop.direction),
        "corridor": str(stop.corridor),
        "lat": stop.latitude,
        "lon": stop.longitude,
    }


class Hoboken126Provider(TransitStopProvider):
    """Dual-corridor stop provider for Hoboken NJ Transit Route 126.

    Selects the nearest inbound Washington Street stop (index 0) and
    nearest inbound Clinton Street stop (index 1) to NYC Port Authority
    Bus Terminal.
    """

    def __init__(self, stops: tuple[BusStop, ...] | None = None) -> None:
        self.stops = stops or HOBOKEN_126_STOPS

    def resolve_stops(
        self,
        latitude: float,
        longitude: float,
        route: str = "126",
        overrides: list[Any] | None = None,
        fallback_to_default: bool = False,
    ) -> list[dict[str, Any]]:
        _validate_coordinates(latitude, longitude)

        target_route = (route or "126").strip()
        if target_route != "126":
            raise ValueError(
                f"Hoboken126Provider only supports route '126', got '{route}'"
            )

        # 1. Respect explicit user overrides if non-empty
        if overrides:
            return self._resolve_overrides(overrides, latitude, longitude, target_route)

        # 2. Check bounding box coverage
        if not is_in_hoboken_bounds(latitude, longitude):
            if fallback_to_default:
                return [dict(s) for s in DEFAULT_STOPS]
            return []

        # 3. Filter inbound candidate stops for route 126
        candidates = [
            s
            for s in self.stops
            if s.line == target_route and s.direction.lower() == "inbound"
        ]
        if not candidates:
            candidates = [s for s in self.stops if s.direction.lower() == "inbound"]

        washington_stops = [s for s in candidates if s.corridor.lower() == "washington"]
        clinton_stops = [s for s in candidates if s.corridor.lower() == "clinton"]

        results: list[dict[str, Any]] = []

        # 4. Find closest Washington Street stop (index 0)
        if washington_stops:
            best_wash = min(
                washington_stops,
                key=lambda s: (
                    pedestrian_distance(latitude, longitude, s.latitude, s.longitude),
                    s.id,
                ),
            )
            dist_w = pedestrian_distance(
                latitude, longitude, best_wash.latitude, best_wash.longitude
            )
            walk_w = calculate_walk_minutes(dist_w)
            results.append(_format_stop_dict(best_wash, dist_w, walk_w))

        # 5. Find closest Clinton Street stop (index 1)
        if clinton_stops:
            best_clin = min(
                clinton_stops,
                key=lambda s: (
                    pedestrian_distance(latitude, longitude, s.latitude, s.longitude),
                    s.id,
                ),
            )
            dist_c = pedestrian_distance(
                latitude, longitude, best_clin.latitude, best_clin.longitude
            )
            walk_c = calculate_walk_minutes(dist_c)
            results.append(_format_stop_dict(best_clin, dist_c, walk_c))

        return results

    def _resolve_overrides(
        self,
        overrides: Any,
        user_lat: float,
        user_lon: float,
        route: str,
    ) -> list[dict[str, Any]]:
        if not isinstance(overrides, (list, tuple)):
            raise ValueError("overrides must be a list or tuple")
        if len(overrides) > 16:
            raise ValueError(
                f"At most 16 stops allowed in overrides, got {len(overrides)}"
            )

        resolved: list[dict[str, Any]] = []
        for i, item in enumerate(overrides):
            if isinstance(item, bool):
                raise ValueError(
                    f"overrides[{i}]: expected stop ID string or object, got bool"
                )
            elif isinstance(item, (int, str)):
                clean_id = str(item).strip()
                if not clean_id:
                    raise ValueError(f"overrides[{i}]: stop ID must not be empty")
                cat_stop = get_stop_by_id(clean_id)
                if cat_stop:
                    dist_m = pedestrian_distance(
                        user_lat, user_lon, cat_stop.latitude, cat_stop.longitude
                    )
                    walk_m = calculate_walk_minutes(dist_m)
                    resolved.append(
                        {
                            "id": cat_stop.id,
                            "name": cat_stop.name,
                            "subtitle": cat_stop.subtitle,
                            "walk_min": walk_m,
                            "distance_m": dist_m,
                            "line": cat_stop.line,
                            "direction": cat_stop.direction,
                            "corridor": cat_stop.corridor,
                            "lat": cat_stop.latitude,
                            "lon": cat_stop.longitude,
                        }
                    )
                else:
                    resolved.append(
                        {
                            "id": clean_id,
                            "name": f"Stop #{clean_id}",
                            "subtitle": f"Stop #{clean_id} (custom)",
                            "walk_min": 5,
                            "distance_m": 400,
                            "line": route,
                            "direction": "inbound",
                            "corridor": "custom",
                        }
                    )
            elif isinstance(item, dict):
                if "id" not in item:
                    raise ValueError(f"overrides[{i}]: missing required 'id' key")
                clean_id = str(item["id"]).strip()
                if not clean_id:
                    raise ValueError(f"overrides[{i}].id: must not be empty")

                cat_stop = get_stop_by_id(clean_id)
                if cat_stop:
                    calc_dist = pedestrian_distance(
                        user_lat,
                        user_lon,
                        cat_stop.latitude,
                        cat_stop.longitude,
                    )
                    calc_walk = calculate_walk_minutes(calc_dist)
                    default_name = cat_stop.name
                    default_subtitle = cat_stop.subtitle
                    default_line = cat_stop.line
                    default_dir = cat_stop.direction
                    default_corridor = cat_stop.corridor
                    default_lat: float | None = cat_stop.latitude
                    default_lon: float | None = cat_stop.longitude
                else:
                    calc_dist = 400
                    calc_walk = 5
                    default_name = f"Stop #{clean_id}"
                    default_subtitle = f"Stop #{clean_id} (custom)"
                    default_line = route
                    default_dir = "inbound"
                    default_corridor = "custom"
                    default_lat = None
                    default_lon = None

                # walk_min validation
                walk_min = item.get("walk_min")
                if walk_min is not None:
                    if (
                        isinstance(walk_min, bool)
                        or not isinstance(walk_min, int)
                        or not (1 <= walk_min <= 180)
                    ):
                        raise ValueError(
                            f"overrides[{i}].walk_min must be between 1 and 180"
                        )
                else:
                    walk_min = calc_walk

                # distance_m validation
                distance_m = item.get("distance_m")
                if distance_m is not None:
                    if (
                        isinstance(distance_m, bool)
                        or not isinstance(distance_m, int)
                        or not (0 <= distance_m <= 50000)
                    ):
                        raise ValueError(
                            f"overrides[{i}].distance_m must be between 0 and 50000"
                        )
                else:
                    distance_m = calc_dist

                name = str(item.get("name") or default_name).strip() or default_name
                subtitle = (
                    str(item.get("subtitle") or default_subtitle).strip()
                    or default_subtitle
                )
                line = str(item.get("line") or default_line).strip() or default_line
                direction = (
                    str(item.get("direction") or default_dir).strip() or default_dir
                )
                corridor = (
                    str(item.get("corridor") or default_corridor).strip()
                    or default_corridor
                )

                res_dict: dict[str, Any] = {
                    "id": clean_id,
                    "name": name,
                    "subtitle": subtitle,
                    "walk_min": walk_min,
                    "distance_m": distance_m,
                    "line": line,
                    "direction": direction,
                    "corridor": corridor,
                }
                lat_val = item.get("lat", default_lat)
                lon_val = item.get("lon", default_lon)
                if lat_val is not None:
                    res_dict["lat"] = float(lat_val)
                if lon_val is not None:
                    res_dict["lon"] = float(lon_val)

                resolved.append(res_dict)
            else:
                raise ValueError(
                    f"overrides[{i}]: expected stop ID string or object, got {type(item).__name__}"
                )
        return resolved


def _normalize_city_route(city: str, route: str) -> tuple[str, str]:
    """Normalizes city and route identifiers for case-insensitive lookup."""
    raw_city = (city or "Hoboken").strip().lower()
    clean_city = raw_city.split(",")[0].strip()
    clean_route = (route or "126").strip().lower()
    return clean_city, clean_route


ProviderType = Union[TransitStopProvider, type[TransitStopProvider]]
T = TypeVar("T", bound=ProviderType)


class TransitProviderRegistry:
    """Thread-safe registry for municipal transit providers."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._providers: dict[tuple[str, str], ProviderType] = {}
        self.register("hoboken", "126", Hoboken126Provider)

    def register(
        self,
        city: str,
        route: str,
        provider: ProviderType,
    ) -> None:
        norm_city, norm_route = _normalize_city_route(city, route)
        with self._lock:
            self._providers[(norm_city, norm_route)] = provider

    def get(self, city: str = "Hoboken", route: str = "126") -> TransitStopProvider:
        norm_city, norm_route = _normalize_city_route(city, route)
        with self._lock:
            provider = self._providers.get((norm_city, norm_route))

        if provider is None:
            raise ValueError(
                f"No transit provider registered for city='{city}', route='{route}'"
            )

        if isinstance(provider, type):
            return provider()
        return provider


# Global singleton registry
_REGISTRY = TransitProviderRegistry()


def register_transit_provider(
    city: str,
    route: str,
    provider: ProviderType | None = None,
) -> Any:
    """Registers a TransitStopProvider for a city/route combination.

    Can be invoked directly:
        register_transit_provider("Jersey City", "80", my_provider)
    Or as a decorator:
        @register_transit_provider("Jersey City", "80")
        class JerseyCity80Provider(TransitStopProvider):
            ...
    """

    def _decorator(cls_or_inst: T) -> T:
        _REGISTRY.register(city, route, cls_or_inst)
        return cls_or_inst

    if provider is not None:
        return _decorator(provider)
    return _decorator


def get_transit_provider(
    city: str = "Hoboken", route: str = "126"
) -> TransitStopProvider:
    """Returns the registered TransitStopProvider for (city, route)."""
    return _REGISTRY.get(city=city, route=route)
