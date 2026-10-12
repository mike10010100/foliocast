"""Unit tests for Citi Bike auto-discovery, 24-hour caching, pedestrian geometry, and station selection."""

from __future__ import annotations

import json
import math
import os
import shutil
import tempfile
import time
import unittest
from typing import Any
from unittest.mock import MagicMock, patch

from citibike import DEFAULT_STATIONS
from citibike_discovery import (
    DEFAULT_TTL_SECONDS,
    CitiBikeCatalog,
    atomic_write_json,
    calculate_walk_minutes,
    clean_station_name,
    compact_station,
    compute_bounding_box_deltas,
    discover_citibike_stations,
    extract_stations_from_doc,
    haversine_distance,
    is_cache_fresh,
    is_in_metro_area,
    pedestrian_distance,
    select_closest_stations,
)
from paths import resolve_data_dir


class TestDistanceAndPedestrianGeometry(unittest.TestCase):
    def test_haversine_identical_points(self) -> None:
        self.assertEqual(
            haversine_distance(40.7371, -74.0305, 40.7371, -74.0305),
            0.0,
        )

    def test_haversine_symmetry(self) -> None:
        p1 = (40.7371, -74.0305)
        p2 = (40.748161, -74.032453)
        d1 = haversine_distance(p1[0], p1[1], p2[0], p2[1])
        d2 = haversine_distance(p2[0], p2[1], p1[0], p1[1])
        self.assertAlmostEqual(d1, d2, places=6)

    def test_haversine_known_hoboken_distance(self) -> None:
        # Hoboken City Hall to Columbus Park
        dist = haversine_distance(40.7371, -74.0305, 40.748161, -74.032453)
        self.assertGreater(dist, 170.0)
        self.assertLess(dist, 210.0)

    def test_haversine_antipodal_points(self) -> None:
        # Distance between (0, 0) and (0, 180) is half circumference of Earth ~ 20,015,000 m
        dist = haversine_distance(0.0, 0.0, 0.0, 180.0)
        self.assertAlmostEqual(dist, math.pi * 6371000.0, delta=100.0)

    def test_pedestrian_circuity_multiplier(self) -> None:
        # 100m straight-line becomes 125m pedestrian distance
        with patch("citibike_discovery.haversine_distance", return_value=100.0):
            p_dist = pedestrian_distance(0.0, 0.0, 0.0, 1.0)
            self.assertEqual(p_dist, 125)

    def test_calculate_walk_minutes(self) -> None:
        # 0m -> 0 min
        self.assertEqual(calculate_walk_minutes(0), 0)
        self.assertEqual(calculate_walk_minutes(-10), 0)
        # Small distance -> at least 1 min
        self.assertEqual(calculate_walk_minutes(10), 1)
        self.assertEqual(calculate_walk_minutes(40), 1)
        # 80m -> 1 min
        self.assertEqual(calculate_walk_minutes(80), 1)
        # 125m -> round(125 / 80) = round(1.5625) = 2 min
        self.assertEqual(calculate_walk_minutes(125), 2)
        # 240m -> round(240 / 80) = 3 min
        self.assertEqual(calculate_walk_minutes(240), 3)
        # 440m -> round(440 / 80) = 6 min
        self.assertEqual(calculate_walk_minutes(440), 6)

    def test_hoboken_reference_stations_variance(self) -> None:
        user_lat, user_lon = 40.7371, -74.0305
        coords = {
            "fadf00cf-d84a-49e8-9607-c67154915412": (40.748161, -74.032453),
            "f417d8da-0f15-49b0-9e3c-3c3e55c2691d": (40.749985, -74.027150),
            "655b0878-c22b-4f8c-8675-21bf30d1eebf": (40.751867, -74.030377),
            "519824e4-69ba-4270-a395-17c204f328f8": (40.745984, -74.028199),
            "21c4a77d-b1ae-4262-b143-087fd14a07b8": (40.745420, -74.033320),
            "9d344652-976b-4c2d-bede-2ef19b0fbf13": (40.744398, -74.034501),
        }
        for st in DEFAULT_STATIONS:
            sid = st["id"]
            slat, slon = coords[sid]
            ped_m = pedestrian_distance(user_lat, user_lon, slat, slon)
            walk_min = calculate_walk_minutes(ped_m)
            # Calculated walk time must track human curated time within +/- 1 minute
            self.assertLessEqual(
                abs(walk_min - st["walk_min"]),
                1,
                f"Variance > 1 min for station {st['name']}",
            )


class TestBoundingBoxAndMetroRegion(unittest.TestCase):
    def test_bounding_box_deltas_scale(self) -> None:
        dlat15, dlon15 = compute_bounding_box_deltas(40.7484, 15)
        dlat30, dlon30 = compute_bounding_box_deltas(40.7484, 30)
        self.assertGreater(dlat30, dlat15)
        self.assertGreater(dlon30, dlon15)

    def test_is_in_metro_area(self) -> None:
        # In metro
        self.assertTrue(is_in_metro_area(40.7484, -74.0303))  # Hoboken
        self.assertTrue(is_in_metro_area(40.7195, -74.0431))  # Jersey City
        self.assertTrue(is_in_metro_area(40.7580, -73.9855))  # NYC Midtown
        # Out of metro
        self.assertFalse(is_in_metro_area(37.7749, -122.4194))  # San Francisco
        self.assertFalse(is_in_metro_area(47.6062, -122.3321))  # Seattle
        self.assertFalse(is_in_metro_area(51.5074, -0.1278))  # London
        self.assertFalse(is_in_metro_area(35.6762, 139.6503))  # Tokyo
        self.assertFalse(is_in_metro_area(40.3573, -74.6672))  # Princeton, NJ


class TestCleanStationName(unittest.TestCase):
    def test_default_stations_exact_reproduction(self) -> None:
        cases = [
            ("Columbus Park - Clinton St & 9 St", "Clinton & 9th"),
            ("11 St & Washington St", "Washington & 11th"),
            ("Willow Ave & 12 St", "Willow & 12th"),
            ("8 St & Washington St", "Washington & 8th"),
            ("Clinton St & 7 St", "Clinton & 7th"),
            ("6 St & Grand St", "Grand & 6th"),
        ]
        for raw, expected in cases:
            self.assertEqual(clean_station_name(raw), expected)

    def test_transit_hubs_and_landmarks(self) -> None:
        self.assertEqual(
            clean_station_name("Hoboken Terminal - Hudson St & Hudson Pl"),
            "Hoboken Terminal",
        )
        self.assertEqual(clean_station_name("Grove St PATH"), "Grove St PATH")
        self.assertEqual(clean_station_name("Journal Square"), "Journal Square")
        self.assertEqual(
            clean_station_name("14 St Ferry - 14 St & Shipyard Ln"),
            "Shipyard Ln & 14th",
        )
        self.assertEqual(
            clean_station_name("City Hall - Washington St & 1 St"),
            "Washington & 1st",
        )
        self.assertEqual(
            clean_station_name("Church Sq Park - 5 St & Park Ave"),
            "Park & 5th",
        )
        self.assertEqual(
            clean_station_name("Mama Johnson Field - 4 St & Jackson St"),
            "Jackson & 4th",
        )
        self.assertEqual(
            clean_station_name("9 St HBLR - Jackson St & 8 St"),
            "Jackson & 8th",
        )

    def test_numbered_ordinals_and_directions(self) -> None:
        self.assertEqual(clean_station_name("W 26 St & 10 Ave"), "W 26th & 10th")
        self.assertEqual(clean_station_name("2 Ave & 36 St"), "2nd & 36th")
        self.assertEqual(clean_station_name("Vesey St & Church St"), "Vesey & Church")
        self.assertEqual(clean_station_name("1 St & Washington St"), "Washington & 1st")
        self.assertEqual(clean_station_name("2 St & Washington St"), "Washington & 2nd")
        self.assertEqual(clean_station_name("3 St & Washington St"), "Washington & 3rd")

    def test_empty_and_edge_inputs(self) -> None:
        self.assertEqual(clean_station_name(""), "")
        self.assertEqual(clean_station_name("   "), "")
        self.assertEqual(clean_station_name(None), "")  # type: ignore[arg-type]
        self.assertEqual(clean_station_name("Clinton St &amp; 9 St"), "Clinton & 9th")


class TestStationDataProcessing(unittest.TestCase):
    def test_extract_stations_dual_schema(self) -> None:
        # Schema 1: compact
        doc1 = {"stations": [{"station_id": "1", "name": "Station 1"}]}
        self.assertEqual(extract_stations_from_doc(doc1), doc1["stations"])

        # Schema 2: raw GBFS
        doc2 = {"data": {"stations": [{"station_id": "2", "name": "Station 2"}]}}
        self.assertEqual(extract_stations_from_doc(doc2), doc2["data"]["stations"])

        # Invalid docs
        self.assertEqual(extract_stations_from_doc({}), [])
        self.assertEqual(extract_stations_from_doc(None), [])
        self.assertEqual(extract_stations_from_doc([]), [])

    def test_compact_station_validation(self) -> None:
        valid = {
            "station_id": "st-1",
            "name": "Station One",
            "short_name": "S1",
            "lat": 40.75,
            "lon": -74.03,
            "capacity": 20,
            "extra_field": "ignore_me",
        }
        compacted = compact_station(valid)
        self.assertIsNotNone(compacted)
        assert compacted is not None
        self.assertEqual(compacted["station_id"], "st-1")
        self.assertEqual(compacted["name"], "Station One")
        self.assertEqual(compacted["short_name"], "S1")
        self.assertEqual(compacted["lat"], 40.75)
        self.assertEqual(compacted["lon"], -74.03)
        self.assertEqual(compacted["capacity"], 20)
        self.assertNotIn("extra_field", compacted)

        # Invalid fields
        self.assertIsNone(compact_station({"station_id": "1"}))
        self.assertIsNone(
            compact_station(
                {"station_id": "1", "name": "N", "lat": "bad", "lon": -74.0}
            )
        )


class TestBundledOfflineSeed(unittest.TestCase):
    def test_seed_file_integrity(self) -> None:
        seed_path = os.path.join(resolve_data_dir(), "citibike_stations_seed.json")
        self.assertTrue(os.path.exists(seed_path), "Seed file must exist in data dir")

        with open(seed_path, "rb") as f:
            doc = json.loads(f.read().decode("utf-8"))

        stations = extract_stations_from_doc(doc)
        self.assertGreater(
            len(stations), 2000, "Seed must contain >2000 active stations"
        )

        # Confirm all 6 default station IDs are in seed
        seed_ids = {s["station_id"] for s in stations}
        for def_st in DEFAULT_STATIONS:
            self.assertIn(
                def_st["id"],
                seed_ids,
                f"Default station {def_st['name']} ({def_st['id']}) missing from seed!",
            )


class TestCitiBikeCatalogAndCaching(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp()
        self.cache_path = os.path.join(self.temp_dir, "citibike_stations.json")
        self.seed_path = os.path.join(self.temp_dir, "citibike_seed.json")

        self.sample_stations = [
            {
                "station_id": "test-1",
                "name": "Test & 1st",
                "short_name": "T1",
                "lat": 40.748,
                "lon": -74.030,
                "capacity": 20,
            },
            {
                "station_id": "test-2",
                "name": "Test & 2nd",
                "short_name": "T2",
                "lat": 40.750,
                "lon": -74.028,
                "capacity": 25,
            },
        ]
        with open(self.seed_path, "w", encoding="utf-8") as f:
            json.dump({"stations": self.sample_stations}, f)

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_atomic_write_json(self) -> None:
        test_file = os.path.join(self.temp_dir, "sub", "test.json")
        data = {"hello": "world"}
        success = atomic_write_json(test_file, data)
        self.assertTrue(success)
        self.assertTrue(os.path.exists(test_file))

        with open(test_file, "rb") as f:
            read_back = json.loads(f.read().decode("utf-8"))
        self.assertEqual(read_back, data)

    def test_atomic_write_handles_permission_error(self) -> None:
        with patch("builtins.open", side_effect=PermissionError("read-only")):
            test_file = os.path.join(self.temp_dir, "perm_test.json")
            success = atomic_write_json(test_file, {"a": 1})
            self.assertFalse(success)

    def test_is_cache_fresh(self) -> None:
        # Non-existent
        self.assertFalse(is_cache_fresh("/nonexistent/file.json", 86400))

        # Fresh file
        now = time.time()
        with open(self.cache_path, "w") as f:
            f.write("{}")
        os.utime(self.cache_path, (now, now))
        self.assertTrue(is_cache_fresh(self.cache_path, 86400))

        # Expired file (25h old)
        old_time = now - 90000
        os.utime(self.cache_path, (old_time, old_time))
        self.assertFalse(is_cache_fresh(self.cache_path, 86400))

    def test_catalog_loads_from_fresh_disk_cache(self) -> None:
        cached_data = {
            "version": 1,
            "last_updated": int(time.time()),
            "ttl": DEFAULT_TTL_SECONDS,
            "stations": [
                {
                    "station_id": "cached-1",
                    "name": "Cached Station",
                    "short_name": "CS1",
                    "lat": 40.748,
                    "lon": -74.030,
                    "capacity": 15,
                }
            ],
        }
        with open(self.cache_path, "w") as f:
            json.dump(cached_data, f)

        catalog = CitiBikeCatalog(cache_path=self.cache_path, seed_path=self.seed_path)
        with patch("urllib.request.urlopen") as mock_url:
            stations = catalog.get_stations(force_refresh=False)
            mock_url.assert_not_called()
            self.assertEqual(len(stations), 1)
            self.assertEqual(stations[0]["station_id"], "cached-1")

    def test_catalog_memory_caching(self) -> None:
        catalog = CitiBikeCatalog(cache_path=self.cache_path, seed_path=self.seed_path)
        with patch("urllib.request.urlopen", side_effect=Exception("network down")):
            # First call falls back to seed
            s1 = catalog.get_stations()
            self.assertEqual(len(s1), 2)

            # Overwrite seed file
            with open(self.seed_path, "w") as f:
                f.write('{"stations": []}')

            # Second call returns in-memory cached stations
            s2 = catalog.get_stations()
            self.assertEqual(len(s2), 2)
            self.assertIs(s1, s2)

            # After invalidating memory cache, reload occurs
            catalog.invalidate_memory_cache()
            # Seed is now empty, so emergency fallback returns DEFAULT_STATIONS
            s3 = catalog.get_stations()
            self.assertEqual(len(s3), len(DEFAULT_STATIONS))

    def test_catalog_live_fetch_success(self) -> None:
        fake_upstream = {
            "last_updated": 1728670000,
            "data": {
                "stations": [
                    {
                        "station_id": "live-1",
                        "name": "Live Station",
                        "short_name": "L1",
                        "lat": 40.749,
                        "lon": -74.031,
                        "capacity": 30,
                    }
                ]
            },
        }
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(fake_upstream).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp

        catalog = CitiBikeCatalog(cache_path=self.cache_path, seed_path=self.seed_path)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            stations = catalog.get_stations(force_refresh=True)
            self.assertEqual(len(stations), 1)
            self.assertEqual(stations[0]["station_id"], "live-1")
            # Verify cache was written to disk
            self.assertTrue(os.path.exists(self.cache_path))

    def test_catalog_fallback_to_stale_cache_on_network_error(self) -> None:
        stale_data = {
            "version": 1,
            "stations": [
                {
                    "station_id": "stale-1",
                    "name": "Stale Station",
                    "lat": 40.748,
                    "lon": -74.030,
                    "capacity": 10,
                }
            ],
        }
        with open(self.cache_path, "w") as f:
            json.dump(stale_data, f)
        # Mark cache as 30 hours old
        old_time = time.time() - 30 * 3600
        os.utime(self.cache_path, (old_time, old_time))

        catalog = CitiBikeCatalog(cache_path=self.cache_path, seed_path=self.seed_path)
        with patch("urllib.request.urlopen", side_effect=Exception("Network down")):
            stations = catalog.get_stations(force_refresh=False)
            self.assertEqual(len(stations), 1)
            self.assertEqual(stations[0]["station_id"], "stale-1")

    def test_catalog_fallback_to_seed_when_no_cache_and_network_fails(
        self,
    ) -> None:
        # cache_path does not exist
        catalog = CitiBikeCatalog(cache_path=self.cache_path, seed_path=self.seed_path)
        with patch("urllib.request.urlopen", side_effect=Exception("Network down")):
            stations = catalog.get_stations(force_refresh=False)
            self.assertEqual(len(stations), 2)
            self.assertEqual(stations[0]["station_id"], "test-1")

    def test_catalog_corrupt_cache_recovery(self) -> None:
        # Write corrupted JSON to cache file
        with open(self.cache_path, "w") as f:
            f.write("{corrupt json content")

        catalog = CitiBikeCatalog(cache_path=self.cache_path, seed_path=self.seed_path)
        with patch("urllib.request.urlopen", side_effect=Exception("Network down")):
            stations = catalog.get_stations(force_refresh=False)
            # Recovers via seed
            self.assertEqual(len(stations), 2)
            self.assertEqual(stations[0]["station_id"], "test-1")

    def test_catalog_emergency_fallback_when_seed_missing(self) -> None:
        # No cache, no seed, no network
        catalog = CitiBikeCatalog(
            cache_path=self.cache_path,
            seed_path=os.path.join(self.temp_dir, "missing_seed.json"),
        )
        with patch("urllib.request.urlopen", side_effect=Exception("Network down")):
            stations = catalog.get_stations(force_refresh=False)
            self.assertEqual(len(stations), len(DEFAULT_STATIONS))
            ids = {s["station_id"] for s in stations}
            self.assertIn("fadf00cf-d84a-49e8-9607-c67154915412", ids)


class TestStationSelectionAndAutoDiscovery(unittest.TestCase):
    def test_select_closest_stations_ordering(self) -> None:
        user_lat, user_lon = 40.7371, -74.0305
        raw = [
            {
                "station_id": "far",
                "name": "Far Station",
                "lat": 40.755,
                "lon": -74.030,
            },
            {
                "station_id": "close",
                "name": "Close Station",
                "lat": 40.7485,
                "lon": -74.0305,
            },
            {
                "station_id": "mid",
                "name": "Mid Station",
                "lat": 40.750,
                "lon": -74.030,
            },
        ]
        selected = select_closest_stations(
            raw, user_lat, user_lon, max_walk_minutes=15, max_stations=2
        )
        self.assertEqual(len(selected), 2)
        self.assertEqual(selected[0]["id"], "close")
        self.assertEqual(selected[1]["id"], "mid")
        self.assertLessEqual(selected[0]["distance_m"], selected[1]["distance_m"])

    def test_discover_hoboken_at_919_park_ave(self) -> None:
        # Uses real bundled seed file
        stations = discover_citibike_stations(
            40.7371, -74.0305, max_stations=6, max_walk_minutes=15
        )
        self.assertEqual(len(stations), 6)
        # Clinton & 9th must be first (closest, ~230m)
        self.assertEqual(stations[0]["name"], "Clinton & 9th")
        self.assertEqual(stations[0]["walk_min"], 3)

        # Distances must be sorted ascending
        for i in range(len(stations) - 1):
            self.assertLessEqual(
                stations[i]["distance_m"], stations[i + 1]["distance_m"]
            )

    def test_discover_out_of_coverage_returns_empty(self) -> None:
        # San Francisco
        self.assertEqual(discover_citibike_stations(37.7749, -122.4194), [])
        # Seattle
        self.assertEqual(discover_citibike_stations(47.6062, -122.3321), [])
        # London
        self.assertEqual(discover_citibike_stations(51.5074, -0.1278), [])

    def test_discover_micromobility_disabled_returns_empty(self) -> None:
        stations = discover_citibike_stations(
            40.7371, -74.0305, enable_micromobility=False
        )
        self.assertEqual(stations, [])

    def test_discover_max_walk_minutes_filtering(self) -> None:
        # At 3 minutes walk threshold, only Clinton & 9th should qualify
        stations = discover_citibike_stations(
            40.7371, -74.0305, max_walk_minutes=3
        )
        self.assertEqual(len(stations), 1)
        self.assertEqual(stations[0]["name"], "Clinton & 9th")

    def test_discover_max_stations_cap(self) -> None:
        stations = discover_citibike_stations(40.7371, -74.0305, max_stations=2)
        self.assertEqual(len(stations), 2)

    def test_discover_zero_stations_or_minutes(self) -> None:
        self.assertEqual(
            discover_citibike_stations(40.7371, -74.0305, max_stations=0),
            [],
        )
        self.assertEqual(
            discover_citibike_stations(40.7371, -74.0305, max_walk_minutes=0),
            [],
        )

    def test_discover_invalid_latitude_raises_error(self) -> None:
        with self.assertRaises(ValueError):
            discover_citibike_stations(95.0, -74.03)
        with self.assertRaises(ValueError):
            discover_citibike_stations(-95.0, -74.03)
        with self.assertRaises(ValueError):
            discover_citibike_stations(float("nan"), -74.03)

    def test_discover_invalid_longitude_raises_error(self) -> None:
        with self.assertRaises(ValueError):
            discover_citibike_stations(40.74, 200.0)
        with self.assertRaises(ValueError):
            discover_citibike_stations(40.74, -200.0)
        with self.assertRaises(ValueError):
            discover_citibike_stations(40.74, float("inf"))

    def test_discover_with_custom_catalog(self) -> None:
        custom_catalog = MagicMock()
        custom_catalog.get_stations.return_value = [
            {
                "station_id": "c1",
                "name": "Custom & 1st",
                "lat": 40.7484,
                "lon": -74.0302,
                "capacity": 10,
            }
        ]
        stations = discover_citibike_stations(
            40.7371, -74.0305, catalog=custom_catalog
        )
        self.assertEqual(len(stations), 1)
        self.assertEqual(stations[0]["id"], "c1")
        custom_catalog.get_stations.assert_called_once_with(force_refresh=False)

    def test_discover_with_custom_paths(self) -> None:
        temp_dir = tempfile.mkdtemp()
        try:
            cache_file = os.path.join(temp_dir, "cache.json")
            seed_file = os.path.join(temp_dir, "seed.json")
            with open(seed_file, "w") as f:
                json.dump(
                    {
                        "stations": [
                            {
                                "station_id": "p1",
                                "name": "Path & 1st",
                                "lat": 40.7484,
                                "lon": -74.0302,
                                "capacity": 10,
                            }
                        ]
                    },
                    f,
                )
            with patch("urllib.request.urlopen", side_effect=Exception("offline")):
                stations = discover_citibike_stations(
                    40.7371,
                    -74.0305,
                    cache_path=cache_file,
                    seed_path=seed_file,
                )
                self.assertEqual(len(stations), 1)
                self.assertEqual(stations[0]["id"], "p1")
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_clean_station_name_additional_branches(self) -> None:
        # Landmark with no & on right side
        self.assertEqual(
            clean_station_name("Pier 40 - Hudson River Park"),
            "Hudson River Park",
        )
        # Left side has & but right side does not
        self.assertEqual(
            clean_station_name("11 St & Washington St - North Dock"),
            "Washington & 11th",
        )
        # Missing one leg
        self.assertEqual(clean_station_name(" & Washington St"), "Washington")
        self.assertEqual(clean_station_name("Washington St & "), "Washington")
        self.assertEqual(clean_station_name(" & "), "")

    def test_select_closest_stations_edge_cases(self) -> None:
        user_lat, user_lon = 40.7371, -74.0305
        # Missing lat/lon
        raw_missing = [{"station_id": "m1", "name": "Missing coords"}]
        self.assertEqual(select_closest_stations(raw_missing, user_lat, user_lon), [])
        # Invalid numeric lat/lon
        raw_invalid = [
            {"station_id": "i1", "name": "Bad", "lat": "invalid", "lon": -74.0}
        ]
        self.assertEqual(select_closest_stations(raw_invalid, user_lat, user_lon), [])
        # All stations out of walk threshold
        raw_far = [{"station_id": "f1", "name": "Far", "lat": 40.71, "lon": -74.04}]
        self.assertEqual(
            select_closest_stations(raw_far, user_lat, user_lon, max_walk_minutes=1),
            [],
        )
        # Empty input list
        self.assertEqual(select_closest_stations([], user_lat, user_lon), [])
        # User out of metro
        self.assertEqual(select_closest_stations(raw_far, 0.0, 0.0), [])

    def test_atomic_write_json_error_handling(self) -> None:
        # os.makedirs fails
        with patch("os.makedirs", side_effect=OSError("dir creation failed")):
            self.assertFalse(atomic_write_json("/tmp/test/path.json", {"a": 1}))

        # os.replace fails
        temp_dir = tempfile.mkdtemp()
        try:
            target = os.path.join(temp_dir, "test.json")
            with patch("os.replace", side_effect=OSError("rename failed")):
                self.assertFalse(atomic_write_json(target, {"a": 1}))
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_catalog_fetch_live_empty_and_invalid_data(self) -> None:
        temp_dir = tempfile.mkdtemp()
        try:
            cache_file = os.path.join(temp_dir, "cache.json")
            seed_file = os.path.join(temp_dir, "seed.json")
            catalog = CitiBikeCatalog(cache_path=cache_file, seed_path=seed_file)

            # Upstream returns empty stations list
            resp_empty = MagicMock()
            resp_empty.read.return_value = json.dumps(
                {"data": {"stations": []}}
            ).encode("utf-8")
            resp_empty.__enter__.return_value = resp_empty

            with patch("urllib.request.urlopen", return_value=resp_empty):
                # Falls back to emergency defaults
                stations = catalog.get_stations(force_refresh=True)
                self.assertEqual(len(stations), len(DEFAULT_STATIONS))

            catalog.invalidate_memory_cache()

            # Upstream returns stations with missing required fields
            resp_bad = MagicMock()
            resp_bad.read.return_value = json.dumps(
                {"data": {"stations": [{"bad": "data"}]}}
            ).encode("utf-8")
            resp_bad.__enter__.return_value = resp_bad

            with patch("urllib.request.urlopen", return_value=resp_bad):
                stations = catalog.get_stations(force_refresh=True)
                self.assertEqual(len(stations), len(DEFAULT_STATIONS))
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_catalog_stale_cache_os_stat_error(self) -> None:
        temp_dir = tempfile.mkdtemp()
        try:
            cache_file = os.path.join(temp_dir, "cache.json")
            with open(cache_file, "w") as f:
                json.dump(
                    {
                        "stations": [
                            {
                                "station_id": "s1",
                                "name": "S1",
                                "lat": 40.75,
                                "lon": -74.03,
                            }
                        ]
                    },
                    f,
                )
            # Make cache stale
            old_time = time.time() - 100000
            os.utime(cache_file, (old_time, old_time))

            catalog = CitiBikeCatalog(cache_path=cache_file)
            real_stat = os.stat
            cache_calls = 0

            def counting_stat(path: str, *args: Any, **kwargs: Any) -> Any:
                nonlocal cache_calls
                if os.path.abspath(path) == os.path.abspath(cache_file):
                    cache_calls += 1
                    if cache_calls == 4:
                        raise OSError("stat age error")
                return real_stat(path, *args, **kwargs)

            with patch("urllib.request.urlopen", side_effect=Exception("network down")):
                with patch("os.stat", side_effect=counting_stat):
                    stations = catalog.get_stations(force_refresh=False)
                    self.assertEqual(len(stations), 1)
                    self.assertEqual(stations[0]["station_id"], "s1")
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
