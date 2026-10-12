"""Milestone 3 Adversarial Challenge Suite: Overrides Fuzzing, Error Injection & Concurrency Stress.

Adversarial empirical testing harness verifying:
1. Fuzzing stops_override across string IDs, integer IDs, partial dicts,
   custom IDs not in catalog, metadata enrichment, and coordinate precedence.
2. Adversarial error injection asserting clean ValueError rejection on empty IDs,
   missing keys, invalid types (None, booleans, floats), out-of-range walk_min/distance_m,
   and lists exceeding 16 items.
3. Concurrency stress across 25+ worker threads exercising mixed coordinates,
   overrides, and fallback flags with zero data races and zero thread crosstalk.
4. Provider registry concurrency, custom registration (functional and decorator),
   case-insensitive resolution, and unregistered provider rejection.
"""

from __future__ import annotations

import os
import sys
import threading
import unittest
from typing import Any

# Ensure server module is on sys.path
_SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "server"))
if _SERVER_DIR not in sys.path:
    sys.path.insert(0, _SERVER_DIR)

from transit_catalog import (  # noqa: E402
    CORRIDOR_WASHINGTON,
    HOBOKEN_126_STOPS,
)
from transit_provider import (  # noqa: E402
    Hoboken126Provider,
    TransitProviderRegistry,
    TransitStopProvider,
    get_transit_provider,
    register_transit_provider,
)


class TestFuzzStopsOverride(unittest.TestCase):
    """Adversarial fuzzing and precedence verification for stops_override."""

    def setUp(self) -> None:
        self.provider = Hoboken126Provider()
        self.default_lat = 40.7371
        self.default_lon = -74.0305

    def test_fuzz_canonical_and_alias_string_ids(self) -> None:
        """String IDs resolve canonical catalog stops and map alias IDs accurately."""
        # Canonical Washington stop
        res_wash = self.provider.resolve_stops(
            self.default_lat, self.default_lon, overrides=["20512"]
        )
        self.assertEqual(len(res_wash), 1)
        self.assertEqual(res_wash[0]["id"], "20512")
        self.assertEqual(res_wash[0]["name"], "Washington & 9th")
        self.assertEqual(res_wash[0]["corridor"], CORRIDOR_WASHINGTON)
        self.assertEqual(res_wash[0]["line"], "126")
        self.assertEqual(res_wash[0]["direction"], "inbound")
        self.assertGreater(res_wash[0]["distance_m"], 0)
        self.assertGreater(res_wash[0]["walk_min"], 0)

        # Alias stop: 20516 maps to 20508 (Washington & 1st)
        res_alias = self.provider.resolve_stops(
            self.default_lat, self.default_lon, overrides=["20516"]
        )
        self.assertEqual(len(res_alias), 1)
        self.assertEqual(res_alias[0]["id"], "20508")
        self.assertEqual(res_alias[0]["name"], "Washington & 1st")

        # Whitespace padded ID string
        res_ws = self.provider.resolve_stops(
            self.default_lat, self.default_lon, overrides=["  20494  "]
        )
        self.assertEqual(len(res_ws), 1)
        self.assertEqual(res_ws[0]["id"], "20494")
        self.assertEqual(res_ws[0]["name"], "Clinton & 9th")

    def test_fuzz_integer_ids_and_stringification(self) -> None:
        """Integer IDs must resolve correctly and always output stringified IDs."""
        res_int = self.provider.resolve_stops(
            self.default_lat, self.default_lon, overrides=[20512, 20494]
        )
        self.assertEqual(len(res_int), 2)
        self.assertEqual(res_int[0]["id"], "20512")
        self.assertIsInstance(res_int[0]["id"], str)
        self.assertEqual(res_int[0]["name"], "Washington & 9th")
        self.assertEqual(res_int[1]["id"], "20494")
        self.assertIsInstance(res_int[1]["id"], str)
        self.assertEqual(res_int[1]["name"], "Clinton & 9th")

        # Int alias 20498 maps to 20491 (Clinton & 1st)
        res_alias_int = self.provider.resolve_stops(
            self.default_lat, self.default_lon, overrides=[20498]
        )
        self.assertEqual(res_alias_int[0]["id"], "20491")

        # Custom int ID
        res_custom_int = self.provider.resolve_stops(
            self.default_lat, self.default_lon, overrides=[99999]
        )
        self.assertEqual(res_custom_int[0]["id"], "99999")
        self.assertEqual(res_custom_int[0]["name"], "Stop #99999")
        self.assertEqual(res_custom_int[0]["corridor"], "custom")

    def test_fuzz_dicts_with_partial_fields(self) -> None:
        """Dicts with minimal or partial fields enrich missing metadata from catalog."""
        # Dict with only 'id'
        res_minimal = self.provider.resolve_stops(
            self.default_lat, self.default_lon, overrides=[{"id": "20512"}]
        )
        self.assertEqual(len(res_minimal), 1)
        stop = res_minimal[0]
        self.assertEqual(stop["id"], "20512")
        self.assertEqual(stop["name"], "Washington & 9th")
        self.assertEqual(stop["subtitle"], "Stop #20512 • via Lincoln Tunnel")
        self.assertEqual(stop["line"], "126")
        self.assertEqual(stop["direction"], "inbound")
        self.assertEqual(stop["corridor"], CORRIDOR_WASHINGTON)
        self.assertEqual(stop["lat"], 40.74780)
        self.assertEqual(stop["lon"], -74.02800)
        self.assertIsInstance(stop["walk_min"], int)
        self.assertIsInstance(stop["distance_m"], int)

        # Dict with custom name and walk_min, but catalog coordinates & corridor
        res_custom_walk = self.provider.resolve_stops(
            self.default_lat,
            self.default_lon,
            overrides=[{"id": "20512", "name": "Express 9th", "walk_min": 12}],
        )
        self.assertEqual(res_custom_walk[0]["name"], "Express 9th")
        self.assertEqual(res_custom_walk[0]["walk_min"], 12)
        # distance_m dynamically calculated because not provided
        self.assertGreater(res_custom_walk[0]["distance_m"], 0)
        self.assertEqual(res_custom_walk[0]["corridor"], CORRIDOR_WASHINGTON)
        self.assertEqual(res_custom_walk[0]["lat"], 40.74780)

        # Dict with explicit distance_m
        res_dist = self.provider.resolve_stops(
            self.default_lat,
            self.default_lon,
            overrides=[{"id": "20512", "distance_m": 750}],
        )
        self.assertEqual(res_dist[0]["distance_m"], 750)
        # walk_min dynamically calculated
        self.assertGreater(res_dist[0]["walk_min"], 0)

    def test_fuzz_custom_ids_not_in_catalog(self) -> None:
        """Custom stop IDs not in the catalog receive safe fallback properties."""
        res_custom = self.provider.resolve_stops(
            self.default_lat,
            self.default_lon,
            overrides=[
                "CUSTOM_UNKNOWN_STOP",
                {
                    "id": "CUSTOM_SPECIAL",
                    "name": "Hudson Yards Connector",
                    "walk_min": 8,
                    "distance_m": 600,
                    "lat": 40.7538,
                    "lon": -74.0022,
                },
            ],
        )
        self.assertEqual(len(res_custom), 2)

        # String custom stop
        c1 = res_custom[0]
        self.assertEqual(c1["id"], "CUSTOM_UNKNOWN_STOP")
        self.assertEqual(c1["name"], "Stop #CUSTOM_UNKNOWN_STOP")
        self.assertEqual(c1["subtitle"], "Stop #CUSTOM_UNKNOWN_STOP (custom)")
        self.assertEqual(c1["corridor"], "custom")
        self.assertEqual(c1["walk_min"], 5)
        self.assertEqual(c1["distance_m"], 400)
        self.assertNotIn("lat", c1)
        self.assertNotIn("lon", c1)

        # Dict custom stop with custom coordinates
        c2 = res_custom[1]
        self.assertEqual(c2["id"], "CUSTOM_SPECIAL")
        self.assertEqual(c2["name"], "Hudson Yards Connector")
        self.assertEqual(c2["walk_min"], 8)
        self.assertEqual(c2["distance_m"], 600)
        self.assertEqual(c2["lat"], 40.7538)
        self.assertEqual(c2["lon"], -74.0022)

    def test_fuzz_precedence_over_user_coordinates(self) -> None:
        """Overrides take absolute precedence over user proximity and bounding boxes."""
        # User is in South Hoboken (1st St), override asks for North Hoboken (14th St)
        south_lat, south_lon = 40.73710, -74.03050
        res = self.provider.resolve_stops(south_lat, south_lon, overrides=["20515"])
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["id"], "20515")
        self.assertEqual(res[0]["name"], "Washington & 14th")

        # User is outside Hoboken in Manhattan (Times Square: 40.7580, -73.9855)
        # Without overrides, returns []
        res_no_ov = self.provider.resolve_stops(40.7580, -73.9855)
        self.assertEqual(res_no_ov, [])

        # With overrides, returns requested stops despite out-of-bounds coordinates
        res_oob_ov = self.provider.resolve_stops(
            40.7580, -73.9855, overrides=["20512", "20494"]
        )
        self.assertEqual(len(res_oob_ov), 2)
        self.assertEqual([s["id"] for s in res_oob_ov], ["20512", "20494"])

    def test_fuzz_ordering_and_max_boundary_length(self) -> None:
        """Output strictly preserves input order up to maximum boundary of 16 stops."""
        # Reverse order from standard
        rev_ids = ["20494", "20512"]
        res_rev = self.provider.resolve_stops(
            self.default_lat, self.default_lon, overrides=rev_ids
        )
        self.assertEqual([s["id"] for s in res_rev], rev_ids)

        # Exactly 16 stops (valid boundary)
        sixteen_ids = [s.id for s in HOBOKEN_126_STOPS] + ["20512", "20494"]
        self.assertEqual(len(sixteen_ids), 16)
        res_16 = self.provider.resolve_stops(
            self.default_lat, self.default_lon, overrides=sixteen_ids
        )
        self.assertEqual(len(res_16), 16)
        self.assertEqual([s["id"] for s in res_16], sixteen_ids)


class TestAdversarialErrorInjection(unittest.TestCase):
    """Adversarial error injection asserting clean ValueError rejections."""

    def setUp(self) -> None:
        self.provider = Hoboken126Provider()
        self.lat = 40.7371
        self.lon = -74.0305

    def test_reject_empty_string_ids(self) -> None:
        """Empty string or whitespace-only stop IDs must raise clean ValueError."""
        for empty_val in ["", "   ", "\t", "\n"]:
            with self.assertRaises(ValueError):
                self.provider.resolve_stops(self.lat, self.lon, overrides=[empty_val])
            with self.assertRaises(ValueError):
                self.provider.resolve_stops(
                    self.lat, self.lon, overrides=[{"id": empty_val}]
                )

    def test_reject_missing_id_key(self) -> None:
        """Dict entries without 'id' key must raise clean ValueError."""
        invalid_dicts: list[dict[str, Any]] = [
            {},
            {"name": "No ID Stop"},
            {"walk_min": 5},
            {"distance_m": 400},
            {"corridor": "washington"},
        ]
        for d in invalid_dicts:
            with self.assertRaises(ValueError):
                self.provider.resolve_stops(self.lat, self.lon, overrides=[d])

    def test_reject_invalid_element_types(self) -> None:
        """None, booleans, floats, and objects in overrides list must raise ValueError."""
        invalid_items: list[Any] = [
            None,
            True,
            False,
            12.34,
            ["nested_list"],
            {"nested": "set"},
            object(),
        ]
        for item in invalid_items:
            with self.assertRaises(ValueError):
                self.provider.resolve_stops(self.lat, self.lon, overrides=[item])
            # Even when mixed with valid items
            with self.assertRaises(ValueError):
                self.provider.resolve_stops(
                    self.lat, self.lon, overrides=["20512", item]
                )

    def test_reject_invalid_override_container_types(self) -> None:
        """Passing non-list/non-tuple truthy containers must raise ValueError."""
        invalid_containers: list[Any] = [
            "20512",
            123,
            True,
            {"id": "20512"},
            {"20512", "20494"},
        ]
        for c in invalid_containers:
            with self.assertRaises(ValueError):
                self.provider.resolve_stops(self.lat, self.lon, overrides=c)

    def test_reject_walk_min_out_of_range(self) -> None:
        """walk_min < 0, > 180, or non-integer must raise ValueError."""
        invalid_walk_vals: list[Any] = [
            -1,
            -50,
            181,
            200,
            1000,
            True,
            False,
            3.5,
            "5",
        ]
        for w in invalid_walk_vals:
            with self.assertRaises(ValueError):
                self.provider.resolve_stops(
                    self.lat, self.lon, overrides=[{"id": "20512", "walk_min": w}]
                )

        # 0 must be accepted as valid walk time for adjacent/at-stop locations
        res_zero = self.provider.resolve_stops(
            self.lat, self.lon, overrides=[{"id": "20512", "walk_min": 0}]
        )
        self.assertEqual(res_zero[0]["walk_min"], 0)

    def test_reject_distance_m_out_of_range(self) -> None:
        """distance_m < 0, > 50000, or non-integer must raise ValueError."""
        invalid_dist_vals: list[Any] = [
            -1,
            -100,
            50001,
            60000,
            100000,
            True,
            False,
            250.5,
            "500",
        ]
        for d in invalid_dist_vals:
            with self.assertRaises(ValueError):
                self.provider.resolve_stops(
                    self.lat, self.lon, overrides=[{"id": "20512", "distance_m": d}]
                )

    def test_reject_list_length_exceeding_16(self) -> None:
        """Overrides list lengths > 16 must raise clean ValueError."""
        with self.assertRaises(ValueError):
            self.provider.resolve_stops(self.lat, self.lon, overrides=["20512"] * 17)

        with self.assertRaises(ValueError):
            self.provider.resolve_stops(self.lat, self.lon, overrides=["20512"] * 50)


class TestConcurrencyStress(unittest.TestCase):
    """High-concurrency stress test for Hoboken126Provider and resolve_stops."""

    def test_concurrent_resolve_stops_across_threads(self) -> None:
        """25+ concurrent worker threads executing resolve_stops produce deterministic results."""
        provider = Hoboken126Provider()
        num_threads = 25
        iterations_per_thread = 50
        barrier = threading.Barrier(num_threads)
        errors: list[str] = []

        def worker(tid: int) -> None:
            # Wait for all threads to start simultaneously
            barrier.wait()
            for i in range(iterations_per_thread):
                try:
                    mode = (tid + i) % 7
                    if mode == 0:
                        # Midtown Hoboken 9th St
                        stops = provider.resolve_stops(40.7478, -74.0280)
                        if [s["id"] for s in stops] != ["20512", "20494"]:
                            errors.append(
                                f"Thread {tid} mode 0 mismatch: {[s['id'] for s in stops]}"
                            )
                    elif mode == 1:
                        # South Hoboken 1st St
                        stops = provider.resolve_stops(40.73710, -74.03050)
                        if [s["id"] for s in stops] != ["20508", "20491"]:
                            errors.append(
                                f"Thread {tid} mode 1 mismatch: {[s['id'] for s in stops]}"
                            )
                    elif mode == 2:
                        # North Hoboken 14th St
                        stops = provider.resolve_stops(40.75460, -74.02650)
                        if [s["id"] for s in stops] != ["20515", "20495"]:
                            errors.append(
                                f"Thread {tid} mode 2 mismatch: {[s['id'] for s in stops]}"
                            )
                    elif mode == 3:
                        # Explicit string overrides
                        stops = provider.resolve_stops(
                            40.7371, -74.0305, overrides=["20510", "20492"]
                        )
                        if [s["id"] for s in stops] != ["20510", "20492"]:
                            errors.append(
                                f"Thread {tid} mode 3 mismatch: {[s['id'] for s in stops]}"
                            )
                    elif mode == 4:
                        # Thread-unique custom dict override
                        unique_id = f"STOP_{tid}_{i}"
                        stops = provider.resolve_stops(
                            40.7371,
                            -74.0305,
                            overrides=[
                                {
                                    "id": unique_id,
                                    "name": f"Stop {unique_id}",
                                    "walk_min": 7,
                                    "distance_m": 500,
                                }
                            ],
                        )
                        if (
                            len(stops) != 1
                            or stops[0]["id"] != unique_id
                            or stops[0]["walk_min"] != 7
                            or stops[0]["distance_m"] != 500
                        ):
                            errors.append(f"Thread {tid} mode 4 crosstalk: {stops}")
                    elif mode == 5:
                        # Out of bounds without fallback
                        stops = provider.resolve_stops(51.5074, -0.1278)
                        if stops != []:
                            errors.append(
                                f"Thread {tid} mode 5 out of bounds not empty: {stops}"
                            )
                    elif mode == 6:
                        # Out of bounds with fallback
                        stops = provider.resolve_stops(
                            51.5074, -0.1278, fallback_to_default=True
                        )
                        if [s["id"] for s in stops] != ["20512", "20494"]:
                            errors.append(
                                f"Thread {tid} mode 6 fallback mismatch: {[s['id'] for s in stops]}"
                            )
                except Exception as ex:
                    errors.append(f"Thread {tid} iter {i} crashed: {ex}")

        threads = [
            threading.Thread(target=worker, args=(t,)) for t in range(num_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(
            len(errors), 0, f"Concurrency errors encountered: {errors[:5]}"
        )


class TestProviderRegistryStress(unittest.TestCase):
    """Concurrency, custom registration, and normalization stress for TransitProviderRegistry."""

    def test_concurrent_registry_queries(self) -> None:
        """Concurrent queries to get_transit_provider produce valid provider instances."""
        num_threads = 25
        iterations = 40
        errors: list[str] = []

        def reader_worker(tid: int) -> None:
            for _ in range(iterations):
                try:
                    # Query with variations of case, whitespace, state
                    p1 = get_transit_provider("Hoboken", "126")
                    p2 = get_transit_provider("  hoboken, nj  ", "126")
                    p3 = get_transit_provider("HOBOKEN", " 126 ")

                    if not isinstance(p1, Hoboken126Provider):
                        errors.append(f"Thread {tid}: p1 unexpected type {type(p1)}")
                    if not isinstance(p2, Hoboken126Provider):
                        errors.append(f"Thread {tid}: p2 unexpected type {type(p2)}")
                    if not isinstance(p3, Hoboken126Provider):
                        errors.append(f"Thread {tid}: p3 unexpected type {type(p3)}")
                except Exception as ex:
                    errors.append(f"Thread {tid} query crashed: {ex}")

        threads = [
            threading.Thread(target=reader_worker, args=(t,))
            for t in range(num_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, f"Registry query errors: {errors[:5]}")

    def test_custom_provider_functional_and_decorator_registration(self) -> None:
        """Functional and decorator registration correctly bind custom providers."""
        reg = TransitProviderRegistry()

        class MockCityProvider(TransitStopProvider):
            def __init__(self, tag: str = "JC87") -> None:
                self.tag = tag

            def resolve_stops(
                self,
                latitude: float,
                longitude: float,
                route: str = "126",
                overrides: list[Any] | None = None,
                fallback_to_default: bool = False,
            ) -> list[dict[str, Any]]:
                return [{"id": self.tag, "name": f"Mock Stop {self.tag}"}]

        # Functional registration of an instance
        reg.register("Jersey City", "80", MockCityProvider("JC80"))
        jc_p = reg.get("jersey city", "80")
        jc_stops = jc_p.resolve_stops(40.72, -74.06)
        self.assertEqual(len(jc_stops), 1)
        self.assertEqual(jc_stops[0]["id"], "JC80")

        # Class registration
        reg.register("Jersey City", "87", MockCityProvider)
        jc87_p = reg.get("Jersey City, NJ", "87")
        self.assertIsInstance(jc87_p, MockCityProvider)

        # Global decorator registration
        @register_transit_provider("Newark", "62")
        class Newark62Provider(TransitStopProvider):
            def resolve_stops(
                self,
                latitude: float,
                longitude: float,
                route: str = "62",
                overrides: list[Any] | None = None,
                fallback_to_default: bool = False,
            ) -> list[dict[str, Any]]:
                return [{"id": "EWR_AIRPORT", "name": "Terminal B"}]

        nwk_p = get_transit_provider("newark", "62")
        nwk_stops = nwk_p.resolve_stops(40.6895, -74.1745)
        self.assertEqual(len(nwk_stops), 1)
        self.assertEqual(nwk_stops[0]["id"], "EWR_AIRPORT")

    def test_concurrent_dynamic_registrations_and_queries(self) -> None:
        """Concurrent registrations and queries do not race or corrupt registry."""
        reg = TransitProviderRegistry()
        num_threads = 20
        errors: list[str] = []

        class DynamicProvider(TransitStopProvider):
            def __init__(self, city_id: str) -> None:
                self.city_id = city_id

            def resolve_stops(
                self,
                latitude: float,
                longitude: float,
                route: str = "1",
                overrides: list[Any] | None = None,
                fallback_to_default: bool = False,
            ) -> list[dict[str, Any]]:
                return [{"id": f"STOP_{self.city_id}"}]

        def reg_worker(tid: int) -> None:
            try:
                city_name = f"Municipality_{tid}"
                route_name = f"Route_{tid}"
                # Register unique provider
                reg.register(city_name, route_name, DynamicProvider(f"TID_{tid}"))

                # Query it back with various normalizations
                resolved = reg.get(f"municipality_{tid}, state", f" route_{tid} ")
                res = resolved.resolve_stops(40.0, -74.0)
                if res[0]["id"] != f"STOP_TID_{tid}":
                    errors.append(f"Worker {tid} lookup mismatch: {res}")

                # Query default Hoboken to verify base registry remains intact
                hoboken_p = reg.get("hoboken", "126")
                h_stops = hoboken_p.resolve_stops(40.7371, -74.0305)
                if len(h_stops) != 2:
                    errors.append(f"Worker {tid} base hoboken broken: {len(h_stops)}")
            except Exception as ex:
                errors.append(f"Worker {tid} failed: {ex}")

        threads = [
            threading.Thread(target=reg_worker, args=(t,)) for t in range(num_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, f"Dynamic registry race errors: {errors[:5]}")

    def test_unregistered_city_route_raises_value_error(self) -> None:
        """Querying unregistered city or route raises clean ValueError."""
        with self.assertRaises(ValueError):
            get_transit_provider("Tokyo", "126")

        with self.assertRaises(ValueError):
            get_transit_provider("Hoboken", "999")


if __name__ == "__main__":
    unittest.main()
