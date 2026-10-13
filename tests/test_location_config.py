"""Unit tests for LocationConfig, validation, store, paths, and environment layering."""

import errno
import glob
import json
import os
import tempfile
import threading
import unittest
from dataclasses import FrozenInstanceError
from unittest.mock import patch

import location as loc
from paths import (
    resolve_config_dir,
    resolve_data_dir,
    resolve_location_config_path,
)


class TestLocationConfigDataclass(unittest.TestCase):
    def test_default_values_match_hoboken(self):
        cfg = loc.default_location_config()
        self.assertAlmostEqual(cfg.latitude, 40.7371)
        self.assertAlmostEqual(cfg.longitude, -74.0305)
        self.assertEqual(cfg.location_name, "Hoboken City Hall")
        self.assertEqual(cfg.address, "94 Washington St")
        self.assertEqual(cfg.city, "Hoboken")
        self.assertEqual(cfg.state, "NJ")
        self.assertEqual(cfg.route, "126")
        self.assertEqual(cfg.destination, "NYC PORT AUTHORITY")
        self.assertTrue(cfg.enable_micromobility)
        self.assertEqual(cfg.max_walk_minutes, 15)
        self.assertEqual(cfg.citibike_max_stations, 6)
        self.assertIsNone(cfg.stops_override)
        self.assertEqual(cfg.version, 1)

    def test_property_aliases(self):
        cfg = loc.default_location_config()
        self.assertEqual(cfg.name, cfg.location_name)
        self.assertEqual(cfg.citibike_enabled, cfg.enable_micromobility)

    def test_immutability_frozen(self):
        cfg = loc.default_location_config()
        with self.assertRaises(FrozenInstanceError):
            cfg.latitude = 41.0  # type: ignore[misc]

    def test_to_dict_serialization(self):
        cfg = loc.default_location_config()
        d = cfg.to_dict()
        self.assertEqual(d["version"], 1)
        self.assertAlmostEqual(d["latitude"], 40.7371)
        self.assertEqual(d["name"], "Hoboken City Hall")
        self.assertEqual(d["location_name"], "Hoboken City Hall")
        self.assertTrue(d["citibike_enabled"])
        self.assertTrue(d["enable_micromobility"])
        self.assertIsNone(d["stops_override"])

    def test_from_dict_deserialization(self):
        doc = {
            "latitude": 40.7128,
            "longitude": -74.0060,
            "location_name": "New York City",
        }
        cfg = loc.LocationConfig.from_dict(doc)
        self.assertAlmostEqual(cfg.latitude, 40.7128)
        self.assertAlmostEqual(cfg.longitude, -74.0060)
        self.assertEqual(cfg.location_name, "New York City")


class TestLocationValidationAndParsing(unittest.TestCase):
    def test_parse_minimal_empty_dict(self):
        cfg = loc.parse_location_config({})
        self.assertEqual(cfg, loc.default_location_config())

    def test_parse_aliases_in_json(self):
        doc = {
            "name": "Midtown East",
            "citibike_enabled": False,
        }
        cfg = loc.parse_location_config(doc)
        self.assertEqual(cfg.location_name, "Midtown East")
        self.assertEqual(cfg.name, "Midtown East")
        self.assertFalse(cfg.enable_micromobility)
        self.assertFalse(cfg.citibike_enabled)

    def test_reject_non_dict_payload(self):
        for invalid in ([], 123, "string", None):
            with self.assertRaises(loc.LocationConfigError):
                loc.parse_location_config(invalid)

    def test_reject_unknown_keys(self):
        with self.assertRaisesRegex(loc.LocationConfigError, "unknown key"):
            loc.parse_location_config({"unrecognized_field": True})

    def test_reject_invalid_version(self):
        with self.assertRaises(loc.LocationConfigError):
            loc.parse_location_config({"version": 2})
        with self.assertRaises(loc.LocationConfigError):
            loc.parse_location_config({"version": True})

    def test_latitude_bounds(self):
        # Valid boundaries
        self.assertEqual(loc.parse_location_config({"latitude": 90.0}).latitude, 90.0)
        self.assertEqual(loc.parse_location_config({"latitude": -90.0}).latitude, -90.0)
        self.assertEqual(loc.parse_location_config({"latitude": 0}).latitude, 0.0)

        # Invalid boundaries
        for inv in (
            90.0001,
            -90.0001,
            100,
            -100,
            float("nan"),
            float("inf"),
            "40.0",
            True,
        ):
            with self.assertRaises(loc.LocationConfigError):
                loc.parse_location_config({"latitude": inv})

    def test_longitude_bounds(self):
        # Valid boundaries
        self.assertEqual(
            loc.parse_location_config({"longitude": 180.0}).longitude, 180.0
        )
        self.assertEqual(
            loc.parse_location_config({"longitude": -180.0}).longitude, -180.0
        )
        self.assertEqual(loc.parse_location_config({"longitude": 0}).longitude, 0.0)

        # Invalid boundaries
        for inv in (
            180.0001,
            -180.0001,
            200,
            -200,
            float("nan"),
            float("inf"),
            "-74.0",
            True,
        ):
            with self.assertRaises(loc.LocationConfigError):
                loc.parse_location_config({"longitude": inv})

    def test_max_walk_minutes_bounds(self):
        self.assertEqual(
            loc.parse_location_config({"max_walk_minutes": 1}).max_walk_minutes, 1
        )
        self.assertEqual(
            loc.parse_location_config({"max_walk_minutes": 60}).max_walk_minutes, 60
        )

        for inv in (0, -1, -15, 181, 15.5, True, "15"):
            with self.assertRaises(loc.LocationConfigError):
                loc.parse_location_config({"max_walk_minutes": inv})

    def test_citibike_max_stations_bounds(self):
        self.assertEqual(
            loc.parse_location_config(
                {"citibike_max_stations": 0}
            ).citibike_max_stations,
            0,
        )
        self.assertEqual(
            loc.parse_location_config(
                {"citibike_max_stations": 20}
            ).citibike_max_stations,
            20,
        )

        for inv in (-1, 31, True, "6"):
            with self.assertRaises(loc.LocationConfigError):
                loc.parse_location_config({"citibike_max_stations": inv})

    def test_string_fields_validation(self):
        # Empty and whitespace
        for field in (
            "location_name",
            "address",
            "city",
            "state",
            "route",
            "destination",
        ):
            with self.assertRaises(loc.LocationConfigError):
                loc.parse_location_config({field: ""})
            with self.assertRaises(loc.LocationConfigError):
                loc.parse_location_config({field: "   "})
            with self.assertRaises(loc.LocationConfigError):
                loc.parse_location_config({field: 123})

        # Overlong string
        with self.assertRaises(loc.LocationConfigError):
            loc.parse_location_config({"location_name": "x" * 101})

        # Unprintable characters
        with self.assertRaises(loc.LocationConfigError):
            loc.parse_location_config({"city": "Hobo\x01ken"})

    def test_stops_override_strings_list(self):
        doc = {"stops_override": ["20512", "20494"]}
        cfg = loc.parse_location_config(doc)
        self.assertIsNotNone(cfg.stops_override)
        self.assertEqual(len(cfg.stops_override), 2)  # type: ignore[arg-type]
        self.assertEqual(cfg.stops_override[0]["id"], "20512")  # type: ignore[index]
        self.assertEqual(cfg.stops_override[1]["id"], "20494")  # type: ignore[index]

    def test_stops_override_dicts_list(self):
        doc = {
            "stops_override": [
                {
                    "id": "20512",
                    "name": "Washington & 9th",
                    "walk_min": 5,
                    "distance_m": 350,
                    "subtitle": "via Lincoln Tunnel",
                    "direction": "inbound",
                }
            ]
        }
        cfg = loc.parse_location_config(doc)
        self.assertIsNotNone(cfg.stops_override)
        self.assertEqual(cfg.stops_override[0]["name"], "Washington & 9th")  # type: ignore[index]
        self.assertEqual(cfg.stops_override[0]["walk_min"], 5)  # type: ignore[index]

    def test_stops_override_invalid_entries(self):
        with self.assertRaises(loc.LocationConfigError):
            loc.parse_location_config({"stops_override": "not-a-list"})
        with self.assertRaises(loc.LocationConfigError):
            loc.parse_location_config({"stops_override": [{}]})  # missing id
        with self.assertRaises(loc.LocationConfigError):
            loc.parse_location_config({"stops_override": [""]})  # empty id string
        with self.assertRaises(loc.LocationConfigError):
            loc.parse_location_config({"stops_override": [{"id": ""}]})
        with self.assertRaises(loc.LocationConfigError):
            loc.parse_location_config(
                {"stops_override": [f"{i}" for i in range(17)]}
            )  # > 16

    def test_parse_non_bool_micromobility(self):
        with self.assertRaises(loc.LocationConfigError):
            loc.parse_location_config({"enable_micromobility": "yes"})
        with self.assertRaises(loc.LocationConfigError):
            loc.parse_location_config({"citibike_enabled": 1})


class TestExampleLocationConfig(unittest.TestCase):
    def test_example_file_matches_defaults(self):
        path = os.path.join(
            os.path.dirname(__file__), "..", "config", "location.example.json"
        )
        self.assertTrue(os.path.exists(path), f"{path} must exist")
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
        cfg = loc.parse_location_config(doc)
        self.assertEqual(cfg, loc.default_location_config())


class TestEnvironmentOverrides(unittest.TestCase):
    def test_all_tracker_env_vars(self):
        env = {
            "TRACKER_LATITUDE": "40.7128",
            "TRACKER_LONGITUDE": "-74.0060",
            "TRACKER_LOCATION_NAME": "NYC Financial District",
            "TRACKER_ADDRESS": "100 Broadway",
            "TRACKER_CITY": "New York",
            "TRACKER_STATE": "NY",
            "TRACKER_ROUTE": "119",
            "TRACKER_DESTINATION": "HOBOKEN TERMINAL",
            "TRACKER_ENABLE_MICROMOBILITY": "false",
            "TRACKER_MAX_WALK_MINUTES": "25",
            "TRACKER_CITIBIKE_MAX_STATIONS": "10",
        }
        cfg, warnings = loc.apply_env_overrides(loc.default_location_config(), env)
        self.assertEqual(warnings, [])
        self.assertAlmostEqual(cfg.latitude, 40.7128)
        self.assertAlmostEqual(cfg.longitude, -74.0060)
        self.assertEqual(cfg.location_name, "NYC Financial District")
        self.assertEqual(cfg.address, "100 Broadway")
        self.assertEqual(cfg.city, "New York")
        self.assertEqual(cfg.state, "NY")
        self.assertEqual(cfg.route, "119")
        self.assertEqual(cfg.destination, "HOBOKEN TERMINAL")
        self.assertFalse(cfg.enable_micromobility)
        self.assertEqual(cfg.max_walk_minutes, 25)
        self.assertEqual(cfg.citibike_max_stations, 10)

    def test_invalid_env_vars_produce_warnings(self):
        env = {
            "TRACKER_LATITUDE": "invalid",
            "TRACKER_LONGITUDE": "999.0",
            "TRACKER_ENABLE_MICROMOBILITY": "not-a-boolean",
            "TRACKER_MAX_WALK_MINUTES": "-5",
            "TRACKER_CITIBIKE_MAX_STATIONS": "99",
        }
        cfg, warnings = loc.apply_env_overrides(loc.default_location_config(), env)
        self.assertEqual(len(warnings), 5)
        # Defaults should remain untouched
        self.assertAlmostEqual(cfg.latitude, loc.DEFAULT_LATITUDE)
        self.assertAlmostEqual(cfg.longitude, loc.DEFAULT_LONGITUDE)
        self.assertTrue(cfg.enable_micromobility)
        self.assertEqual(cfg.max_walk_minutes, loc.DEFAULT_MAX_WALK_MINUTES)
        self.assertEqual(cfg.citibike_max_stations, loc.DEFAULT_CITIBIKE_MAX_STATIONS)

    def test_empty_env_vars_ignored(self):
        env = {
            "TRACKER_LATITUDE": "   ",
            "TRACKER_LOCATION_NAME": "",
        }
        cfg, warnings = loc.apply_env_overrides(loc.default_location_config(), env)
        self.assertEqual(warnings, [])
        self.assertAlmostEqual(cfg.latitude, loc.DEFAULT_LATITUDE)
        self.assertEqual(cfg.location_name, loc.DEFAULT_LOCATION_NAME)


class TestLocationConfigStore(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.config_path = os.path.join(self.tmp_dir.name, "location.json")

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_store_initialization_defaults(self):
        logs = []
        store = loc.LocationConfigStore(path=self.config_path, env={}, log=logs.append)
        self.assertEqual(store.source, "built-in defaults")
        self.assertEqual(store.error, "")
        self.assertEqual(store.get(), loc.default_location_config())

    def test_store_loads_existing_file(self):
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump({"latitude": 40.7300, "longitude": -74.0400}, f)

        store = loc.LocationConfigStore(
            path=self.config_path, env={}, log=lambda *_: None
        )
        self.assertEqual(store.source, self.config_path)
        self.assertAlmostEqual(store.get().latitude, 40.7300)
        self.assertAlmostEqual(store.get().longitude, -74.0400)

    def test_store_hot_reload_on_mtime(self):
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump({"latitude": 40.7300}, f)

        store = loc.LocationConfigStore(
            path=self.config_path, env={}, log=lambda *_: None
        )
        self.assertAlmostEqual(store.get().latitude, 40.7300)

        # Update disk file
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump({"latitude": 40.7600}, f)
        st = os.stat(self.config_path)
        os.utime(self.config_path, ns=(st.st_atime_ns, st.st_mtime_ns + 10**9))

        self.assertAlmostEqual(store.get().latitude, 40.7600)

    def test_store_stat_caching(self):
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump({"latitude": 40.7300}, f)

        store = loc.LocationConfigStore(
            path=self.config_path, env={}, log=lambda *_: None
        )
        cfg1 = store.get()
        cfg2 = store.get()
        self.assertIs(cfg1, cfg2)

    def test_store_corrupt_file_keeps_last_good(self):
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump({"latitude": 40.7300}, f)

        store = loc.LocationConfigStore(
            path=self.config_path, env={}, log=lambda *_: None
        )
        self.assertAlmostEqual(store.get().latitude, 40.7300)

        # Corrupt file on disk
        with open(self.config_path, "w", encoding="utf-8") as f:
            f.write("INVALID JSON")

        cfg = store.get()
        self.assertAlmostEqual(cfg.latitude, 40.7300)
        self.assertIn("not valid JSON", store.error)

    def test_store_file_deletion_reverts_to_defaults(self):
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump({"latitude": 40.7300}, f)

        store = loc.LocationConfigStore(
            path=self.config_path, env={}, log=lambda *_: None
        )
        self.assertAlmostEqual(store.get().latitude, 40.7300)

        os.remove(self.config_path)
        cfg = store.get()
        self.assertAlmostEqual(cfg.latitude, loc.DEFAULT_LATITUDE)
        self.assertEqual(store.source, "built-in defaults")

    def test_store_atomic_save_config(self):
        store = loc.LocationConfigStore(
            path=self.config_path, env={}, log=lambda *_: None
        )
        new_data = {
            "latitude": 40.7100,
            "longitude": -74.0200,
            "location_name": "Downtown JC",
        }
        cfg, warnings = store.save_config(new_data)
        self.assertEqual(warnings, [])
        self.assertAlmostEqual(cfg.latitude, 40.7100)
        self.assertTrue(os.path.exists(self.config_path))
        self.assertEqual(store.source, self.config_path)

        # Read directly from disk
        with open(self.config_path, encoding="utf-8") as f:
            disk_doc = json.load(f)
        self.assertAlmostEqual(disk_doc["latitude"], 40.7100)

    def test_store_save_config_invalid_data_raises(self):
        store = loc.LocationConfigStore(
            path=self.config_path, env={}, log=lambda *_: None
        )
        with self.assertRaises(loc.LocationConfigError):
            store.save_config({"latitude": 1000.0})
        self.assertFalse(os.path.exists(self.config_path))

    def test_store_save_config_fallback_on_os_error(self):
        cache_fallback_dir = os.path.join(self.tmp_dir.name, "cache_fallback")
        os.makedirs(cache_fallback_dir, exist_ok=True)
        store = loc.LocationConfigStore(
            path=self.config_path, env={}, log=lambda *_: None
        )

        orig_makedirs = os.makedirs

        def fake_makedirs(path, exist_ok=True):
            if "read_only" in path:
                raise OSError("Read-only filesystem")
            return orig_makedirs(path, exist_ok=exist_ok)

        with patch("paths.resolve_cache_dir", return_value=cache_fallback_dir):
            with patch("os.makedirs", side_effect=fake_makedirs):
                target_ro = os.path.join(
                    self.tmp_dir.name, "read_only", "location.json"
                )
                cfg, _ = store.save_config({"latitude": 40.7200}, target_path=target_ro)
                fallback_file = os.path.join(cache_fallback_dir, "location.json")
                self.assertTrue(os.path.exists(fallback_file))
                self.assertEqual(store.path, fallback_file)
                self.assertAlmostEqual(cfg.latitude, 40.7200)

    def test_store_save_config_fallback_failure_raises(self):
        store = loc.LocationConfigStore(
            path=self.config_path, env={}, log=lambda *_: None
        )
        with patch(
            "paths.resolve_cache_dir", return_value=os.path.dirname(self.config_path)
        ):
            with patch("builtins.open", side_effect=OSError("Disk full")):
                with self.assertRaises(loc.LocationConfigError):
                    store.save_config({"latitude": 40.7200})

    def test_store_reset_to_default(self):
        store = loc.LocationConfigStore(
            path=self.config_path, env={}, log=lambda *_: None
        )
        store.save_config({"latitude": 40.7100, "city": "Jersey City"})
        self.assertAlmostEqual(store.get().latitude, 40.7100)

        cfg, _ = store.reset_to_default()
        self.assertAlmostEqual(cfg.latitude, loc.DEFAULT_LATITUDE)
        self.assertEqual(cfg.city, "Hoboken")

    def test_store_reset_method(self):
        store = loc.LocationConfigStore(
            path=self.config_path, env={}, log=lambda *_: None
        )
        store.reset()
        self.assertEqual(store.source, "built-in defaults")
        self.assertEqual(store.get(), loc.default_location_config())

    def test_module_level_helpers(self):
        orig_path = loc.LOCATION_STORE.path
        orig_primary = getattr(loc.LOCATION_STORE, "primary_path", orig_path)
        try:
            loc.LOCATION_STORE.primary_path = self.config_path
            loc.LOCATION_STORE.path = self.config_path
            loc.LOCATION_STORE.reset()
            cfg = loc.get_location_config()
            self.assertAlmostEqual(cfg.latitude, loc.DEFAULT_LATITUDE)

            saved = loc.save_location_config({"latitude": 40.7350})
            self.assertAlmostEqual(saved.latitude, 40.7350)
            self.assertAlmostEqual(loc.get_location_config().latitude, 40.7350)

            reset_cfg = loc.reset_location_config()
            self.assertAlmostEqual(reset_cfg.latitude, loc.DEFAULT_LATITUDE)
        finally:
            loc.LOCATION_STORE.primary_path = orig_primary
            loc.LOCATION_STORE.path = orig_path
            loc.LOCATION_STORE.reset()

    def test_store_init_without_path(self):
        store = loc.LocationConfigStore(env={}, log=lambda *_: None)
        self.assertIsNotNone(store.path)

    def test_load_location_config_file_too_large(self):
        large_path = os.path.join(self.tmp_dir.name, "large.json")
        with open(large_path, "wb") as f:
            f.write(b"x" * (64 * 1024 + 10))
        with self.assertRaises(loc.LocationConfigError):
            loc.load_location_config(large_path, {})

    def test_load_location_config_unreadable(self):
        unreadable_dir = os.path.join(self.tmp_dir.name, "dir_as_file")
        os.makedirs(unreadable_dir, exist_ok=True)
        with self.assertRaises(loc.LocationConfigError):
            loc.load_location_config(unreadable_dir, {})

    def test_store_save_config_target_matches_fallback(self):
        store = loc.LocationConfigStore(
            path=self.config_path, env={}, log=lambda *_: None
        )
        with patch(
            "paths.resolve_cache_dir", return_value=os.path.dirname(self.config_path)
        ):
            with patch("builtins.open", side_effect=OSError("Read-only")):
                with self.assertRaises(loc.LocationConfigError):
                    store.save_config(
                        {"latitude": 40.7100}, target_path=self.config_path
                    )

    def test_store_concurrent_access(self):
        store = loc.LocationConfigStore(
            path=self.config_path, env={}, log=lambda *_: None
        )
        errors = []

        def reader():
            for _ in range(50):
                try:
                    _ = store.get()
                except Exception as e:
                    errors.append(e)

        def writer():
            for i in range(20):
                try:
                    store.save_config({"latitude": 40.7000 + (i * 0.001)})
                except Exception as e:
                    errors.append(e)

        threads = [threading.Thread(target=reader) for _ in range(4)]
        threads.extend([threading.Thread(target=writer) for _ in range(2)])
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])

    def test_location_storage_error_subclass(self):
        self.assertTrue(issubclass(loc.LocationStorageError, loc.LocationConfigError))
        self.assertTrue(issubclass(loc.LocationStorageError, ValueError))

    def test_is_read_only_error_classification(self):
        self.assertTrue(loc._is_read_only_error(PermissionError("Access denied")))
        self.assertTrue(
            loc._is_read_only_error(OSError(errno.EACCES, "Permission denied"))
        )
        self.assertTrue(
            loc._is_read_only_error(OSError(errno.EPERM, "Operation not permitted"))
        )
        self.assertTrue(
            loc._is_read_only_error(OSError(errno.EROFS, "Read-only file system"))
        )
        self.assertTrue(loc._is_read_only_error(OSError("Read-only filesystem")))
        self.assertTrue(loc._is_read_only_error(OSError("Target permission denied")))
        self.assertFalse(
            loc._is_read_only_error(OSError(errno.ENOSPC, "No space left on device"))
        )
        self.assertFalse(
            loc._is_read_only_error(
                FileNotFoundError(errno.ENOENT, "No such file or directory")
            )
        )

    def test_store_save_config_double_fallback_failure_raises(self):
        store = loc.LocationConfigStore(
            path=self.config_path, env={}, log=lambda *_: None
        )
        cache_fallback_dir = os.path.join(self.tmp_dir.name, "cache_fallback")
        os.makedirs(cache_fallback_dir, exist_ok=True)
        with patch("paths.resolve_cache_dir", return_value=cache_fallback_dir):
            with patch(
                "builtins.open",
                side_effect=PermissionError(errno.EACCES, "Permission denied"),
            ):
                with self.assertRaises(loc.LocationStorageError) as ctx:
                    store.save_config({"latitude": 40.7200})
                self.assertIn("failed to write location", str(ctx.exception))
                self.assertIn("fallback", str(ctx.exception))

    def test_store_non_permission_error_raises_storage_error_without_fallback(self):
        store = loc.LocationConfigStore(
            path=self.config_path, env={}, log=lambda *_: None
        )
        cache_fallback_dir = os.path.join(self.tmp_dir.name, "cache_fallback")
        os.makedirs(cache_fallback_dir, exist_ok=True)
        fallback_file = os.path.join(cache_fallback_dir, "location.json")

        with patch("paths.resolve_cache_dir", return_value=cache_fallback_dir):
            with patch(
                "builtins.open",
                side_effect=OSError(errno.ENOSPC, "No space left on device"),
            ):
                with self.assertRaises(loc.LocationStorageError) as ctx:
                    store.save_config({"latitude": 40.7200})
                self.assertIn("No space left on device", str(ctx.exception))
                self.assertFalse(os.path.exists(fallback_file))
                self.assertEqual(store.path, self.config_path)

    def test_store_reset_restores_primary_path_after_fallback(self):
        cache_fallback_dir = os.path.join(self.tmp_dir.name, "cache_fallback")
        os.makedirs(cache_fallback_dir, exist_ok=True)
        store = loc.LocationConfigStore(
            path=self.config_path, env={}, log=lambda *_: None
        )
        orig_makedirs = os.makedirs

        def fake_makedirs(path, exist_ok=True):
            if "read_only" in path:
                raise PermissionError(errno.EACCES, "Permission denied")
            return orig_makedirs(path, exist_ok=exist_ok)

        with patch("paths.resolve_cache_dir", return_value=cache_fallback_dir):
            with patch("os.makedirs", side_effect=fake_makedirs):
                target_ro = os.path.join(
                    self.tmp_dir.name, "read_only", "location.json"
                )
                store.save_config({"latitude": 40.7200}, target_path=target_ro)
                fallback_file = os.path.join(cache_fallback_dir, "location.json")
                self.assertEqual(store.path, fallback_file)

        # Reset should restore store.path to store.primary_path
        store.reset()
        self.assertEqual(store.path, self.config_path)

    def test_store_concurrent_writers_no_failures_or_path_diversion(self):
        """Regression test for concurrency race condition in LocationConfigStore.save_config.

        Exercises 8 concurrent writer threads performing 25 writes each (200 total writes)
        synchronized via threading.Barrier to maximize contention.
        Asserts:
        - 0 write failures/exceptions across all 200 concurrent writes.
        - 0 path diversions: store.path strictly remains target config_path and never
          diverts to the fallback cache path.
        - store.source strictly remains target config_path.
        - store.error remains empty.
        - On-disk file exists, parses as valid JSON, and contains valid coordinates
          matching one of the written payloads.
        - In-memory store.get() matches the on-disk file state.
        - No orphan temporary files (*.tmp.*) are leaked in the config directory.
        """
        store = loc.LocationConfigStore(
            path=self.config_path, env={}, log=lambda *_: None
        )
        num_threads = 8
        writes_per_thread = 25
        barrier = threading.Barrier(num_threads)
        errors: list[tuple[int, int, str]] = []
        diversions: list[tuple[int, str]] = []
        written_payloads: set[tuple[float, float]] = set()
        payload_lock = threading.Lock()

        def writer(thread_idx: int) -> None:
            barrier.wait()
            for i in range(writes_per_thread):
                lat = round(40.7000 + (thread_idx * 0.001) + (i * 0.00001), 6)
                lon = round(-74.0300 - (i * 0.00001), 6)
                payload = {
                    "latitude": lat,
                    "longitude": lon,
                    "location_name": f"Worker-{thread_idx}-{i}",
                }
                try:
                    cfg, _ = store.save_config(payload)
                    with payload_lock:
                        written_payloads.add((lat, lon))
                    if store.path != self.config_path:
                        diversions.append((thread_idx, store.path))
                except Exception as exc:
                    errors.append((thread_idx, i, str(exc)))

        threads = [
            threading.Thread(target=writer, args=(t,)) for t in range(num_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(
            errors,
            [],
            f"Expected 0 write failures across {num_threads * writes_per_thread} concurrent writes, got {len(errors)}: {errors[:5]}",
        )
        self.assertEqual(
            diversions,
            [],
            f"Expected 0 store path diversions, got {len(diversions)}: {diversions[:5]}",
        )
        self.assertEqual(store.path, self.config_path)
        self.assertEqual(store.source, self.config_path)
        self.assertEqual(store.error, "")

        # Verify disk file validity
        self.assertTrue(os.path.exists(self.config_path))
        with open(self.config_path, encoding="utf-8") as f:
            disk_doc = json.load(f)
        self.assertIn((disk_doc["latitude"], disk_doc["longitude"]), written_payloads)

        # Verify in-memory store consistency
        active = store.get()
        self.assertEqual(active.latitude, disk_doc["latitude"])
        self.assertEqual(active.longitude, disk_doc["longitude"])

        # Verify no temporary files leaked
        temp_files = glob.glob(os.path.join(self.tmp_dir.name, "*.tmp*"))
        self.assertEqual(temp_files, [], f"Leaked temporary files: {temp_files}")

    def test_store_reset_preserves_custom_file_on_disk(self):
        """Verifies that calling store.reset() reloads config but never modifies or overwrites the file on disk."""
        store = loc.LocationConfigStore(
            path=self.config_path, env={}, log=lambda *_: None
        )
        custom_payload = {
            "latitude": 40.7482,
            "longitude": -74.0305,
            "location_name": "Custom Spot",
            "name": "Custom Spot",
            "address": "123 Main St",
        }
        store.save_config(custom_payload)
        with open(self.config_path, "rb") as f:
            content_before = f.read()

        # Calling reset() must reload state without altering content on disk
        store.reset()
        with open(self.config_path, "rb") as f:
            content_after = f.read()

        self.assertEqual(content_before, content_after)
        self.assertEqual(store.get().location_name, "Custom Spot")
        self.assertAlmostEqual(store.get().latitude, 40.7482)

    def test_repo_config_location_json_never_modified_by_test_operations(self):
        """Verifies that location operations in tests never write to the repository's config/location.json."""
        from paths import REPO_DIR

        repo_loc = os.path.join(REPO_DIR, "config", "location.json")
        if not os.path.exists(repo_loc):
            self.skipTest("No repo config/location.json exists")
        with open(repo_loc, "rb") as f:
            content_before = f.read()

        loc.reset_location_config()
        loc.save_location_config({"location_name": "Test Run Isolated Location"})
        loc.reset_location_config()

        with open(repo_loc, "rb") as f:
            content_after = f.read()

        self.assertEqual(
            content_before,
            content_after,
            "Repository config/location.json was modified by test operations!",
        )


class TestPathResolution(unittest.TestCase):
    def test_resolve_config_dir(self):
        cd = resolve_config_dir()
        self.assertTrue(os.path.isabs(cd))

    def test_resolve_location_config_path_default(self):
        path = resolve_location_config_path()
        self.assertTrue(path.endswith("location.json"))

    def test_resolve_location_config_path_env(self):
        with patch.dict(os.environ, {"LOCATION_CONFIG": "/tmp/custom_loc.json"}):
            self.assertEqual(resolve_location_config_path(), "/tmp/custom_loc.json")

    def test_resolve_data_dir(self):
        dd = resolve_data_dir()
        self.assertTrue(os.path.isabs(dd))

    def test_resolve_config_dir_env(self):
        with patch.dict(os.environ, {"CONFIG_DIR": "/custom/config"}):
            self.assertEqual(resolve_config_dir(), "/custom/config")

    def test_resolve_data_dir_env(self):
        with patch.dict(os.environ, {"DATA_DIR": "/custom/data"}):
            self.assertEqual(resolve_data_dir(), "/custom/data")


if __name__ == "__main__":
    unittest.main()
