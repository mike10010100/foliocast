"""Integration tests for the /api/location REST endpoints in server/server.py.

Exercises GET and POST routes, authentication gates, validation errors,
and cache invalidation over a real loopback HTTP socket.
"""

import glob
import json
import os
import socket
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from location import LOCATION_STORE, LocationStorageError
from test_server_http import ServerHTTPTestBase, _auth_headers, _http, _http_get

import server


class TestServerLocationHTTP(ServerHTTPTestBase):
    def setUp(self):
        super().setUp()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_path = os.path.join(self.temp_dir.name, "location.json")
        self._orig_store_path = LOCATION_STORE.path
        self._orig_primary_path = getattr(
            LOCATION_STORE, "primary_path", LOCATION_STORE.path
        )
        LOCATION_STORE.primary_path = self.config_path
        LOCATION_STORE.path = self.config_path
        LOCATION_STORE.reset()

    def tearDown(self):
        LOCATION_STORE.primary_path = self._orig_primary_path
        LOCATION_STORE.path = self._orig_store_path
        LOCATION_STORE.reset()
        self.temp_dir.cleanup()
        super().tearDown()

    def test_get_location_public_unauthenticated(self):
        status, headers, body = _http_get(self.port, "/api/location")
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("Content-Type"), "application/json")
        data = json.loads(body.decode("utf-8"))
        self.assertEqual(data.get("status"), "ok")
        self.assertAlmostEqual(data.get("latitude"), 40.7371, places=4)
        self.assertAlmostEqual(data.get("longitude"), -74.0305, places=4)
        self.assertIn("resolved_bus_stops", data)
        self.assertIn("resolved_citibike_stations", data)
        self.assertIn("stops", data)
        self.assertIn("citibike_stations", data)
        self.assertIn("location", data)

    def test_get_location_with_auth_header(self):
        status, _, body = _http_get(self.port, "/api/location", headers=_auth_headers())
        self.assertEqual(status, 200)
        data = json.loads(body.decode("utf-8"))
        self.assertEqual(data.get("status"), "ok")

    def test_get_location_trailing_slash(self):
        status, _, body = _http_get(self.port, "/api/location/")
        self.assertEqual(status, 200)
        data = json.loads(body.decode("utf-8"))
        self.assertEqual(data.get("status"), "ok")

    def test_post_location_missing_token_403(self):
        payload = json.dumps({"latitude": 40.7410, "longitude": -74.0350}).encode(
            "utf-8"
        )
        status, _, _ = _http("POST", self.port, "/api/location", body=payload)
        self.assertEqual(status, 403)

    def test_post_location_invalid_token_403(self):
        payload = json.dumps({"latitude": 40.7410, "longitude": -74.0350}).encode(
            "utf-8"
        )
        status, _, _ = _http(
            "POST",
            self.port,
            "/api/location",
            headers={"X-Tracker-Token": "invalid-token-xyz"},
            body=payload,
        )
        self.assertEqual(status, 403)

    def test_post_location_missing_content_length_411(self):
        s = socket.create_connection(("127.0.0.1", self.port), timeout=5)
        try:
            req = (
                f"POST /api/location HTTP/1.1\r\n"
                f"Host: 127.0.0.1:{self.port}\r\n"
                f"X-Tracker-Token: {server.CONTROL_TOKEN}\r\n\r\n"
            )
            s.sendall(req.encode("utf-8"))
            resp = s.recv(4096)
            self.assertTrue(
                resp.startswith(b"HTTP/1.0 411") or resp.startswith(b"HTTP/1.1 411")
            )
        finally:
            s.close()

    def test_post_location_payload_too_large_413(self):
        payload = b"A" * 70000
        headers = _auth_headers({"Content-Type": "application/json"})
        status, _, _ = _http(
            "POST", self.port, "/api/location", headers=headers, body=payload
        )
        self.assertEqual(status, 413)

    def test_post_location_malformed_json_400(self):
        status, _, body = _http(
            "POST",
            self.port,
            "/api/location",
            headers=_auth_headers({"Content-Type": "application/json"}),
            body=b"not-json-content",
        )
        self.assertEqual(status, 400)
        err = json.loads(body.decode("utf-8"))
        self.assertIn("error", err)

    def test_post_location_non_object_json_400(self):
        for invalid_body in (b'["array"]', b'"string"', b"123"):
            status, _, body = _http(
                "POST",
                self.port,
                "/api/location",
                headers=_auth_headers({"Content-Type": "application/json"}),
                body=invalid_body,
            )
            self.assertEqual(status, 400)
            err = json.loads(body.decode("utf-8"))
            self.assertIn("error", err)

    def test_post_location_non_object_config_field_400(self):
        status, _, body = _http(
            "POST",
            self.port,
            "/api/location",
            headers=_auth_headers({"Content-Type": "application/json"}),
            body=json.dumps({"config": "not-an-object"}).encode("utf-8"),
        )
        self.assertEqual(status, 400)
        err = json.loads(body.decode("utf-8"))
        self.assertIn("error", err)

    def test_post_location_invalid_bounds_400(self):
        # Latitude out of bounds
        status, _, body = _http(
            "POST",
            self.port,
            "/api/location",
            headers=_auth_headers({"Content-Type": "application/json"}),
            body=json.dumps({"latitude": 95.0, "longitude": -74.03}).encode("utf-8"),
        )
        self.assertEqual(status, 400)
        err = json.loads(body.decode("utf-8"))
        self.assertIn("error", err)

        # Longitude out of bounds
        status, _, body = _http(
            "POST",
            self.port,
            "/api/location",
            headers=_auth_headers({"Content-Type": "application/json"}),
            body=json.dumps({"latitude": 40.74, "longitude": -190.0}).encode("utf-8"),
        )
        self.assertEqual(status, 400)
        err = json.loads(body.decode("utf-8"))
        self.assertIn("error", err)

    def test_post_location_valid_update_200(self):
        update_data = {
            "latitude": 40.7410,
            "longitude": -74.0350,
            "name": "Downtown Hoboken",
            "city": "Hoboken",
            "state": "NJ",
        }
        status, headers, body = _http(
            "POST",
            self.port,
            "/api/location",
            headers=_auth_headers({"Content-Type": "application/json"}),
            body=json.dumps(update_data).encode("utf-8"),
        )
        self.assertEqual(status, 200)
        data = json.loads(body.decode("utf-8"))
        self.assertAlmostEqual(data.get("latitude"), 40.7410, places=4)
        self.assertAlmostEqual(data.get("longitude"), -74.0350, places=4)
        self.assertEqual(data.get("name"), "Downtown Hoboken")

        # Verify GET returns updated location
        get_status, _, get_body = _http_get(self.port, "/api/location")
        self.assertEqual(get_status, 200)
        get_data = json.loads(get_body.decode("utf-8"))
        self.assertAlmostEqual(get_data.get("latitude"), 40.7410, places=4)
        self.assertEqual(get_data.get("name"), "Downtown Hoboken")

    def test_post_location_trailing_slash_200(self):
        update_data = {"latitude": 40.7420, "longitude": -74.0320}
        status, _, body = _http(
            "POST",
            self.port,
            "/api/location/",
            headers=_auth_headers({"Content-Type": "application/json"}),
            body=json.dumps(update_data).encode("utf-8"),
        )
        self.assertEqual(status, 200)
        data = json.loads(body.decode("utf-8"))
        self.assertAlmostEqual(data.get("latitude"), 40.7420, places=4)

    def test_post_location_form_urlencoded_200(self):
        status, _, body = _http(
            "POST",
            self.port,
            "/api/location",
            headers=_auth_headers(
                {"Content-Type": "application/x-www-form-urlencoded"}
            ),
            body=b"latitude=40.7430&longitude=-74.0310",
        )
        self.assertEqual(status, 200)
        data = json.loads(body.decode("utf-8"))
        self.assertAlmostEqual(data.get("latitude"), 40.7430, places=4)

    def test_post_location_stops_override(self):
        update_data = {
            "stops_override": [
                {
                    "id": "20512",
                    "name": "Custom Stop",
                    "walk_min": 7,
                    "distance_m": 500,
                }
            ]
        }
        status, _, body = _http(
            "POST",
            self.port,
            "/api/location",
            headers=_auth_headers({"Content-Type": "application/json"}),
            body=json.dumps(update_data).encode("utf-8"),
        )
        self.assertEqual(status, 200)
        data = json.loads(body.decode("utf-8"))
        self.assertEqual(len(data.get("stops", [])), 1)
        self.assertEqual(data["stops"][0]["id"], "20512")
        self.assertEqual(data["stops"][0]["name"], "Custom Stop")

    def test_post_location_reset_action_200(self):
        # First modify
        _http(
            "POST",
            self.port,
            "/api/location",
            headers=_auth_headers({"Content-Type": "application/json"}),
            body=json.dumps({"latitude": 40.7100, "longitude": -74.0100}).encode(
                "utf-8"
            ),
        )

        # Then reset
        status, _, body = _http(
            "POST",
            self.port,
            "/api/location",
            headers=_auth_headers({"Content-Type": "application/json"}),
            body=json.dumps({"action": "reset"}).encode("utf-8"),
        )
        self.assertEqual(status, 200)
        data = json.loads(body.decode("utf-8"))
        self.assertAlmostEqual(data.get("latitude"), 40.7371, places=4)

    def test_post_location_invalidates_server_caches(self):
        with server._data_lock:
            server._data_cache["stops"] = {"test": 123}
            server._data_cache["time"] = time.time()
            server._data_cache["cb"] = [{"station": "old"}]
        with server._render_lock:
            server._render_cache[("dummy",)] = b"dummy_png"

        status, _, _ = _http(
            "POST",
            self.port,
            "/api/location",
            headers=_auth_headers({"Content-Type": "application/json"}),
            body=json.dumps({"latitude": 40.7410, "longitude": -74.0350}).encode(
                "utf-8"
            ),
        )
        self.assertEqual(status, 200)

        with server._data_lock:
            self.assertIsNone(server._data_cache["stops"])
            self.assertEqual(server._data_cache["time"], 0.0)
            self.assertIsNone(server._data_cache["cb"])
        with server._render_lock:
            self.assertEqual(len(server._render_cache), 0)

    def test_unsupported_method(self):
        status, _, _ = _http(
            "PUT",
            self.port,
            "/api/location",
            headers=_auth_headers({"Content-Type": "application/json"}),
            body=b"{}",
        )
        self.assertIn(status, (404, 405, 501))

    def test_post_location_storage_error_returns_500(self):
        with patch(
            "server.save_location_config",
            side_effect=LocationStorageError("disk I/O error"),
        ):
            status, _, body = _http(
                "POST",
                self.port,
                "/api/location",
                headers=_auth_headers({"Content-Type": "application/json"}),
                body=json.dumps({"latitude": 40.7100, "longitude": -74.0100}).encode(
                    "utf-8"
                ),
            )
        self.assertEqual(status, 500)
        data = json.loads(body.decode("utf-8"))
        self.assertIn("disk I/O error", data.get("error", ""))

    def test_post_location_concurrent_requests_no_path_hijacking(self):
        """Regression test for concurrent HTTP POST /api/location requests.

        Fires concurrent authenticated POST requests across 8 client threads
        (10 requests each = 80 total requests) synchronized via threading.Barrier
        against the live ThreadingHTTPServer.
        Asserts:
        - 100% of requests return HTTP 200 (0 errors, 0 HTTP 400/500).
        - Every response body contains valid JSON with status 'ok' and valid coordinates.
        - LOCATION_STORE.path is never hijacked to the fallback cache path.
        - LOCATION_STORE.source remains self.config_path.
        - Sequential GET /api/location returns HTTP 200 matching disk state.
        - No temporary files (*.tmp.*) are leaked in the temporary configuration directory.
        """
        num_threads = 8
        reqs_per_thread = 10
        barrier = threading.Barrier(num_threads)
        responses: list[tuple[int, int, int, bytes]] = []
        resp_lock = threading.Lock()

        def client_worker(thread_idx: int) -> None:
            barrier.wait()
            for i in range(reqs_per_thread):
                lat = round(40.7100 + (thread_idx * 0.001) + (i * 0.00001), 6)
                lon = round(-74.0200 - (i * 0.00001), 6)
                body = json.dumps(
                    {
                        "latitude": lat,
                        "longitude": lon,
                        "location_name": f"Concurrent-{thread_idx}-{i}",
                    }
                ).encode("utf-8")
                status, _, raw_body = _http(
                    "POST",
                    self.port,
                    "/api/location",
                    headers=_auth_headers({"Content-Type": "application/json"}),
                    body=body,
                )
                with resp_lock:
                    responses.append((thread_idx, i, status, raw_body))

        threads = [
            threading.Thread(target=client_worker, args=(t,))
            for t in range(num_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        total_requests = num_threads * reqs_per_thread
        self.assertEqual(len(responses), total_requests)

        non_200 = [r for r in responses if r[2] != 200]
        self.assertEqual(
            non_200,
            [],
            f"Expected all HTTP 200, but {len(non_200)}/{total_requests} requests failed: {non_200[:3]}",
        )

        # Verify response body structure
        for _, _, _, raw_body in responses:
            doc = json.loads(raw_body.decode("utf-8"))
            self.assertEqual(doc.get("status"), "ok")
            self.assertIn("latitude", doc)
            self.assertIn("longitude", doc)
            self.assertIn("resolved_bus_stops", doc)
            self.assertIn("resolved_citibike_stations", doc)

        # Assert no path hijacking occurred on LOCATION_STORE
        self.assertEqual(
            LOCATION_STORE.path,
            self.config_path,
            f"LOCATION_STORE.path was hijacked to {LOCATION_STORE.path}",
        )
        self.assertEqual(LOCATION_STORE.source, self.config_path)
        self.assertEqual(LOCATION_STORE.error, "")

        # Verify follow-up sequential GET /api/location returns 200
        get_status, _, get_body = _http_get(self.port, "/api/location")
        self.assertEqual(get_status, 200)
        get_doc = json.loads(get_body.decode("utf-8"))
        self.assertEqual(get_doc.get("status"), "ok")

        # Verify disk file validity
        self.assertTrue(os.path.exists(self.config_path))
        with open(self.config_path, encoding="utf-8") as f:
            disk_doc = json.load(f)
        self.assertAlmostEqual(disk_doc["latitude"], get_doc["latitude"], places=5)
        self.assertAlmostEqual(disk_doc["longitude"], get_doc["longitude"], places=5)

        # Verify no orphan temporary files leaked
        temp_files = glob.glob(os.path.join(self.temp_dir.name, "*.tmp*"))
        self.assertEqual(temp_files, [], f"Leaked temporary files: {temp_files}")


if __name__ == "__main__":
    unittest.main()
