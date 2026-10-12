"""Comprehensive unit and behavioral tests for transit catalog and transit providers."""

from __future__ import annotations

import dataclasses
import unittest
from typing import Any

from transit_catalog import (
    CORRIDOR_CLINTON,
    CORRIDOR_WASHINGTON,
    DEFAULT_STOPS,
    HOBOKEN_126_STOPS,
    BusStop,
    CuratedStop,
    calculate_walk_minutes,
    find_stop_by_id,
    format_resolved_stop,
    get_catalog_stops,
    get_curated_stops,
    get_stop_by_id,
    haversine_distance,
    is_in_hoboken_bounds,
    pedestrian_distance,
)
from transit_provider import (
    Hoboken126Provider,
    TransitProviderRegistry,
    TransitStopProvider,
    get_transit_provider,
    register_transit_provider,
)


class TestTransitCatalog(unittest.TestCase):
    """Verifies catalog integrity, coordinates, corridor tagging, and lookup functions."""

    def test_catalog_completeness_and_corridors(self) -> None:
        """Catalog must have 14 curated stops: 8 Washington and 6 Clinton."""
        self.assertEqual(len(HOBOKEN_126_STOPS), 14)
        wash_stops = [s for s in HOBOKEN_126_STOPS if s.corridor == CORRIDOR_WASHINGTON]
        clin_stops = [s for s in HOBOKEN_126_STOPS if s.corridor == CORRIDOR_CLINTON]
        self.assertEqual(len(wash_stops), 8)
        self.assertEqual(len(clin_stops), 6)

    def test_catalog_ids_unique_and_non_empty(self) -> None:
        """All stop IDs in the catalog must be unique, non-empty strings."""
        ids = [s.id for s in HOBOKEN_126_STOPS]
        self.assertEqual(len(ids), len(set(ids)))
        for stop in HOBOKEN_126_STOPS:
            self.assertTrue(stop.id.isdigit())
            self.assertTrue(len(stop.id) >= 4)
            self.assertTrue(len(stop.name) > 0)
            self.assertTrue(len(stop.full_name) > 0)
            self.assertTrue(len(stop.subtitle) > 0)
            self.assertEqual(stop.direction, "inbound")
            self.assertEqual(stop.line, "126")

    def test_catalog_coordinates_in_hoboken(self) -> None:
        """All curated stops must lie within the Hoboken municipal bounds."""
        for stop in HOBOKEN_126_STOPS:
            self.assertTrue(
                40.730 <= stop.latitude <= 40.760,
                f"Latitude out of expected range for {stop.id}: {stop.latitude}",
            )
            self.assertTrue(
                -74.040 <= stop.longitude <= -74.020,
                f"Longitude out of expected range for {stop.id}: {stop.longitude}",
            )
            self.assertTrue(
                is_in_hoboken_bounds(stop.latitude, stop.longitude),
                f"Stop {stop.id} failed is_in_hoboken_bounds check",
            )

    def test_bus_stop_immutability_and_aliases(self) -> None:
        """BusStop must be frozen dataclass with property aliases."""
        stop = HOBOKEN_126_STOPS[0]
        self.assertIs(CuratedStop, BusStop)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            stop.id = "99999"  # type: ignore[misc]

        self.assertEqual(stop.lat, stop.latitude)
        self.assertEqual(stop.lon, stop.longitude)
        self.assertEqual(stop.route, stop.line)

    def test_catalog_filtering(self) -> None:
        """get_curated_stops and get_catalog_stops filter by corridor and route."""
        all_stops = get_curated_stops()
        self.assertEqual(len(all_stops), 14)
        self.assertEqual(get_catalog_stops(), all_stops)

        wash = get_curated_stops(corridor="washington")
        self.assertEqual(len(wash), 8)
        self.assertTrue(all(s.corridor == CORRIDOR_WASHINGTON for s in wash))

        clin = get_curated_stops(corridor="CLINTON")
        self.assertEqual(len(clin), 6)
        self.assertTrue(all(s.corridor == CORRIDOR_CLINTON for s in clin))

        unknown_corridor = get_curated_stops(corridor="nonexistent")
        self.assertEqual(unknown_corridor, [])

        unknown_route = get_curated_stops(route="999")
        self.assertEqual(unknown_route, [])

    def test_get_stop_by_id_and_aliases(self) -> None:
        """Lookup by ID resolves canonical GTFS IDs and aliases."""
        # Canonical IDs
        wash_9 = get_stop_by_id("20512")
        self.assertIsNotNone(wash_9)
        assert wash_9 is not None
        self.assertEqual(wash_9.name, "Washington & 9th")

        clin_9 = find_stop_by_id("20494")
        self.assertIsNotNone(clin_9)
        assert clin_9 is not None
        self.assertEqual(clin_9.name, "Clinton & 9th")

        # Whitespace handling
        self.assertEqual(get_stop_by_id("  20512  "), wash_9)

        # Aliases mapping legacy/dispatch numbers
        self.assertEqual(get_stop_by_id("20516"), get_stop_by_id("20508"))
        self.assertEqual(get_stop_by_id("20498"), get_stop_by_id("20491"))
        self.assertEqual(get_stop_by_id("20497"), get_stop_by_id("20492"))
        self.assertEqual(get_stop_by_id("20496"), get_stop_by_id("33053"))
        self.assertEqual(get_stop_by_id("20493"), get_stop_by_id("20495"))

        # Unknown ID returns None
        self.assertIsNone(get_stop_by_id("99999"))
        self.assertIsNone(find_stop_by_id("unknown"))

    def test_is_in_hoboken_bounds(self) -> None:
        """Verifies boundary checking for Hoboken transit bounding box."""
        # In-bounds: Hoboken City Hall
        self.assertTrue(is_in_hoboken_bounds(40.7371, -74.0305))
        # In-bounds corners
        self.assertTrue(is_in_hoboken_bounds(40.720, -74.055))
        self.assertTrue(is_in_hoboken_bounds(40.770, -74.015))

        # Out-of-bounds
        self.assertFalse(is_in_hoboken_bounds(40.719, -74.030))  # south
        self.assertFalse(is_in_hoboken_bounds(40.771, -74.030))  # north
        self.assertFalse(is_in_hoboken_bounds(40.748, -74.056))  # west
        self.assertFalse(is_in_hoboken_bounds(40.748, -74.014))  # east
        # Distant locations
        self.assertFalse(
            is_in_hoboken_bounds(40.7580, -73.9855)
        )  # Manhattan Times Square
        self.assertFalse(is_in_hoboken_bounds(35.6762, 139.6503))  # Tokyo


class TestPedestrianGeometry(unittest.TestCase):
    """Verifies Haversine, pedestrian circuity, and walk time calculations."""

    def test_haversine_properties(self) -> None:
        """Haversine distance must satisfy identity, symmetry, and positive definiteness."""
        p1 = (40.7371, -74.0305)
        p2 = (40.74780, -74.02800)

        # Identity
        self.assertEqual(haversine_distance(p1[0], p1[1], p1[0], p1[1]), 0.0)

        # Symmetry
        d1 = haversine_distance(p1[0], p1[1], p2[0], p2[1])
        d2 = haversine_distance(p2[0], p2[1], p1[0], p1[1])
        self.assertAlmostEqual(d1, d2, places=6)

        # Realistic value (~207 meters)
        self.assertTrue(200.0 < d1 < 215.0)

    def test_pedestrian_distance(self) -> None:
        """Pedestrian distance applies 1.25 circuity multiplier and returns integer."""
        p1 = (40.7371, -74.0305)
        p2 = (40.74780, -74.02800)

        straight = haversine_distance(p1[0], p1[1], p2[0], p2[1])
        ped = pedestrian_distance(p1[0], p1[1], p2[0], p2[1])

        self.assertIsInstance(ped, int)
        self.assertEqual(ped, int(round(straight * 1.25)))
        self.assertEqual(ped, 259)

    def test_calculate_walk_minutes(self) -> None:
        """Walk time evaluates at 80 m/min, with min 1 min if distance > 0."""
        self.assertEqual(calculate_walk_minutes(0), 0)
        self.assertEqual(calculate_walk_minutes(-50), 0)

        # Distance > 0 must be at least 1 min
        self.assertEqual(calculate_walk_minutes(10), 1)
        self.assertEqual(calculate_walk_minutes(40), 1)
        self.assertEqual(calculate_walk_minutes(80), 1)
        self.assertEqual(calculate_walk_minutes(120), 2)
        self.assertEqual(calculate_walk_minutes(160), 2)
        self.assertEqual(calculate_walk_minutes(240), 3)
        self.assertEqual(calculate_walk_minutes(259), 3)
        self.assertEqual(calculate_walk_minutes(800), 10)

    def test_format_resolved_stop(self) -> None:
        """format_resolved_stop projects BusStop into expected schema."""
        stop = HOBOKEN_126_STOPS[4]  # Washington & 9th (20512)
        resolved = format_resolved_stop(stop, 40.7371, -74.0305)
        self.assertEqual(resolved["id"], "20512")
        self.assertEqual(resolved["name"], "Washington & 9th")
        self.assertEqual(resolved["line"], "126")
        self.assertEqual(resolved["direction"], "inbound")
        self.assertEqual(resolved["walk_min"], 3)
        self.assertEqual(resolved["distance_m"], 259)
        self.assertEqual(resolved["subtitle"], "Stop #20512 • via Lincoln Tunnel")
        self.assertEqual(resolved["corridor"], "washington")
        self.assertEqual(resolved["lat"], 40.74780)
        self.assertEqual(resolved["lon"], -74.02800)


class TestHoboken126ProviderDualCorridor(unittest.TestCase):
    """Verifies dual-corridor auto-selection, backward compatibility, and geo zones."""

    def setUp(self) -> None:
        self.provider = Hoboken126Provider()

    def test_backward_compatibility_919_park_ave(self) -> None:
        """Default Hoboken City Hall Hoboken MUST resolve to 20512 and 20494."""
        user_lat = 40.7371
        user_lon = -74.0305

        stops = self.provider.resolve_stops(user_lat, user_lon)
        self.assertEqual(len(stops), 2)

        # Index 0: Nearest Washington St stop
        w_stop = stops[0]
        self.assertEqual(w_stop["id"], "20512")
        self.assertEqual(w_stop["name"], "Washington & 9th")
        self.assertEqual(w_stop["corridor"], CORRIDOR_WASHINGTON)
        self.assertEqual(w_stop["subtitle"], "Stop #20512 • via Lincoln Tunnel")
        self.assertEqual(w_stop["distance_m"], 259)
        self.assertIn(w_stop["walk_min"], (3, 4, 5))
        self.assertEqual(w_stop["line"], "126")
        self.assertEqual(w_stop["direction"], "inbound")

        # Index 1: Nearest Clinton St stop
        c_stop = stops[1]
        self.assertEqual(c_stop["id"], "20494")
        self.assertEqual(c_stop["name"], "Clinton & 9th")
        self.assertEqual(c_stop["corridor"], CORRIDOR_CLINTON)
        self.assertEqual(c_stop["subtitle"], "Stop #20494 • via Clinton Ave")
        self.assertEqual(c_stop["distance_m"], 276)
        self.assertEqual(c_stop["walk_min"], 3)
        self.assertEqual(c_stop["line"], "126")
        self.assertEqual(c_stop["direction"], "inbound")

    def test_north_hoboken_selection(self) -> None:
        """North Hoboken (14th & Washington) selects 20515 and 20495."""
        stops = self.provider.resolve_stops(40.7546, -74.0265)
        self.assertEqual(len(stops), 2)
        self.assertEqual(stops[0]["id"], "20515")  # Washington & 14th
        self.assertEqual(stops[0]["name"], "Washington & 14th")
        self.assertEqual(stops[1]["id"], "20495")  # Clinton & 11th
        self.assertEqual(stops[1]["name"], "Clinton & 11th")

    def test_central_hoboken_selection(self) -> None:
        """Central Hoboken (7th & Park) selects 20511 and 33054."""
        stops = self.provider.resolve_stops(40.7451, -74.0310)
        self.assertEqual(len(stops), 2)
        self.assertEqual(stops[0]["id"], "20511")  # Washington & 7th
        self.assertEqual(stops[0]["name"], "Washington & 7th")
        self.assertEqual(stops[1]["id"], "33054")  # Clinton & 7th
        self.assertEqual(stops[1]["name"], "Clinton & 7th")

    def test_south_hoboken_selection(self) -> None:
        """South Hoboken (1st & Washington) selects 20508 and 20491."""
        stops = self.provider.resolve_stops(40.7371, -74.0305)
        self.assertEqual(len(stops), 2)
        self.assertEqual(stops[0]["id"], "20508")  # Washington & 1st
        self.assertEqual(stops[0]["name"], "Washington & 1st")
        self.assertEqual(stops[1]["id"], "20491")  # Clinton & 1st
        self.assertEqual(stops[1]["name"], "Clinton & 1st")

    def test_hoboken_terminal_selection(self) -> None:
        """Hoboken Terminal selects closest inbound stops 20508 and 20491."""
        stops = self.provider.resolve_stops(40.7357, -74.0290)
        self.assertEqual(len(stops), 2)
        self.assertEqual(stops[0]["id"], "20508")
        self.assertEqual(stops[1]["id"], "20491")

    def test_equidistant_tie_breaking_is_deterministic(self) -> None:
        """Equidistant points produce deterministic, stable stop selection."""
        # Exactly halfway between 7th and 9th on Washington
        mid_lat = (40.74510 + 40.74780) / 2.0
        mid_lon = (-74.02860 + -74.02800) / 2.0
        res1 = self.provider.resolve_stops(mid_lat, mid_lon)
        res2 = self.provider.resolve_stops(mid_lat, mid_lon)
        self.assertEqual(res1, res2)

    def test_single_corridor_candidate_pool(self) -> None:
        """Provider with only Washington or only Clinton stops returns single stop."""
        wash_only = tuple(
            s for s in HOBOKEN_126_STOPS if s.corridor == CORRIDOR_WASHINGTON
        )
        prov_wash = Hoboken126Provider(stops=wash_only)
        res_w = prov_wash.resolve_stops(40.7484, -74.0302)
        self.assertEqual(len(res_w), 1)
        self.assertEqual(res_w[0]["corridor"], CORRIDOR_WASHINGTON)

        clin_only = tuple(
            s for s in HOBOKEN_126_STOPS if s.corridor == CORRIDOR_CLINTON
        )
        prov_clin = Hoboken126Provider(stops=clin_only)
        res_c = prov_clin.resolve_stops(40.7484, -74.0302)
        self.assertEqual(len(res_c), 1)
        self.assertEqual(res_c[0]["corridor"], CORRIDOR_CLINTON)

    def test_inbound_route_fallback(self) -> None:
        """When no stops match route 126 exactly, fall back to inbound stops."""
        custom_stop = BusStop(
            id="90001",
            name="Custom Wash",
            full_name="Custom Washington St",
            corridor=CORRIDOR_WASHINGTON,
            subtitle="Stop #90001",
            latitude=40.74780,
            longitude=-74.02800,
            direction="inbound",
            line="CUSTOM",
        )
        prov = Hoboken126Provider(stops=(custom_stop,))
        res = prov.resolve_stops(40.7484, -74.0302)
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["id"], "90001")


class TestHoboken126ProviderOverrides(unittest.TestCase):
    """Verifies stops_override behavior, validation, metadata enrichment, and precedence."""

    def setUp(self) -> None:
        self.provider = Hoboken126Provider()

    def test_overrides_string_ids_enrichment(self) -> None:
        """String stop IDs in overrides are enriched with catalog metadata."""
        overrides = ["20512", "20494"]
        stops = self.provider.resolve_stops(
            40.7371, -74.0305, overrides=overrides
        )
        self.assertEqual(len(stops), 2)
        self.assertEqual(stops[0]["id"], "20512")
        self.assertEqual(stops[0]["name"], "Washington & 9th")
        self.assertEqual(stops[0]["subtitle"], "Stop #20512 • via Lincoln Tunnel")
        self.assertEqual(stops[0]["walk_min"], 3)
        self.assertEqual(stops[0]["distance_m"], 259)

        self.assertEqual(stops[1]["id"], "20494")
        self.assertEqual(stops[1]["name"], "Clinton & 9th")
        self.assertEqual(stops[1]["subtitle"], "Stop #20494 • via Clinton Ave")
        self.assertEqual(stops[1]["walk_min"], 3)
        self.assertEqual(stops[1]["distance_m"], 276)

    def test_overrides_numeric_int_conversion(self) -> None:
        """Integer IDs in overrides are converted cleanly to strings."""
        overrides: list[Any] = [20512, 20494]
        stops = self.provider.resolve_stops(
            40.7371, -74.0305, overrides=overrides
        )
        self.assertEqual(len(stops), 2)
        self.assertEqual(stops[0]["id"], "20512")
        self.assertEqual(stops[1]["id"], "20494")

    def test_overrides_dict_partial_enrichment(self) -> None:
        """Dict with partial keys has remaining fields enriched from catalog."""
        overrides = [{"id": "20512"}]
        stops = self.provider.resolve_stops(
            40.7371, -74.0305, overrides=overrides
        )
        self.assertEqual(len(stops), 1)
        self.assertEqual(stops[0]["id"], "20512")
        self.assertEqual(stops[0]["name"], "Washington & 9th")
        self.assertEqual(stops[0]["subtitle"], "Stop #20512 • via Lincoln Tunnel")
        self.assertEqual(stops[0]["line"], "126")
        self.assertEqual(stops[0]["direction"], "inbound")
        self.assertEqual(stops[0]["corridor"], "washington")
        self.assertEqual(stops[0]["walk_min"], 3)
        self.assertEqual(stops[0]["distance_m"], 259)

    def test_overrides_dict_custom_fields_preserved(self) -> None:
        """Custom stop not in catalog preserves all explicit fields."""
        overrides = [
            {
                "id": "99999",
                "name": "Custom 10th St Stop",
                "subtitle": "Stop #99999 • Express Special",
                "walk_min": 7,
                "distance_m": 550,
                "line": "126",
                "direction": "inbound",
                "corridor": "willow",
            }
        ]
        stops = self.provider.resolve_stops(
            40.7371, -74.0305, overrides=overrides
        )
        self.assertEqual(len(stops), 1)
        self.assertEqual(stops[0]["id"], "99999")
        self.assertEqual(stops[0]["name"], "Custom 10th St Stop")
        self.assertEqual(stops[0]["subtitle"], "Stop #99999 • Express Special")
        self.assertEqual(stops[0]["walk_min"], 7)
        self.assertEqual(stops[0]["distance_m"], 550)
        self.assertEqual(stops[0]["corridor"], "willow")

    def test_overrides_precedence_over_coordinates(self) -> None:
        """Overrides take strict precedence regardless of proximity to user coords."""
        # User is in South Hoboken (1st St), but override requests North Hoboken (14th St)
        overrides = ["20515"]  # Washington & 14th
        stops = self.provider.resolve_stops(40.7371, -74.0305, overrides=overrides)
        self.assertEqual(len(stops), 1)
        self.assertEqual(stops[0]["id"], "20515")
        self.assertEqual(stops[0]["name"], "Washington & 14th")

    def test_overrides_order_preservation(self) -> None:
        """Overrides preserve the exact sequence specified by the caller."""
        overrides = ["20494", "20512"]  # Clinton first, Washington second
        stops = self.provider.resolve_stops(
            40.7371, -74.0305, overrides=overrides
        )
        self.assertEqual(len(stops), 2)
        self.assertEqual(stops[0]["id"], "20494")
        self.assertEqual(stops[1]["id"], "20512")

    def test_empty_overrides_falls_back_to_discovery(self) -> None:
        """Empty overrides list or None falls back to geometric discovery."""
        res_none = self.provider.resolve_stops(40.7371, -74.0305, overrides=None)
        res_empty = self.provider.resolve_stops(40.7371, -74.0305, overrides=[])
        self.assertEqual(len(res_none), 2)
        self.assertEqual(res_none, res_empty)

    def test_overrides_validation_errors(self) -> None:
        """Invalid override structures raise ValueError."""
        # Not a list
        with self.assertRaises(ValueError):
            self.provider.resolve_stops(
                40.7484,
                -74.030,
                overrides="invalid",  # type: ignore[arg-type]
            )

        # Exceeds max count 16
        with self.assertRaises(ValueError):
            self.provider.resolve_stops(40.7484, -74.030, overrides=["20512"] * 17)

        # Dict missing 'id' key
        with self.assertRaises(ValueError):
            self.provider.resolve_stops(40.7484, -74.030, overrides=[{"name": "No ID"}])

        # Empty ID string
        with self.assertRaises(ValueError):
            self.provider.resolve_stops(40.7484, -74.030, overrides=[{"id": "   "}])
        with self.assertRaises(ValueError):
            self.provider.resolve_stops(40.7484, -74.030, overrides=["   "])

        # Bool item
        with self.assertRaises(ValueError):
            self.provider.resolve_stops(
                40.7484,
                -74.030,
                overrides=[True],  # type: ignore[list-item]
            )

        # Invalid walk_min out of range
        with self.assertRaises(ValueError):
            self.provider.resolve_stops(
                40.7484, -74.030, overrides=[{"id": "20512", "walk_min": 0}]
            )
        with self.assertRaises(ValueError):
            self.provider.resolve_stops(
                40.7484, -74.030, overrides=[{"id": "20512", "walk_min": 200}]
            )

        # Invalid distance_m out of range
        with self.assertRaises(ValueError):
            self.provider.resolve_stops(
                40.7484, -74.030, overrides=[{"id": "20512", "distance_m": -1}]
            )
        with self.assertRaises(ValueError):
            self.provider.resolve_stops(
                40.7484,
                -74.030,
                overrides=[{"id": "20512", "distance_m": 60000}],
            )

    def test_overrides_unknown_string_id(self) -> None:
        """Unknown string stop ID generates fallback custom dictionary."""
        overrides = ["unknown_stop_123"]
        stops = self.provider.resolve_stops(
            40.7371, -74.0305, overrides=overrides
        )
        self.assertEqual(len(stops), 1)
        self.assertEqual(stops[0]["id"], "unknown_stop_123")
        self.assertEqual(stops[0]["name"], "Stop #unknown_stop_123")
        self.assertEqual(stops[0]["subtitle"], "Stop #unknown_stop_123 (custom)")
        self.assertEqual(stops[0]["walk_min"], 5)
        self.assertEqual(stops[0]["distance_m"], 400)
        self.assertEqual(stops[0]["corridor"], "custom")

    def test_overrides_unrecognized_item_type(self) -> None:
        """Unrecognized item type raises ValueError."""
        with self.assertRaises(ValueError):
            self.provider.resolve_stops(
                40.7484,
                -74.030,
                overrides=[None],  # type: ignore[list-item]
            )

    def test_overrides_dict_custom_lat_lon(self) -> None:
        """Explicit custom lat and lon in override dict are preserved."""
        overrides = [{"id": "20512", "lat": 40.75, "lon": -74.03}]
        stops = self.provider.resolve_stops(
            40.7371, -74.0305, overrides=overrides
        )
        self.assertEqual(len(stops), 1)
        self.assertEqual(stops[0]["lat"], 40.75)
        self.assertEqual(stops[0]["lon"], -74.03)


class TestHoboken126ProviderBoundariesAndErrors(unittest.TestCase):
    """Verifies out-of-coverage handling and input validation."""

    def setUp(self) -> None:
        self.provider = Hoboken126Provider()

    def test_out_of_coverage_returns_empty_by_default(self) -> None:
        """Coordinates outside Hoboken service area return empty list []."""
        # Tokyo
        self.assertEqual(
            self.provider.resolve_stops(35.6762, 139.6503),
            [],
        )
        # Manhattan
        self.assertEqual(
            self.provider.resolve_stops(40.7580, -73.9855),
            [],
        )

    def test_out_of_coverage_fallback_to_default(self) -> None:
        """When fallback_to_default=True, out-of-coverage coordinates return DEFAULT_STOPS."""
        res = self.provider.resolve_stops(35.6762, 139.6503, fallback_to_default=True)
        self.assertEqual(len(res), 2)
        self.assertEqual(res[0]["id"], "20512")
        self.assertEqual(res[1]["id"], "20494")
        self.assertEqual(res, DEFAULT_STOPS)

    def test_invalid_coordinates_raise_value_error(self) -> None:
        """NaN, Inf, booleans, and out-of-range coords raise ValueError."""
        with self.assertRaises(ValueError):
            self.provider.resolve_stops(float("nan"), -74.030)
        with self.assertRaises(ValueError):
            self.provider.resolve_stops(40.748, float("nan"))
        with self.assertRaises(ValueError):
            self.provider.resolve_stops(float("inf"), -74.030)
        with self.assertRaises(ValueError):
            self.provider.resolve_stops(40.748, float("-inf"))
        with self.assertRaises(ValueError):
            self.provider.resolve_stops(95.0, -74.030)
        with self.assertRaises(ValueError):
            self.provider.resolve_stops(-95.0, -74.030)
        with self.assertRaises(ValueError):
            self.provider.resolve_stops(40.748, 190.0)
        with self.assertRaises(ValueError):
            self.provider.resolve_stops(40.748, -190.0)
        with self.assertRaises(ValueError):
            self.provider.resolve_stops(True, -74.030)  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            self.provider.resolve_stops(40.748, False)  # type: ignore[arg-type]

    def test_unsupported_route_raises_value_error(self) -> None:
        """Hoboken126Provider raises ValueError when route is not 126."""
        with self.assertRaises(ValueError):
            self.provider.resolve_stops(40.7484, -74.0302, route="85")
        with self.assertRaises(ValueError):
            self.provider.resolve_stops(40.7484, -74.0302, route="M15")


class TestTransitProviderRegistryAndFactory(unittest.TestCase):
    """Verifies TransitStopProvider ABC, factory resolution, and registry extensibility."""

    def test_abc_cannot_be_instantiated(self) -> None:
        """TransitStopProvider is abstract and cannot be directly instantiated."""
        with self.assertRaises(TypeError):
            TransitStopProvider()  # type: ignore[abstract]

    def test_incomplete_subclass_cannot_be_instantiated(self) -> None:
        """Subclass missing resolve_stops cannot be instantiated."""

        class IncompleteProvider(TransitStopProvider):
            pass

        with self.assertRaises(TypeError):
            IncompleteProvider()  # type: ignore[abstract]

    def test_get_transit_provider_defaults(self) -> None:
        """get_transit_provider with defaults returns Hoboken126Provider."""
        provider = get_transit_provider()
        self.assertIsInstance(provider, Hoboken126Provider)

    def test_get_transit_provider_case_insensitive_and_aliases(self) -> None:
        """get_transit_provider normalizes city name and route case/formatting."""
        p1 = get_transit_provider("hoboken", "126")
        p2 = get_transit_provider("HOBOKEN", "126")
        p3 = get_transit_provider("Hoboken, NJ", "126")
        p4 = get_transit_provider("  Hoboken, New Jersey  ", " 126 ")
        self.assertIsInstance(p1, Hoboken126Provider)
        self.assertIsInstance(p2, Hoboken126Provider)
        self.assertIsInstance(p3, Hoboken126Provider)
        self.assertIsInstance(p4, Hoboken126Provider)

    def test_get_transit_provider_unsupported_raises_value_error(self) -> None:
        """Unknown city or route raises ValueError."""
        with self.assertRaises(ValueError):
            get_transit_provider("Jersey City", "80")
        with self.assertRaises(ValueError):
            get_transit_provider("San Francisco", "126")
        with self.assertRaises(ValueError):
            get_transit_provider("Hoboken", "85")

    def test_registry_registration_and_decorator(self) -> None:
        """Providers can be registered via function or decorator and resolved."""
        registry = TransitProviderRegistry()

        class MockJCProvider(TransitStopProvider):
            def resolve_stops(
                self,
                latitude: float,
                longitude: float,
                route: str = "80",
                overrides: list[Any] | None = None,
                fallback_to_default: bool = False,
            ) -> list[dict[str, Any]]:
                return [{"id": "jc-1", "name": "Journal Square"}]

        # Direct function registration
        registry.register("Jersey City", "80", MockJCProvider)
        resolved = registry.get("Jersey City", "80")
        self.assertIsInstance(resolved, MockJCProvider)
        self.assertEqual(
            resolved.resolve_stops(40.73, -74.06)[0]["name"], "Journal Square"
        )

        # Global decorator registration
        @register_transit_provider("New York", "M15")
        class MockNYCProvider(TransitStopProvider):
            def resolve_stops(
                self,
                latitude: float,
                longitude: float,
                route: str = "M15",
                overrides: list[Any] | None = None,
                fallback_to_default: bool = False,
            ) -> list[dict[str, Any]]:
                return [{"id": "m15-1", "name": "1st Ave & 14th St"}]

        nyc_prov = get_transit_provider("New York", "M15")
        self.assertIsInstance(nyc_prov, MockNYCProvider)
        self.assertEqual(
            nyc_prov.resolve_stops(40.73, -73.98)[0]["name"],
            "1st Ave & 14th St",
        )

    def test_abc_pass_coverage(self) -> None:
        """Invoking super().resolve_stops executes the ABC method body."""

        class SubProvider(TransitStopProvider):
            def resolve_stops(
                self,
                latitude: float,
                longitude: float,
                route: str = "126",
                overrides: list[Any] | None = None,
                fallback_to_default: bool = False,
            ) -> list[dict[str, Any]]:
                super().resolve_stops(
                    latitude, longitude, route, overrides, fallback_to_default
                )
                return []

        p = SubProvider()
        self.assertEqual(p.resolve_stops(40.74, -74.03), [])

    def test_global_register_direct_instance(self) -> None:
        """Registering a direct instance returns the same instance on lookup."""

        class DirectProvider(TransitStopProvider):
            def resolve_stops(
                self,
                latitude: float,
                longitude: float,
                route: str = "126",
                overrides: list[Any] | None = None,
                fallback_to_default: bool = False,
            ) -> list[dict[str, Any]]:
                return [{"id": "direct-1"}]

        inst = DirectProvider()
        res = register_transit_provider("DirectCity", "50", inst)
        self.assertIs(res, inst)
        lookup = get_transit_provider("DirectCity", "50")
        self.assertIs(lookup, inst)


if __name__ == "__main__":
    unittest.main()
