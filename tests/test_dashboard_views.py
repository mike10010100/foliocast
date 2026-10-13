import io
import json
import os
import tempfile
import threading
import unittest
from datetime import datetime
from typing import Any
from unittest.mock import MagicMock, patch

import render_dashboard as rd
from canvas import (
    DEFAULT_STOPS,
    STOPS,
    ScaledDraw,
    get_canvas_stops,
)
from evening_view import render_evening_view
from location import (
    LOCATION_STORE,
    LocationConfig,
    reset_location_config,
    save_location_config,
)
from morning_view import render_morning_view
from PIL import Image, ImageDraw
from weather import (
    WeatherSnapshot,
    WeatherTracker,
    get_mock_weather_data,
)

from server import get_fresh_data, invalidate_transit_cache


class IsolatedLocationMixin:
    """Isolates LOCATION_STORE to a temporary directory for tests to prevent modifying live config."""

    def setUp(self):
        super().setUp()
        self._loc_temp_dir = tempfile.TemporaryDirectory()
        self._loc_config_path = os.path.join(self._loc_temp_dir.name, "location.json")
        self._orig_store_path = LOCATION_STORE.path
        self._orig_primary_path = getattr(
            LOCATION_STORE, "primary_path", LOCATION_STORE.path
        )
        LOCATION_STORE.primary_path = self._loc_config_path
        LOCATION_STORE.path = self._loc_config_path
        LOCATION_STORE.reset()
        reset_location_config()

    def tearDown(self):
        LOCATION_STORE.primary_path = self._orig_primary_path
        LOCATION_STORE.path = self._orig_store_path
        LOCATION_STORE.reset()
        self._loc_temp_dir.cleanup()
        super().tearDown()


class TestWeatherAdaptation(IsolatedLocationMixin, unittest.TestCase):
    def test_weather_tracker_adopts_active_location_coordinates(self):
        save_location_config(
            {
                "latitude": 40.7282,
                "longitude": -74.0776,
                "location_name": "Journal Square",
                "city": "Jersey City",
            }
        )
        tracker = WeatherTracker()
        self.assertAlmostEqual(tracker.latitude, 40.7282, places=4)
        self.assertAlmostEqual(tracker.longitude, -74.0776, places=4)
        self.assertEqual(tracker.location_name, "Journal Square")

    def test_weather_tracker_explicit_coordinates_override_config(self):
        save_location_config(
            {
                "latitude": 40.7282,
                "longitude": -74.0776,
                "location_name": "Journal Square",
            }
        )
        tracker = WeatherTracker(
            latitude=40.7128, longitude=-74.0060, location_name="New York, NY"
        )
        self.assertAlmostEqual(tracker.latitude, 40.7128, places=4)
        self.assertAlmostEqual(tracker.longitude, -74.0060, places=4)
        self.assertEqual(tracker.location_name, "New York, NY")

    @patch("urllib.request.urlopen")
    def test_weather_tracker_queries_open_meteo_with_custom_coordinates(
        self, mock_urlopen
    ):
        sample_api_resp = {
            "current": {
                "temperature_2m": 70.0,
                "apparent_temperature": 69.0,
                "relative_humidity_2m": 50,
                "weather_code": 0,
                "wind_speed_10m": 5.0,
            },
            "daily": {
                "time": ["2026-10-11"],
                "temperature_2m_max": [72.0],
                "temperature_2m_min": [55.0],
                "weather_code": [0],
                "precipitation_probability_max": [0],
            },
        }
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(sample_api_resp).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        tracker = WeatherTracker(
            latitude=40.7128, longitude=-74.0060, location_name="New York, NY"
        )
        snapshot = tracker.get_weather(force_refresh=True)

        self.assertEqual(snapshot.temp, 70)
        self.assertEqual(snapshot.location_name, "New York, NY")
        self.assertTrue(mock_urlopen.called)
        req = mock_urlopen.call_args[0][0]
        url = req.full_url
        self.assertIn("latitude=40.7128", url)
        self.assertIn("longitude=-74.006", url)

    def test_weather_cache_invalidation_on_location_update(self):
        tracker = WeatherTracker(cache_ttl=900)
        tracker._cache = WeatherSnapshot(
            temp=65,
            apparent_temp=64,
            condition="Clear",
            condition_glyph="SUN",
            temp_max=70,
            temp_min=50,
            humidity=50,
            wind_speed=5,
            precip_prob=0,
            forecast=(),
            status="ok",
            as_of=100.0,
            location_name="Hoboken, NJ",
        )
        tracker._cache_time = 100.0

        # Updating location via set_location must invalidate cache
        tracker.set_location(40.7128, -74.0060, "New York, NY")
        self.assertIsNone(tracker._cache)
        self.assertEqual(tracker._cache_time, 0.0)
        self.assertAlmostEqual(tracker.latitude, 40.7128, places=4)
        self.assertAlmostEqual(tracker.longitude, -74.0060, places=4)
        self.assertEqual(tracker.location_name, "New York, NY")

    def test_weather_tracker_set_location_thread_safety(self):
        tracker = WeatherTracker(latitude=40.7371, longitude=-74.0305)
        errors = []

        def worker(idx: int):
            try:
                for i in range(50):
                    lat = 40.0 + (idx + i) * 0.01
                    lon = -74.0 - (idx + i) * 0.01
                    tracker.set_location(lat, lon, f"Loc {idx}_{i}")
                    _ = tracker.latitude
                    _ = tracker.longitude
                    _ = tracker.location_name
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0)

    def test_weather_snapshot_to_dict_includes_location_name(self):
        snap = WeatherSnapshot(
            temp=68,
            apparent_temp=67,
            condition="Partly cloudy",
            condition_glyph="PARTLY_CLOUD",
            temp_max=72,
            temp_min=55,
            humidity=60,
            wind_speed=7,
            precip_prob=20,
            forecast=(),
            status="ok",
            as_of=500.0,
            location_name="Jersey City, NJ",
        )
        d = snap.to_dict()
        self.assertEqual(d["location_name"], "Jersey City, NJ")
        self.assertEqual(d["temp"], 68)

    def test_get_mock_weather_data_accepts_location_name(self):
        mock = get_mock_weather_data(location_name="Montclair, NJ")
        self.assertEqual(mock.location_name, "Montclair, NJ")
        d = mock.to_dict()
        self.assertEqual(d["location_name"], "Montclair, NJ")


class TestDynamicHeaderFormatting(unittest.TestCase):
    def test_morning_view_header_with_citibike_active(self):
        drawn_texts = []
        img = Image.new("RGB", (800, 480), "white")
        draw = ScaledDraw(ImageDraw.Draw(img), 1.0)
        orig_text = draw.text

        def mock_text(xy, text, *args, **kwargs):
            drawn_texts.append((xy, text))
            return orig_text(xy, text, *args, **kwargs)

        draw.text = mock_text

        cfg = LocationConfig(
            location_name="Hoboken City Hall", city="Hoboken", route="126"
        )
        cb_data = [
            {
                "name": "Clinton & 9th",
                "ebikes": 5,
                "classic": 2,
                "docks": 8,
                "walk_min": 3,
            }
        ]
        render_morning_view(
            draw,
            stops_data={},
            citibike_data=cb_data,
            now=datetime(2026, 10, 11, 8, 30),
            batt_level=85,
            is_charging=False,
            is_mock=False,
            width=800,
            height=480,
            location_config=cfg,
        )

        all_text_content = [t[1] for t in drawn_texts]
        self.assertTrue(any("CITI BIKE" in txt for txt in all_text_content))
        self.assertTrue(any("HOBOKEN MORNING DOCKS" in txt for txt in all_text_content))
        self.assertTrue(any("HOBOKEN CITY HALL" in txt for txt in all_text_content))
        self.assertTrue(any("126 BUS" in txt for txt in all_text_content))

    def test_morning_view_header_without_citibike(self):
        drawn_texts = []
        img = Image.new("RGB", (800, 480), "white")
        draw = ScaledDraw(ImageDraw.Draw(img), 1.0)
        orig_text = draw.text

        def mock_text(xy, text, *args, **kwargs):
            drawn_texts.append((xy, text))
            return orig_text(xy, text, *args, **kwargs)

        draw.text = mock_text

        cfg = LocationConfig(
            location_name="Grove St",
            city="Jersey City",
            route="119",
            destination="NYC Port Authority",
        )
        render_morning_view(
            draw,
            stops_data={},
            citibike_data=[],
            now=datetime(2026, 10, 11, 8, 30),
            batt_level=85,
            is_charging=False,
            is_mock=False,
            width=800,
            height=480,
            location_config=cfg,
        )

        all_text_content = [t[1] for t in drawn_texts]
        self.assertTrue(any(txt == "119" for txt in all_text_content))
        self.assertTrue(any("JERSEY CITY" in txt for txt in all_text_content))
        self.assertTrue(any("NYC PORT AUTHORITY" in txt for txt in all_text_content))
        self.assertFalse(any("E-BIKE PRIORITY" in txt for txt in all_text_content))
        self.assertTrue(any("GROVE ST" in txt for txt in all_text_content))

    def test_evening_view_dynamic_header_variations(self):
        drawn_texts = []
        img = Image.new("RGB", (800, 480), "white")
        draw = ScaledDraw(ImageDraw.Draw(img), 1.0)
        orig_text = draw.text

        def mock_text(xy, text, *args, **kwargs):
            drawn_texts.append((xy, text))
            return orig_text(xy, text, *args, **kwargs)

        draw.text = mock_text

        cfg = LocationConfig(
            city="Hoboken",
            route="126",
            destination="NYC Port Authority",
            location_name="Hoboken City Hall",
        )
        # With citibike
        render_evening_view(
            draw,
            stops_data={},
            citibike_data=[
                {"name": "Clinton & 9th", "ebikes": 2, "classic": 5, "docks": 4}
            ],
            now=datetime(2026, 10, 11, 18, 30),
            batt_level=80,
            is_charging=False,
            is_mock=False,
            width=800,
            height=480,
            location_config=cfg,
        )
        all_text_1 = [t[1] for t in drawn_texts]
        self.assertTrue(
            any("126 & CITI BIKE LIVE TRACKER" in txt for txt in all_text_1)
        )

        # Without citibike
        drawn_texts.clear()
        render_evening_view(
            draw,
            stops_data={},
            citibike_data=[],
            now=datetime(2026, 10, 11, 18, 30),
            batt_level=80,
            is_charging=False,
            is_mock=False,
            width=800,
            height=480,
            location_config=cfg,
        )
        all_text_2 = [t[1] for t in drawn_texts]
        self.assertTrue(any("126 REAL-TIME TRACKER" in txt for txt in all_text_2))
        self.assertFalse(any("CITI BIKE LIVE TRACKER" in txt for txt in all_text_2))

    def test_header_title_ellipsizing_for_long_city_and_destination(self):
        cfg = LocationConfig(
            city="Extremely Long Municipality Name That Would Surely Overflow",
            destination="A Very Long Port Authority Bus Terminal NYC Midtown Center",
            route="999",
        )
        drawn_texts = []
        img = Image.new("RGB", (800, 480), "white")
        draw = ScaledDraw(ImageDraw.Draw(img), 1.0)
        orig_text = draw.text

        def mock_text(xy, text, *args, **kwargs):
            drawn_texts.append((xy, text))
            return orig_text(xy, text, *args, **kwargs)

        draw.text = mock_text

        render_morning_view(
            draw,
            stops_data={},
            citibike_data=[],
            now=datetime(2026, 10, 11, 8, 30),
            batt_level=85,
            is_charging=False,
            is_mock=False,
            width=800,
            height=480,
            location_config=cfg,
        )
        # Find the title drawn at (b_x1 + 12, 15)
        title_item = next(
            (
                item
                for item in drawn_texts
                if item[0][1] == 15 and "EXTREMELY" in item[1]
            ),
            None,
        )
        self.assertIsNotNone(title_item)
        self.assertTrue(title_item[1].endswith("…") or len(title_item[1]) < 60)


class TestMorningViewLayoutAdaptation(IsolatedLocationMixin, unittest.TestCase):
    def test_morning_view_citi_bike_absent_bus_hero_expansion(self):
        containers = []
        img = Image.new("RGB", (800, 480), "white")
        draw = ScaledDraw(ImageDraw.Draw(img), 1.0)
        orig_rrect = draw.rounded_rectangle

        def mock_rrect(xy, *args, **kwargs):
            containers.append(tuple(xy))
            return orig_rrect(xy, *args, **kwargs)

        draw.rounded_rectangle = mock_rrect

        stops_data = {
            "20512": [
                {
                    "route": "126",
                    "destination": "126 NEW YORK",
                    "eta": "in 5 mins (8:35 AM)",
                    "vehicle_id": "25248",
                }
            ]
        }
        render_morning_view(
            draw,
            stops_data=stops_data,
            citibike_data=[],
            now=datetime(2026, 10, 11, 8, 30),
            batt_level=85,
            is_charging=False,
            is_mock=False,
            width=800,
            height=480,
        )

        hero_cards = [c for c in containers if c[1] == 70 and c[3] == 424]
        self.assertTrue(len(hero_cards) >= 1)
        # Verify no dock cards at width ~246 were drawn
        cb_cards = [c for c in containers if c[1] == 70 and c[3] == 346]
        self.assertEqual(len(cb_cards), 0)

    def test_morning_view_single_stop_full_width_expansion(self):
        containers = []
        img = Image.new("RGB", (800, 480), "white")
        draw = ScaledDraw(ImageDraw.Draw(img), 1.0)
        orig_rrect = draw.rounded_rectangle

        def mock_rrect(xy, *args, **kwargs):
            containers.append(tuple(xy))
            return orig_rrect(xy, *args, **kwargs)

        draw.rounded_rectangle = mock_rrect

        single_stop = [{"id": "20512", "name": "Washington & 9th", "walk_min": 5}]
        render_morning_view(
            draw,
            stops_data={"20512": [{"eta": "in 4 mins", "vehicle_id": "123"}]},
            citibike_data=[],
            now=datetime(2026, 10, 11, 8, 30),
            batt_level=85,
            is_charging=False,
            is_mock=False,
            width=800,
            height=480,
            stops=single_stop,
        )

        full_width_cards = [
            c
            for c in containers
            if c[0] == 20 and c[2] == 780 and c[1] == 70 and c[3] == 424
        ]
        self.assertEqual(len(full_width_cards), 1)

    def test_morning_view_dual_stop_side_by_side_expansion(self):
        containers = []
        img = Image.new("RGB", (800, 480), "white")
        draw = ScaledDraw(ImageDraw.Draw(img), 1.0)
        orig_rrect = draw.rounded_rectangle

        def mock_rrect(xy, *args, **kwargs):
            containers.append(tuple(xy))
            return orig_rrect(xy, *args, **kwargs)

        draw.rounded_rectangle = mock_rrect

        dual_stops = [
            {"id": "20512", "name": "Washington & 9th", "walk_min": 5},
            {"id": "20494", "name": "Clinton & 9th", "walk_min": 3},
        ]
        render_morning_view(
            draw,
            stops_data={},
            citibike_data=[],
            now=datetime(2026, 10, 11, 8, 30),
            batt_level=85,
            is_charging=False,
            is_mock=False,
            width=800,
            height=480,
            stops=dual_stops,
        )

        col_w = (800 - 40 - 20) // 2  # 370
        card_0 = (20, 70, 20 + col_w, 424)
        card_1 = (20 + col_w + 20, 70, 20 + col_w + 20 + col_w, 424)

        self.assertIn(card_0, containers)
        self.assertIn(card_1, containers)

    def test_adapted_morning_view_text_containment(self):
        """Exercises text containment on adapted morning view without Citi Bike."""
        from PIL import ImageDraw

        orig_text = ImageDraw.ImageDraw.text
        orig_rrect = ImageDraw.ImageDraw.rounded_rectangle

        container_calls = []
        text_calls = []

        def cap_rrect(self, xy, *a, **k):
            container_calls.append(tuple(xy))
            return orig_rrect(self, xy, *a, **k)

        def cap_text(self, xy, text, *a, **k):
            try:
                bbox = self.textbbox(xy, text, font=k.get("font"))
            except Exception:
                bbox = None
            text_calls.append((xy, text, bbox))
            return orig_text(self, xy, text, *a, **k)

        ImageDraw.ImageDraw.rounded_rectangle = cap_rrect
        ImageDraw.ImageDraw.text = cap_text

        try:
            permutations = [
                # (height, stops_data, stops_cfg)
                (
                    480,
                    {
                        "20512": [
                            {
                                "route": "126",
                                "destination": "126 NEW YORK",
                                "eta": "in 5 mins",
                                "vehicle_id": "25248",
                            },
                            {
                                "route": "126",
                                "destination": "126 NEW YORK",
                                "eta": "in 15 mins",
                                "vehicle_id": "25249",
                            },
                        ]
                    },
                    STOPS,
                ),
                (
                    600,
                    {
                        "20512": [
                            {
                                "route": "126",
                                "destination": "126 NEW YORK",
                                "eta": "in 2 mins",
                                "vehicle_id": "999",
                            },
                            {
                                "route": "126",
                                "destination": "126 NEW YORK",
                                "eta": "in 12 mins",
                                "vehicle_id": "998",
                            },
                            {
                                "route": "126",
                                "destination": "126 NEW YORK",
                                "eta": "in 22 mins",
                                "vehicle_id": "997",
                            },
                        ]
                    },
                    STOPS,
                ),
                (480, {}, STOPS),  # empty arrivals state
                (
                    480,
                    {
                        "20512": [
                            {"route": "126", "eta": "in 7 mins", "vehicle_id": "111"}
                        ]
                    },
                    [{"id": "20512", "name": "Washington & 9th", "walk_min": 5}],
                ),  # single stop
            ]

            for h, s_data, s_cfg in permutations:
                container_calls.clear()
                text_calls.clear()
                rd.render_dashboard(
                    s_data,
                    citibike_data=[],
                    output_path="/tmp/_containment_m4.png",
                    view="morning",
                    is_mock=False,
                    batt_level=80,
                    width=800,
                    height=h,
                    stops=s_cfg,
                )

                # Assert containment
                for xy, text, bbox in text_calls:
                    if not bbox:
                        continue
                    left, top, right, bottom = bbox
                    tx, ty = xy
                    enclosing = [
                        c
                        for c in container_calls
                        if c[0] <= tx <= c[2] and c[1] <= ty <= c[3]
                    ]
                    if not enclosing:
                        continue
                    c = min(enclosing, key=lambda r: (r[2] - r[0]) * (r[3] - r[1]))
                    self.assertLessEqual(
                        bottom,
                        c[3],
                        f"Text {text[:40]!r} bottom {bottom} > container {c}",
                    )
                    self.assertLessEqual(
                        right,
                        c[2] - 1,
                        f"Text {text[:40]!r} right {right} > container {c}",
                    )
                    self.assertGreaterEqual(
                        left, c[0], f"Text {text[:40]!r} left {left} < container {c}"
                    )
                    self.assertGreaterEqual(
                        top, c[1], f"Text {text[:40]!r} top {top} < container {c}"
                    )
        finally:
            ImageDraw.ImageDraw.text = orig_text
            ImageDraw.ImageDraw.rounded_rectangle = orig_rrect

    def test_morning_view_three_stop_balanced_columns(self):
        """Exercises 3-stop configuration rendering 3 balanced hero cards without Citi Bike."""
        containers = []
        img = Image.new("RGB", (800, 480), "white")
        draw = ScaledDraw(ImageDraw.Draw(img), 1.0)
        orig_rrect = draw.rounded_rectangle

        def mock_rrect(xy, *args, **kwargs):
            containers.append(tuple(xy))
            return orig_rrect(xy, *args, **kwargs)

        draw.rounded_rectangle = mock_rrect

        three_stops = [
            {"id": "20512", "name": "Washington & 9th", "walk_min": 5},
            {"id": "20494", "name": "Clinton & 9th", "walk_min": 3},
            {"id": "20514", "name": "Washington & 11th", "walk_min": 6},
        ]
        render_morning_view(
            draw,
            stops_data={},
            citibike_data=[],
            now=datetime(2026, 10, 11, 8, 30),
            batt_level=85,
            is_charging=False,
            is_mock=False,
            width=800,
            height=480,
            stops=three_stops,
        )

        hero_cards = [c for c in containers if c[1] == 70 and c[3] == 424]
        self.assertEqual(len(hero_cards), 3)
        self.assertEqual(hero_cards[0], (20.0, 70.0, 264.0, 424.0))
        self.assertEqual(hero_cards[1], (278.0, 70.0, 522.0, 424.0))
        self.assertEqual(hero_cards[2], (536.0, 70.0, 780.0, 424.0))

    def test_morning_view_arrival_countdown_states_and_branches(self):
        """Verifies DUE countdown, ALL ABOARD badge, non-int ETA, and error empty state."""
        from canvas import STATUS_ERROR

        stops = [
            {"id": "20512", "name": "Washington & 9th", "walk_min": 5},
            {"id": "20494", "name": "Clinton & 9th", "walk_min": 3},
            {"id": "20514", "name": "Washington & 11th", "walk_min": 6},
        ]
        s_data = {
            "20512": [
                {"route": "126", "eta": "in 0 mins", "vehicle_id": "101"},
                {"route": "126", "eta": "all aboard", "vehicle_id": "102"},
                {"route": "126", "eta": "in 15 mins", "vehicle_id": "103"},
            ],
            "20494": [
                {"route": "126", "eta": "11:45 PM", "vehicle_id": "201"},
            ],
        }
        drawn_texts = []
        img = Image.new("RGB", (800, 480), "white")
        draw = ScaledDraw(ImageDraw.Draw(img), 1.0)
        orig_text = draw.text

        def mock_text(xy, text, *args, **kwargs):
            drawn_texts.append(str(text))
            return orig_text(xy, text, *args, **kwargs)

        draw.text = mock_text

        render_morning_view(
            draw,
            stops_data=s_data,
            citibike_data=[],
            now=datetime(2026, 10, 11, 8, 30),
            batt_level=85,
            is_charging=False,
            is_mock=False,
            stop_status={"20514": STATUS_ERROR},
            width=800,
            height=480,
            stops=stops,
        )

        self.assertTrue(any("DUE" in t for t in drawn_texts))
        self.assertTrue(any("LIVE DATA UNAVAILABLE" in t for t in drawn_texts))
        self.assertTrue(any("Followed by: in 15 mins" in t for t in drawn_texts))

    def test_evening_view_tall_display_card_bottom_clears_divider(self):
        """Verifies tall (800x600) display evening view cards do not cross divider at y=548."""
        containers = []
        img = Image.new("RGB", (800, 600), "white")
        draw = ScaledDraw(ImageDraw.Draw(img), 1.0)
        orig_rrect = draw.rounded_rectangle

        def mock_rrect(xy, *args, **kwargs):
            containers.append(tuple(xy))
            return orig_rrect(xy, *args, **kwargs)

        draw.rounded_rectangle = mock_rrect

        render_evening_view(
            draw,
            stops_data={},
            citibike_data=[],
            now=datetime(2026, 10, 11, 18, 30),
            batt_level=85,
            is_charging=False,
            is_mock=False,
            width=800,
            height=600,
        )

        hero_cards = [c for c in containers if c[1] == 80 and c[3] > 200]
        self.assertEqual(len(hero_cards), 2)
        for card in hero_cards:
            self.assertLessEqual(
                card[3],
                544,
                f"Hero card bottom {card[3]} exceeds maximum allowed 544 (divider at 548)",
            )
            self.assertEqual(card[3], 542)

    def test_evening_and_morning_view_long_stop_names_text_containment(self):
        """Verifies text containment under long stop names and headers across morning and evening views."""
        long_stops = [
            {
                "id": "20512",
                "name": "WASHINGTON STREET AT 9TH STREET HOBOKEN NJ INBOUND METRO",
                "subtitle": "Stop #20512 • via Lincoln Tunnel Dedicated Bus Lane Corridor",
                "walk_min": 15,
            },
            {
                "id": "20494",
                "name": "CLINTON STREET AT 9TH STREET HOBOKEN NJ RESIDENTIAL",
                "subtitle": "Stop #20494 • via Clinton Avenue Local Priority Route",
                "walk_min": 8,
            },
        ]
        s_data = {
            "20512": [
                {
                    "route": "126",
                    "destination": "PORT AUTHORITY TERMINAL NYC",
                    "eta": "in 12 mins",
                    "vehicle_id": "999",
                }
            ]
        }
        cb_data = [
            {
                "name": "CLINTON STREET & 9TH STREET CROSSING METRO BIKE STATION",
                "ebikes": 5,
                "classic": 3,
                "docks": 10,
                "walk_min": 4,
            }
        ]

        from PIL import ImageDraw

        orig_text = ImageDraw.ImageDraw.text
        orig_rrect = ImageDraw.ImageDraw.rounded_rectangle
        orig_rect = ImageDraw.ImageDraw.rectangle

        all_containers: list[tuple[float, float, float, float]] = []
        all_texts: list[dict[str, Any]] = []

        def cap_rrect(self, xy, *a, **k):
            all_containers.append(tuple(xy))
            return orig_rrect(self, xy, *a, **k)

        def cap_rect(self, xy, *a, **k):
            all_containers.append(tuple(xy))
            return orig_rect(self, xy, *a, **k)

        def cap_text(self, xy, text, *a, **k):
            font = k.get("font")
            try:
                bbox = self.textbbox(xy, text, font=font) if font else None
            except Exception:
                bbox = None
            all_texts.append({"xy": tuple(xy), "text": str(text), "bbox": bbox})
            return orig_text(self, xy, text, *a, **k)

        ImageDraw.ImageDraw.rounded_rectangle = cap_rrect
        ImageDraw.ImageDraw.rectangle = cap_rect
        ImageDraw.ImageDraw.text = cap_text

        try:
            scenarios = [
                (render_morning_view, [], 480),
                (render_morning_view, cb_data, 480),
                (render_morning_view, [], 600),
                (render_evening_view, [], 480),
                (render_evening_view, cb_data, 480),
                (render_evening_view, [], 600),
                (render_evening_view, cb_data, 600),
            ]

            for view_fn, cb, h in scenarios:
                all_containers.clear()
                all_texts.clear()
                img = Image.new("RGB", (800, h), "white")
                draw = ScaledDraw(ImageDraw.Draw(img), 1.0)

                view_fn(
                    draw,
                    stops_data=s_data,
                    citibike_data=cb,
                    now=datetime(2026, 10, 11, 8, 30),
                    batt_level=80,
                    is_charging=False,
                    is_mock=False,
                    width=800,
                    height=h,
                    stops=long_stops,
                )

                for item in all_texts:
                    bbox = item["bbox"]
                    text = item["text"]
                    xy = item["xy"]
                    if not bbox:
                        continue
                    left, top, right, bottom = bbox

                    self.assertLessEqual(
                        right,
                        800,
                        f"{view_fn.__name__} (h={h}) text {text!r} right {right} > 800",
                    )
                    self.assertLessEqual(
                        bottom,
                        h,
                        f"{view_fn.__name__} (h={h}) text {text!r} bottom {bottom} > {h}",
                    )
                    self.assertGreaterEqual(
                        left,
                        0,
                        f"{view_fn.__name__} (h={h}) text {text!r} left {left} < 0",
                    )
                    self.assertGreaterEqual(
                        top,
                        0,
                        f"{view_fn.__name__} (h={h}) text {text!r} top {top} < 0",
                    )

                    tx, ty = xy
                    enclosing = [
                        c
                        for c in all_containers
                        if c[0] <= tx <= c[2] and c[1] <= ty <= c[3]
                    ]
                    if enclosing:
                        c = min(
                            enclosing,
                            key=lambda r: (r[2] - r[0]) * (r[3] - r[1]),
                        )
                        self.assertLessEqual(
                            right,
                            c[2] + 1,
                            f"{view_fn.__name__} text {text!r} right {right} > container {c}",
                        )
                        self.assertLessEqual(
                            bottom,
                            c[3] + 1,
                            f"{view_fn.__name__} text {text!r} bottom {bottom} > container {c}",
                        )
        finally:
            ImageDraw.ImageDraw.rounded_rectangle = orig_rrect
            ImageDraw.ImageDraw.rectangle = orig_rect
            ImageDraw.ImageDraw.text = orig_text


class TestBackwardCompatibilityAndDefaultParity(
    IsolatedLocationMixin, unittest.TestCase
):
    def test_default_config_matches_baseline_morning_view(self):
        drawn_texts = []
        containers = []
        img = Image.new("RGB", (800, 480), "white")
        draw = ScaledDraw(ImageDraw.Draw(img), 1.0)
        orig_text = draw.text
        orig_rrect = draw.rounded_rectangle

        def mock_text(xy, text, *args, **kwargs):
            drawn_texts.append((xy, text))
            return orig_text(xy, text, *args, **kwargs)

        def mock_rrect(xy, *args, **kwargs):
            containers.append(tuple(xy))
            return orig_rrect(xy, *args, **kwargs)

        draw.text = mock_text
        draw.rounded_rectangle = mock_rrect

        cb_mock = [
            {
                "name": "Clinton & 9th",
                "ebikes": 5,
                "classic": 2,
                "docks": 8,
                "walk_min": 3,
            },
            {
                "name": "Washington & 11th",
                "ebikes": 2,
                "classic": 8,
                "docks": 14,
                "walk_min": 5,
            },
            {
                "name": "Washington & 8th",
                "ebikes": 0,
                "classic": 15,
                "docks": 3,
                "walk_min": 4,
            },
        ]
        render_morning_view(
            draw,
            stops_data=rd.get_mock_data(),
            citibike_data=cb_mock,
            now=datetime(2026, 10, 11, 8, 30),
            batt_level=85,
            is_charging=False,
            is_mock=True,
            width=800,
            height=480,
        )

        all_texts = [t[1] for t in drawn_texts]
        self.assertTrue(any(t == "CITI BIKE" for t in all_texts))
        self.assertTrue(any("MORNING DOCKS" in t for t in all_texts))
        self.assertTrue(
            any("HOBOKEN CITY HALL • E-BIKE PRIORITY" in t for t in all_texts)
        )
        # Dock cards at y=70..346
        dock_cards = [c for c in containers if c[1] == 70 and c[3] == 346]
        self.assertEqual(len(dock_cards), 3)
        # Bus bar at y=348..424
        bus_bar = [c for c in containers if c[1] == 348 and c[3] == 424]
        self.assertEqual(len(bus_bar), 1)

    def test_default_config_matches_baseline_evening_view(self):
        drawn_texts = []
        containers = []
        img = Image.new("RGB", (800, 480), "white")
        draw = ScaledDraw(ImageDraw.Draw(img), 1.0)
        orig_text = draw.text
        orig_rrect = draw.rounded_rectangle

        def mock_text(xy, text, *args, **kwargs):
            drawn_texts.append((xy, text))
            return orig_text(xy, text, *args, **kwargs)

        def mock_rrect(xy, *args, **kwargs):
            containers.append(tuple(xy))
            return orig_rrect(xy, *args, **kwargs)

        draw.text = mock_text
        draw.rounded_rectangle = mock_rrect

        cb_mock = [
            {
                "name": "Clinton & 9th",
                "ebikes": 5,
                "classic": 2,
                "docks": 8,
                "walk_min": 3,
            },
            {
                "name": "Washington & 11th",
                "ebikes": 2,
                "classic": 8,
                "docks": 14,
                "walk_min": 5,
            },
            {
                "name": "Washington & 8th",
                "ebikes": 0,
                "classic": 15,
                "docks": 3,
                "walk_min": 4,
            },
        ]
        render_evening_view(
            draw,
            stops_data=rd.get_mock_data(),
            citibike_data=cb_mock,
            now=datetime(2026, 10, 11, 18, 30),
            batt_level=85,
            is_charging=False,
            is_mock=True,
            width=800,
            height=480,
        )

        all_texts = [t[1] for t in drawn_texts]
        self.assertTrue(any(t == "126" for t in all_texts))
        self.assertTrue(any("HOBOKEN → NYC PORT" in t for t in all_texts))
        self.assertTrue(
            any("NJ TRANSIT 126 & CITI BIKE LIVE TRACKER" in t for t in all_texts)
        )
        # Top bus hero cards at y=70..346
        bus_cards = [c for c in containers if c[1] == 70 and c[3] == 346]
        self.assertEqual(len(bus_cards), 2)
        # Bottom Citi Bike summary strip at y=348..424
        cb_strip = [c for c in containers if c[1] == 348 and c[3] == 424]
        self.assertEqual(len(cb_strip), 1)

    def test_get_canvas_stops_fallback_to_default_stops(self):
        stops = get_canvas_stops(None)
        self.assertEqual(len(stops), 2)
        self.assertEqual(stops[0]["id"], "20508")
        self.assertEqual(stops[1]["id"], "20491")
        self.assertEqual(DEFAULT_STOPS, STOPS)

    def test_render_dashboard_sync_alias_callable(self):
        self.assertTrue(callable(rd.render_dashboard_sync))
        buf = io.BytesIO()
        out = rd.render_dashboard_sync(
            rd.get_mock_data(),
            citibike_data=[],
            output_path=buf,
            view="morning",
            is_mock=True,
        )
        self.assertIsNotNone(out)
        self.assertTrue(len(buf.getvalue()) > 0)


class TestServerDynamicDataResolution(IsolatedLocationMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        invalidate_transit_cache()

    def tearDown(self):
        invalidate_transit_cache()
        super().tearDown()

    def test_get_fresh_data_mock_reflects_active_stops(self):
        save_location_config(
            {
                "stops_override": [
                    {
                        "id": "20514",
                        "name": "Washington & 11th",
                        "walk_min": 6,
                    }
                ]
            }
        )
        stops_data, stop_status, cb_data = get_fresh_data(use_mock=True)
        self.assertIn("20514", stops_data)
        self.assertIn("20514", stop_status)

    def test_get_fresh_data_micromobility_disabled_returns_empty_cb(self):
        save_location_config({"enable_micromobility": False})
        stops_data, stop_status, cb_data = get_fresh_data(use_mock=True)
        self.assertEqual(cb_data, [])


if __name__ == "__main__":
    unittest.main()
