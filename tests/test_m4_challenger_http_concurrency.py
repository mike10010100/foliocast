"""Milestone 4 Adversarial Challenge Suite: Live HTTP /dashboard.png, Concurrency & Dynamic Reconfig Stress.

Adversarial empirical testing verifying:
1. Live HTTP testing over real loopback socket:
   - GET /dashboard.png?mock=1 returns valid PNG header and 800x480 dimensions.
   - Dynamic location reconfiguration via authenticated POST /api/location (Jersey City, enable_micromobility=False).
   - Immediate GET /dashboard.png?mock=1 reflects dynamic headers and adaptive empty-CitiBike hero expansion without server restart.
   - Clean return to Hoboken default baseline upon POST /api/location reset.
   - Auth rejection (403) and validation error handling (400).
   - Kindle PW5 resolution/rotation parameter handling.
2. Concurrency stress across 16+ worker threads:
   - WeatherTracker thread-safety under simultaneous set_location, update_from_config, invalidate_cache, and get_weather.
   - render_dashboard concurrency across mixed views, dimensions, and configs.
   - Interleaved concurrent HTTP reconfig and dashboard rendering over socket.
"""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from typing import Any
from unittest.mock import MagicMock, patch

from PIL import Image

# Ensure server module is on sys.path
_SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "server"))
if _SERVER_DIR not in sys.path:
    sys.path.insert(0, _SERVER_DIR)

from location import (  # noqa: E402
    LOCATION_STORE,
    LocationConfig,
    reset_location_config,
)
from render_dashboard import render_dashboard  # noqa: E402
from weather import (  # noqa: E402
    WeatherTracker,
)

import server  # noqa: E402
from server import DashboardHandler  # noqa: E402

TEST_TOKEN = "challenger-m4-stress-token-9876"


def _http_get(
    port: int,
    path: str,
    headers: dict[str, str] | None = None,
    max_retries: int = 4,
) -> tuple[int, dict[str, str], bytes]:
    url = f"http://127.0.0.1:{port}{path}"
    for attempt in range(max_retries):
        req = urllib.request.Request(url, headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status, dict(resp.headers), resp.read()
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read()
        except (ConnectionResetError, urllib.error.URLError):
            if attempt == max_retries - 1:
                raise
            time.sleep(0.02)
    raise RuntimeError("unreachable")


def _http_post(
    port: int,
    path: str,
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
    max_retries: int = 4,
) -> tuple[int, dict[str, str], bytes]:
    url = f"http://127.0.0.1:{port}{path}"
    hdrs = headers or {}
    for attempt in range(max_retries):
        req = urllib.request.Request(
            url,
            data=body,
            headers=hdrs,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status, dict(resp.headers), resp.read()
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read()
        except (ConnectionResetError, urllib.error.URLError):
            if attempt == max_retries - 1:
                raise
            time.sleep(0.02)
    raise RuntimeError("unreachable")


def _auth_headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    hdrs = {
        "X-Tracker-Token": TEST_TOKEN,
        "Content-Type": "application/json",
    }
    if extra:
        hdrs.update(extra)
    return hdrs


class TestLiveHTTPDashboardAndLocationReconfig(unittest.TestCase):
    """Exercises the live HTTP server over a loopback socket with dynamic reconfiguration."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._orig_token = getattr(server, "CONTROL_TOKEN", "")
        server.CONTROL_TOKEN = TEST_TOKEN

        ThreadingHTTPServer.request_queue_size = 64
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), DashboardHandler)
        cls.port = cls.httpd.server_address[1]
        cls.server_thread = threading.Thread(
            target=cls.httpd.serve_forever, daemon=True
        )
        cls.server_thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        server.CONTROL_TOKEN = cls._orig_token
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.server_thread.join(timeout=5)

    def setUp(self) -> None:
        server.CONTROL_TOKEN = TEST_TOKEN
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_path = os.path.join(self.temp_dir.name, "location.json")
        self._orig_store_path = LOCATION_STORE.path
        self._orig_primary_path = getattr(
            LOCATION_STORE, "primary_path", LOCATION_STORE.path
        )
        LOCATION_STORE.primary_path = self.config_path
        LOCATION_STORE.path = self.config_path
        LOCATION_STORE.reset()
        reset_location_config()
        server.invalidate_transit_cache()

    def tearDown(self) -> None:
        LOCATION_STORE.primary_path = self._orig_primary_path
        LOCATION_STORE.path = self._orig_store_path
        LOCATION_STORE.reset()
        reset_location_config()
        server.invalidate_transit_cache()
        server.cb_tracker.set_stations(None)
        self.temp_dir.cleanup()

    def test_default_dashboard_png_headers_and_dimensions(self) -> None:
        """GET /dashboard.png?mock=1 returns 200, valid PNG magic bytes, and 800x480."""
        status, headers, body = _http_get(self.port, "/dashboard.png?mock=1")
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("Content-Type"), "image/png")
        self.assertIn("ETag", headers)

        # Verify PNG magic header
        self.assertTrue(
            body.startswith(b"\x89PNG\r\n\x1a\n"),
            "Response body must start with standard PNG magic signature",
        )

        # Verify exact dimensions with PIL
        img = Image.open(io.BytesIO(body))
        self.assertEqual(img.size, (800, 480))
        self.assertIn(img.mode, ("RGB", "RGBA", "L"))

    def test_dynamic_reconfig_and_adaptive_hero_expansion_without_restart(self) -> None:
        """Dynamic reconfiguration updates header and expands hero card without server restart."""
        # 1. Fetch default Hoboken morning dashboard
        status_def, _, body_def = _http_get(
            self.port, "/dashboard.png?mock=1&view=morning"
        )
        self.assertEqual(status_def, 200)
        img_def = Image.open(io.BytesIO(body_def))
        self.assertEqual(img_def.size, (800, 480))

        # 2. Reconfigure location dynamically to Jersey City with micromobility disabled
        reconfig_payload = {
            "latitude": 40.7178,
            "longitude": -74.0431,
            "city": "Jersey City",
            "location_name": "Grove St",
            "route": "80",
            "destination": "Exchange Place",
            "enable_micromobility": False,
        }
        status_post, _, body_post = _http_post(
            self.port,
            "/api/location",
            body=json.dumps(reconfig_payload).encode("utf-8"),
            headers=_auth_headers(),
        )
        self.assertEqual(status_post, 200)
        post_resp = json.loads(body_post.decode("utf-8"))
        self.assertAlmostEqual(post_resp.get("latitude"), 40.7178, places=4)
        self.assertAlmostEqual(post_resp.get("longitude"), -74.0431, places=4)
        post_loc = post_resp.get("location", {})
        self.assertFalse(post_loc.get("enable_micromobility"))
        self.assertFalse(post_resp.get("citibike_enabled"))
        self.assertEqual(post_resp.get("city"), "Jersey City")

        # Verify GET /api/location returns the new state
        status_get_loc, _, body_get_loc = _http_get(self.port, "/api/location")
        self.assertEqual(status_get_loc, 200)
        get_loc_resp = json.loads(body_get_loc.decode("utf-8"))
        get_loc_obj = get_loc_resp.get("location", {})
        self.assertFalse(get_loc_obj.get("enable_micromobility"))
        self.assertFalse(get_loc_resp.get("citibike_enabled"))
        self.assertEqual(get_loc_resp.get("city"), "Jersey City")

        # 3. Immediately request GET /dashboard.png?mock=1&view=morning without restarting server
        status_jc, headers_jc, body_jc = _http_get(
            self.port, "/dashboard.png?mock=1&view=morning"
        )
        self.assertEqual(status_jc, 200)
        self.assertEqual(headers_jc.get("Content-Type"), "image/png")
        self.assertTrue(body_jc.startswith(b"\x89PNG\r\n\x1a\n"))

        img_jc = Image.open(io.BytesIO(body_jc))
        self.assertEqual(img_jc.size, (800, 480))

        # Verify geometric layout adaptation directly on rendered pixels:
        # At (20, 352):
        # - Default Hoboken morning view has separate dock cards (y0=70, y1=346) and bus arrivals (y0=358, y1=424),
        #   making pixel (20, 352) white (255, 255, 255) between the cards.
        # - Reconfigured Jersey City view expands bus hero card full-height (y0=70, y1=424),
        #   making pixel (20, 352) black (0, 0, 0) on the continuous left outer border.
        self.assertEqual(
            img_def.getpixel((20, 352)),
            (255, 255, 255),
            "Default Hoboken layout must have white gap between dock cards and bus arrival bar at (20, 352)",
        )
        self.assertEqual(
            img_jc.getpixel((20, 352)),
            (0, 0, 0),
            "Adaptive hero expansion must extend outer card border continuously across (20, 352)",
        )

        # 4. Reset location back to Hoboken default
        reset_payload = {"action": "reset"}
        status_reset, _, body_reset = _http_post(
            self.port,
            "/api/location",
            body=json.dumps(reset_payload).encode("utf-8"),
            headers=_auth_headers(),
        )
        self.assertEqual(status_reset, 200)
        reset_resp = json.loads(body_reset.decode("utf-8"))
        reset_loc = reset_resp.get("location", {})
        self.assertEqual(reset_resp.get("city"), "Hoboken")
        self.assertTrue(reset_loc.get("enable_micromobility"))
        self.assertTrue(reset_resp.get("citibike_enabled"))

        # 5. Immediately request GET /dashboard.png?mock=1&view=morning again
        status_restored, _, body_restored = _http_get(
            self.port, "/dashboard.png?mock=1&view=morning"
        )
        self.assertEqual(status_restored, 200)
        img_restored = Image.open(io.BytesIO(body_restored))
        self.assertEqual(img_restored.size, (800, 480))
        self.assertEqual(
            img_restored.getpixel((20, 352)),
            (255, 255, 255),
            "Restored Hoboken layout must restore white gap at (20, 352)",
        )

        # Verify clean structural restoration back to Hoboken default
        self.assertEqual(
            img_restored.getpixel((20, 352)),
            img_def.getpixel((20, 352)),
            "Reset must cleanly restore default Hoboken dashboard layout at (20, 352)",
        )

    def test_out_of_coverage_location_adaptive_expansion(self) -> None:
        """Out-of-coverage coordinates (e.g. Austin, TX) expand morning bus card and disable Citi Bike."""
        reconfig_payload = {
            "latitude": 30.2672,
            "longitude": -97.7431,
            "city": "Austin",
            "location_name": "Congress Ave",
            "route": "1",
            "destination": "Downtown",
            "enable_micromobility": False,
        }
        status_post, _, _ = _http_post(
            self.port,
            "/api/location",
            body=json.dumps(reconfig_payload).encode("utf-8"),
            headers=_auth_headers(),
        )
        self.assertEqual(status_post, 200)

        status_png, _, body_png = _http_get(
            self.port, "/dashboard.png?mock=1&view=morning"
        )
        self.assertEqual(status_png, 200)
        img = Image.open(io.BytesIO(body_png))
        self.assertEqual(img.size, (800, 480))
        self.assertEqual(
            img.getpixel((20, 352)),
            (0, 0, 0),
            "Adaptive hero expansion must extend outer card border continuously across (20, 352) for Austin",
        )

    def test_live_http_auth_and_validation_gates(self) -> None:
        """POST /api/location enforces auth gates (403) and input validation (400)."""
        valid_payload = json.dumps({"latitude": 40.7128, "longitude": -74.0060}).encode(
            "utf-8"
        )

        # Missing auth header -> 403 Forbidden
        status, _, _ = _http_post(self.port, "/api/location", body=valid_payload)
        self.assertEqual(status, 403)

        # Wrong token -> 403 Forbidden
        status, _, _ = _http_post(
            self.port,
            "/api/location",
            body=valid_payload,
            headers={
                "X-Tracker-Token": "bad-token",
                "Content-Type": "application/json",
            },
        )
        self.assertEqual(status, 403)

        # Malformed JSON -> 400 Bad Request
        status, _, body_err = _http_post(
            self.port,
            "/api/location",
            body=b"not-json{{{",
            headers=_auth_headers(),
        )
        self.assertEqual(status, 400)
        self.assertIn(b"invalid JSON", body_err)

        # Non-dict JSON -> 400 Bad Request
        status, _, body_err = _http_post(
            self.port,
            "/api/location",
            body=b'["not", "a", "dict"]',
            headers=_auth_headers(),
        )
        self.assertEqual(status, 400)
        self.assertIn(b"expected a JSON object", body_err)

    def test_kindle_parameter_handling_and_views(self) -> None:
        """Dashboard handles Kindle PW5 full resolution, rotation, and evening view."""
        # Kindle PW5 landscape (1648x1236)
        status_pw5_0, _, body_pw5_0 = _http_get(
            self.port, "/dashboard.png?mock=1&kindle=pw5&rotate=0"
        )
        self.assertEqual(status_pw5_0, 200)
        img_pw5_0 = Image.open(io.BytesIO(body_pw5_0))
        self.assertEqual(img_pw5_0.size, (1648, 1236))

        # Kindle PW5 rotated 90 (1236x1648)
        status_pw5_90, _, body_pw5_90 = _http_get(
            self.port, "/dashboard.png?mock=1&kindle=pw5&rotate=90"
        )
        self.assertEqual(status_pw5_90, 200)
        img_pw5_90 = Image.open(io.BytesIO(body_pw5_90))
        self.assertEqual(img_pw5_90.size, (1236, 1648))

        # Explicit evening view
        status_eve, headers_eve, body_eve = _http_get(
            self.port, "/dashboard.png?mock=1&view=evening"
        )
        self.assertEqual(status_eve, 200)
        self.assertEqual(headers_eve.get("X-Tracker-View"), "evening")
        img_eve = Image.open(io.BytesIO(body_eve))
        self.assertEqual(img_eve.size, (800, 480))


class TestConcurrencyStress(unittest.TestCase):
    """Stress tests WeatherTracker, render_dashboard, and loopback HTTP across 16+ threads."""

    def test_concurrent_weather_tracker_operations_24_threads(self) -> None:
        """24 concurrent threads stressing set_location, update_from_config, invalidate, and get_weather."""
        tracker = WeatherTracker(latitude=40.7484, longitude=-74.0303)
        sample_api_resp = {
            "current": {
                "temperature_2m": 68.0,
                "apparent_temperature": 67.0,
                "relative_humidity_2m": 55,
                "weather_code": 1,
                "wind_speed_10m": 6.0,
            },
            "daily": {
                "time": ["2026-10-11"],
                "temperature_2m_max": [70.0],
                "temperature_2m_min": [52.0],
                "weather_code": [1],
                "precipitation_probability_max": [10],
            },
        }

        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(sample_api_resp).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = False

        num_threads = 24
        iterations_per_thread = 50
        errors: list[Exception] = []

        def worker(thread_id: int) -> None:
            try:
                for i in range(iterations_per_thread):
                    if thread_id % 4 == 0:
                        lat = 40.0 + (thread_id + i) * 0.005
                        lon = -74.0 - (thread_id + i) * 0.005
                        tracker.set_location(lat, lon, f"Loc_{thread_id}_{i}")
                    elif thread_id % 4 == 1:
                        cfg = LocationConfig(
                            latitude=40.7 + thread_id * 0.01,
                            longitude=-74.0 - thread_id * 0.01,
                            location_name=f"ConfigLoc_{thread_id}",
                        )
                        tracker.update_from_config(cfg)
                    elif thread_id % 4 == 2:
                        tracker.invalidate_cache()
                    else:
                        snap = tracker.get_weather(force_refresh=(i % 10 == 0))
                        self.assertIsNotNone(snap)
                        self.assertIn(snap.status, ("ok", "stale", "error"))
            except Exception as exc:
                errors.append(exc)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            threads = [
                threading.Thread(target=worker, args=(t,)) for t in range(num_threads)
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=10)

        self.assertEqual(
            len(errors),
            0,
            f"WeatherTracker concurrent stress failed with errors: {errors}",
        )

    def test_concurrent_render_dashboard_24_threads(self) -> None:
        """24 concurrent threads calling render_dashboard with varying parameters."""
        stops_mock = {
            "20512": [
                {
                    "route": "126",
                    "destination": "126 NEW YORK",
                    "eta": "in 4 mins",
                    "vehicle_id": "1001",
                }
            ],
            "20494": [
                {
                    "route": "126",
                    "destination": "126 NEW YORK",
                    "eta": "in 8 mins",
                    "vehicle_id": "1002",
                }
            ],
        }
        cb_mock = [
            {"name": "Clinton & 9th", "ebikes": 4, "classic": 2, "docks": 8},
            {"name": "Washington & 8th", "ebikes": 1, "classic": 6, "docks": 10},
        ]

        num_threads = 24
        iterations_per_thread = 15
        errors: list[Exception] = []

        def worker(thread_id: int) -> None:
            try:
                for i in range(iterations_per_thread):
                    view = "morning" if (thread_id + i) % 2 == 0 else "evening"
                    has_cb = (thread_id + i) % 3 != 0
                    cb_data = cb_mock if has_cb else []
                    cfg = LocationConfig(
                        latitude=40.7484 + (thread_id * 0.001),
                        longitude=-74.0303 - (thread_id * 0.001),
                        city="Hoboken" if has_cb else "Jersey City",
                        enable_micromobility=has_cb,
                    )
                    buf = io.BytesIO()
                    render_dashboard(
                        stops_data=stops_mock,
                        citibike_data=cb_data,
                        output_path=buf,
                        view=view,
                        is_mock=True,
                        batt_level=75,
                        is_charging=False,
                        width=800,
                        height=480,
                        location_config=cfg,
                    )
                    raw_bytes = buf.getvalue()
                    self.assertTrue(
                        raw_bytes.startswith(b"\x89PNG\r\n\x1a\n"),
                        "Output must be valid PNG",
                    )
                    img = Image.open(io.BytesIO(raw_bytes))
                    self.assertEqual(img.size, (800, 480))
            except Exception as exc:
                errors.append(exc)

        threads = [
            threading.Thread(target=worker, args=(t,)) for t in range(num_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)

        self.assertEqual(
            len(errors),
            0,
            f"render_dashboard concurrency failed with errors: {errors}",
        )

    def test_concurrent_http_interleaved_reconfig_and_render_20_threads(self) -> None:
        """20 concurrent client threads hammering GET /dashboard.png, GET /api/location, and POST /api/location."""
        orig_token = getattr(server, "CONTROL_TOKEN", "")
        server.CONTROL_TOKEN = TEST_TOKEN

        ThreadingHTTPServer.request_queue_size = 64
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), DashboardHandler)
        port = httpd.server_address[1]
        server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        server_thread.start()

        temp_dir = tempfile.TemporaryDirectory()
        config_path = os.path.join(temp_dir.name, "location.json")
        orig_store_path = LOCATION_STORE.path
        orig_primary_path = getattr(LOCATION_STORE, "primary_path", LOCATION_STORE.path)
        LOCATION_STORE.primary_path = config_path
        LOCATION_STORE.path = config_path
        LOCATION_STORE.reset()
        reset_location_config()
        server.invalidate_transit_cache()

        errors: list[tuple[int, str, Any]] = []
        num_threads = 20
        iterations_per_thread = 20
        barrier = threading.Barrier(num_threads)

        def client_worker(thread_id: int) -> None:
            barrier.wait()
            try:
                for i in range(iterations_per_thread):
                    if thread_id < 10:
                        # 10 threads fetching /dashboard.png?mock=1
                        status, _, body = _http_get(
                            port, f"/dashboard.png?mock=1&t={i}_{thread_id}"
                        )
                        if status != 200 or not body.startswith(b"\x89PNG"):
                            errors.append((thread_id, "dashboard", status))
                    elif thread_id < 15:
                        # 5 threads oscillating location configs via POST /api/location
                        if i % 2 == 0:
                            payload = {
                                "latitude": 40.7178,
                                "longitude": -74.0431,
                                "city": "Jersey City",
                                "enable_micromobility": False,
                            }
                        else:
                            payload = {
                                "latitude": 40.7484,
                                "longitude": -74.0303,
                                "city": "Hoboken",
                                "enable_micromobility": True,
                            }
                        status, _, _ = _http_post(
                            port,
                            "/api/location",
                            body=json.dumps(payload).encode("utf-8"),
                            headers=_auth_headers(),
                        )
                        if status != 200:
                            errors.append((thread_id, "post_location", status))
                    else:
                        # 5 threads fetching /api/location
                        status, _, body = _http_get(port, "/api/location")
                        if status != 200 or b"status" not in body:
                            errors.append((thread_id, "get_location", status))
            except Exception as exc:
                errors.append((thread_id, "exception", exc))

        try:
            threads = [
                threading.Thread(target=client_worker, args=(t,))
                for t in range(num_threads)
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=20)
        finally:
            httpd.shutdown()
            httpd.server_close()
            server_thread.join(timeout=5)
            server.CONTROL_TOKEN = orig_token
            LOCATION_STORE.primary_path = orig_primary_path
            LOCATION_STORE.path = orig_store_path
            LOCATION_STORE.reset()
            reset_location_config()
            server.invalidate_transit_cache()
            server.cb_tracker.set_stations(None)
            temp_dir.cleanup()

        self.assertEqual(
            len(errors),
            0,
            f"Interleaved HTTP concurrency encountered errors: {errors}",
        )


if __name__ == "__main__":
    unittest.main()
