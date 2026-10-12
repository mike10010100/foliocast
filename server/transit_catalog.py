"""Curated Route 126 Transit Stop Catalog for Hoboken, NJ.

Provides authoritative stop coordinates, names, corridor classifications,
pedestrian geometry calculations, and stop resolution helpers for NJ Transit
Route 126 NYC-bound buses into the Port Authority Bus Terminal (PABT).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, TypedDict

# Mean Earth radius in meters
EARTH_RADIUS_M = 6371000.0

# Pedestrian circuity multiplier accounting for urban street grid detour
CIRCUITY_MULTIPLIER = 1.25

# Standard urban pedestrian walking speed (meters per minute, 4.8 km/h ~ 3.0 mph)
WALK_SPEED_M_PER_MIN = 80.0

# Hoboken service bounding box
HOBOKEN_LAT_MIN = 40.720
HOBOKEN_LAT_MAX = 40.770
HOBOKEN_LON_MIN = -74.055
HOBOKEN_LON_MAX = -74.015

# Corridor tags
CORRIDOR_WASHINGTON = "washington"
CORRIDOR_CLINTON = "clinton"


class ResolvedStop(TypedDict, total=False):
    """Schema for a resolved transit stop dictionary."""

    id: str
    name: str
    line: str
    direction: str
    walk_min: int
    distance_m: int
    subtitle: str
    corridor: str
    lat: float
    lon: float


@dataclass(frozen=True)
class BusStop:
    """Immutable representation of a curated transit stop."""

    id: str  # Unique NJ Transit stop ID (e.g. "20512")
    name: str  # Clean display name (e.g. "Washington & 9th")
    full_name: str  # Full official name (e.g. "Washington St at 9th St")
    corridor: str  # Corridor tag: "washington" or "clinton"
    subtitle: str  # Badge subtitle (e.g. "Stop #20512 • via Lincoln Tunnel")
    latitude: float  # WGS84 latitude
    longitude: float  # WGS84 longitude
    direction: str = "inbound"  # Commute direction ("inbound" to NYC PABT)
    line: str = "126"  # Bus line / route number

    @property
    def lat(self) -> float:
        """Alias for latitude."""
        return self.latitude

    @property
    def lon(self) -> float:
        """Alias for longitude."""
        return self.longitude

    @property
    def route(self) -> str:
        """Alias for line."""
        return self.line


# CuratedStop is an alias for BusStop
CuratedStop = BusStop


# Authoritative Hoboken NJ Transit Route 126 Inbound (NYC-bound) Stops
# Washington Street Corridor: Central retail spine, runs south-to-north into Lincoln Tunnel
# Clinton Street Corridor: Western residential avenue, dedicated weekday commuter peak route
HOBOKEN_126_STOPS: tuple[BusStop, ...] = (
    # --- Washington Street Corridor (Inbound to NYC PABT) ---
    BusStop(
        id="20508",
        name="Washington & 1st",
        full_name="Washington St at 1st St",
        corridor=CORRIDOR_WASHINGTON,
        subtitle="Stop #20508 • via Washington St",
        latitude=40.73710,
        longitude=-74.03050,
        direction="inbound",
        line="126",
    ),
    BusStop(
        id="20509",
        name="Washington & 3rd",
        full_name="Washington St at 3rd St",
        corridor=CORRIDOR_WASHINGTON,
        subtitle="Stop #20509 • via Washington St",
        latitude=40.73970,
        longitude=-74.02980,
        direction="inbound",
        line="126",
    ),
    BusStop(
        id="20510",
        name="Washington & 5th",
        full_name="Washington St at 5th St",
        corridor=CORRIDOR_WASHINGTON,
        subtitle="Stop #20510 • via Washington St",
        latitude=40.74240,
        longitude=-74.02920,
        direction="inbound",
        line="126",
    ),
    BusStop(
        id="20511",
        name="Washington & 7th",
        full_name="Washington St at 7th St",
        corridor=CORRIDOR_WASHINGTON,
        subtitle="Stop #20511 • via Washington St",
        latitude=40.74510,
        longitude=-74.02860,
        direction="inbound",
        line="126",
    ),
    BusStop(
        id="20512",
        name="Washington & 9th",
        full_name="Washington St at 9th St",
        corridor=CORRIDOR_WASHINGTON,
        subtitle="Stop #20512 • via Lincoln Tunnel",
        latitude=40.74780,
        longitude=-74.02800,
        direction="inbound",
        line="126",
    ),
    BusStop(
        id="20513",
        name="Washington & 11th",
        full_name="Washington St at 11th St",
        corridor=CORRIDOR_WASHINGTON,
        subtitle="Stop #20513 • via Lincoln Tunnel",
        latitude=40.75050,
        longitude=-74.02740,
        direction="inbound",
        line="126",
    ),
    BusStop(
        id="20514",
        name="Washington & 13th",
        full_name="Washington St at 13th St",
        corridor=CORRIDOR_WASHINGTON,
        subtitle="Stop #20514 • via Lincoln Tunnel",
        latitude=40.75320,
        longitude=-74.02680,
        direction="inbound",
        line="126",
    ),
    BusStop(
        id="20515",
        name="Washington & 14th",
        full_name="Washington St at 14th St",
        corridor=CORRIDOR_WASHINGTON,
        subtitle="Stop #20515 • via Lincoln Tunnel",
        latitude=40.75460,
        longitude=-74.02650,
        direction="inbound",
        line="126",
    ),
    # --- Clinton Street Corridor (Inbound to NYC PABT) ---
    BusStop(
        id="20491",
        name="Clinton & 1st",
        full_name="Clinton St at 1st St",
        corridor=CORRIDOR_CLINTON,
        subtitle="Stop #20491 • via Clinton Ave",
        latitude=40.73790,
        longitude=-74.03530,
        direction="inbound",
        line="126",
    ),
    BusStop(
        id="20492",
        name="Clinton & 3rd",
        full_name="Clinton St at 3rd St",
        corridor=CORRIDOR_CLINTON,
        subtitle="Stop #20492 • via Clinton Ave",
        latitude=40.74060,
        longitude=-74.03470,
        direction="inbound",
        line="126",
    ),
    BusStop(
        id="33053",
        name="Clinton & 5th",
        full_name="Clinton St at 5th St",
        corridor=CORRIDOR_CLINTON,
        subtitle="Stop #33053 • via Clinton Ave",
        latitude=40.74330,
        longitude=-74.03410,
        direction="inbound",
        line="126",
    ),
    BusStop(
        id="33054",
        name="Clinton & 7th",
        full_name="Clinton St at 7th St",
        corridor=CORRIDOR_CLINTON,
        subtitle="Stop #33054 • via Clinton Ave",
        latitude=40.74600,
        longitude=-74.03350,
        direction="inbound",
        line="126",
    ),
    BusStop(
        id="20494",
        name="Clinton & 9th",
        full_name="Clinton St at 9th St",
        corridor=CORRIDOR_CLINTON,
        subtitle="Stop #20494 • via Clinton Ave",
        latitude=40.74870,
        longitude=-74.03290,
        direction="inbound",
        line="126",
    ),
    BusStop(
        id="20495",
        name="Clinton & 11th",
        full_name="Clinton St at 11th St",
        corridor=CORRIDOR_CLINTON,
        subtitle="Stop #20495 • via Clinton Ave",
        latitude=40.75140,
        longitude=-74.03230,
        direction="inbound",
        line="126",
    ),
)

# Index of stops by primary ID
_STOPS_BY_ID: dict[str, BusStop] = {stop.id: stop for stop in HOBOKEN_126_STOPS}

# Aliases mapping alternative/legacy/dispatch stop numbers to canonical stops
_STOP_ALIASES: dict[str, str] = {
    # Washington St alternative/dispatch numbers
    "20516": "20508",  # Washington & 1st
    # Clinton St alternative/dispatch numbers
    "20498": "20491",  # Clinton & 1st
    "20497": "20492",  # Clinton & 3rd
    "20496": "33053",  # Clinton & 5th
    "20493": "20495",  # Clinton & 11th
}

# Canonical default fallback stops (Washington & 9th and Clinton & 9th)
DEFAULT_STOPS: list[dict[str, Any]] = [
    {
        "id": "20512",
        "name": "Washington & 9th",
        "subtitle": "Stop #20512 • via Lincoln Tunnel",
        "walk_min": 3,
        "distance_m": 259,
        "line": "126",
        "direction": "inbound",
        "corridor": CORRIDOR_WASHINGTON,
        "lat": 40.74780,
        "lon": -74.02800,
    },
    {
        "id": "20494",
        "name": "Clinton & 9th",
        "subtitle": "Stop #20494 • via Clinton Ave",
        "walk_min": 3,
        "distance_m": 276,
        "line": "126",
        "direction": "inbound",
        "corridor": CORRIDOR_CLINTON,
        "lat": 40.74870,
        "lon": -74.03290,
    },
]


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


def is_in_hoboken_bounds(lat: float, lon: float) -> bool:
    """Checks whether coordinates fall within the Hoboken transit service area."""
    return (
        HOBOKEN_LAT_MIN <= lat <= HOBOKEN_LAT_MAX
        and HOBOKEN_LON_MIN <= lon <= HOBOKEN_LON_MAX
    )


def get_curated_stops(corridor: str | None = None, route: str = "126") -> list[BusStop]:
    """Returns curated stops filtered by corridor and route."""
    stops = [s for s in HOBOKEN_126_STOPS if s.line == route]
    if corridor:
        corridor_lower = corridor.lower()
        stops = [s for s in stops if s.corridor.lower() == corridor_lower]
    return list(stops)


# Alias for get_curated_stops
get_catalog_stops = get_curated_stops


def get_stop_by_id(stop_id: str) -> BusStop | None:
    """Retrieves a curated stop by stop ID, checking primary ID and known aliases."""
    clean_id = str(stop_id).strip()
    if clean_id in _STOPS_BY_ID:
        return _STOPS_BY_ID[clean_id]
    alias_target = _STOP_ALIASES.get(clean_id)
    if alias_target and alias_target in _STOPS_BY_ID:
        return _STOPS_BY_ID[alias_target]
    return None


# Alias for get_stop_by_id
find_stop_by_id = get_stop_by_id


def format_resolved_stop(
    stop: BusStop, user_lat: float, user_lon: float
) -> dict[str, Any]:
    """Formats a BusStop into a resolved stop dictionary with walk metrics."""
    dist_m = pedestrian_distance(user_lat, user_lon, stop.latitude, stop.longitude)
    walk_m = calculate_walk_minutes(dist_m)
    return {
        "id": stop.id,
        "name": stop.name,
        "line": stop.line,
        "direction": stop.direction,
        "walk_min": walk_m,
        "distance_m": dist_m,
        "subtitle": stop.subtitle,
        "corridor": stop.corridor,
        "lat": stop.latitude,
        "lon": stop.longitude,
    }
