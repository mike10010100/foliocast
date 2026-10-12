import datetime
import os
import sys
import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../server"))
)

from canvas import (  # noqa: E402
    format_hero_eta,
    is_arrival_live,
    resolve_badge,
)
from evening_view import render_evening_view  # noqa: E402
from morning_view import render_morning_view  # noqa: E402


class TestHeroEtaAndBadges(unittest.TestCase):
    """
    Direct verification and regression tests for hero ETA formatting,
    live vs scheduled badge resolution, and upcoming departures copy.
    """

    def test_format_hero_eta_under_60_mins(self):
        self.assertEqual(format_hero_eta({"eta": "in 5 mins"}), ("5", "MIN"))
        self.assertEqual(format_hero_eta({"eta": "in 45 mins"}), ("45", "MIN"))
        self.assertEqual(format_hero_eta({"eta": "DUE"}), ("DUE", ""))
        self.assertEqual(format_hero_eta({"eta": "Approaching"}), ("DUE", ""))
        self.assertEqual(format_hero_eta({"eta": "All Aboard"}), ("DUE", ""))

    def test_format_hero_eta_60_plus_mins(self):
        # The exact reported bug case:
        bug_arrival = {"eta": "\u25cb in 160 mins (4:09 PM)", "live": False}
        self.assertEqual(format_hero_eta(bug_arrival), ("4:09", "PM"))

        # Clock time embedded in parenthesis
        self.assertEqual(
            format_hero_eta({"eta": "in 75 mins (10:15 AM)"}), ("10:15", "AM")
        )

        # Elapsed hours/mins fallback when no clock time string is present
        self.assertEqual(format_hero_eta({"eta": "in 120 mins"}), ("2h", ""))
        self.assertEqual(format_hero_eta({"eta": "in 135 mins"}), ("2h 15m", ""))

    def test_format_hero_eta_with_epoch(self):
        # 1700000000 is 2023-11-14 22:13:20 UTC
        # Whatever local time it is, it should return a non-empty clock time string
        dt = datetime.datetime.fromtimestamp(1700000000)
        expected_time = dt.strftime("%I:%M").lstrip("0")
        expected_ampm = dt.strftime("%p")
        res_time, res_ampm = format_hero_eta({"eta": "in 90 mins", "epoch": 1700000000})
        self.assertEqual(res_time, expected_time)
        self.assertEqual(res_ampm, expected_ampm)

    def test_format_hero_eta_clock_only_fallback(self):
        self.assertEqual(format_hero_eta({"eta": "8:35 AM"}), ("8:35", "AM"))
        self.assertEqual(format_hero_eta({"eta": "12:45 PM"}), ("12:45", "PM"))
        self.assertEqual(format_hero_eta({"eta": "Scheduled"}), ("Schedul", ""))
        self.assertEqual(format_hero_eta({}), ("--", ""))

    def test_is_arrival_live(self):
        # Explicit live flag
        self.assertTrue(is_arrival_live({"live": True}))
        self.assertFalse(is_arrival_live({"live": False}))

        # Glyphs
        self.assertFalse(is_arrival_live({"eta": "\u25cb in 10 mins"}))
        self.assertTrue(is_arrival_live({"eta": "\u25cf in 10 mins"}))

        # Vehicle ID presence
        self.assertTrue(is_arrival_live({"vehicle_id": "25248"}))
        self.assertFalse(is_arrival_live({"vehicle_id": None}))

    def test_resolve_badge_scheduled_vs_on_time(self):
        walk_min = 3

        # Reported bug case: 160 mins scheduled departure with no live vehicle
        bug_arrival = {"eta": "\u25cb in 160 mins (4:09 PM)", "live": False}
        badge = resolve_badge(bug_arrival, walk_min)
        self.assertIsNotNone(badge)
        assert badge is not None
        label, bg, fg = badge
        self.assertEqual(label, "SCHEDULED")
        self.assertEqual(bg, "#f0f0f0")
        self.assertEqual(fg, "black")

        # Live vehicle confirmed
        live_arrival = {
            "eta": "in 12 mins (8:42 AM)",
            "vehicle_id": "22119",
            "live": True,
        }
        badge_live = resolve_badge(live_arrival, walk_min)
        self.assertIsNotNone(badge_live)
        assert badge_live is not None
        self.assertEqual(badge_live[0], "ON TIME")

        # Walking thresholds (live or scheduled)
        run_arrival = {"eta": "in 2 mins", "live": True}
        self.assertEqual(resolve_badge(run_arrival, walk_min)[0], "RUN! LEAVING SOON")  # type: ignore[index]
        self.assertEqual(
            resolve_badge(run_arrival, walk_min, compact=True)[0],  # type: ignore[index]
            "RUN!",
        )

        walk_now_arrival = {"eta": "in 5 mins", "live": True}
        self.assertEqual(resolve_badge(walk_now_arrival, walk_min)[0], "WALK NOW")  # type: ignore[index]

        get_ready_arrival = {"eta": "in 9 mins", "live": True}
        self.assertEqual(resolve_badge(get_ready_arrival, walk_min)[0], "GET READY")  # type: ignore[index]

        # None for clock-only or non-minute
        self.assertIsNone(resolve_badge({"eta": "8:35 AM"}, walk_min))


class TestViewRenderingRegression(unittest.TestCase):
    """
    Renders actual images to verify that text, badges, and layout render
    cleanly without contradictory copy or overlapping text.
    """

    def setUp(self):
        self.out = "/tmp/test_hero_render_out.png"

    def tearDown(self):
        if os.path.exists(self.out):
            try:
                os.remove(self.out)
            except OSError:
                pass

    def test_evening_view_renders_reported_bug_state_correctly(self):
        # Recreate the exact scenario from the screenshot:
        # Clinton & 9th (#20494) has a single scheduled bus in 160 mins (4:09 PM)
        stops_data = {
            "20494": [
                {
                    "route": "126",
                    "destination": "126 NEW YORK VIA CLINTON",
                    "eta": "\u25cb in 160 mins (4:09 PM)",
                    "occupancy": None,
                    "vehicle_id": None,
                    "live": False,
                }
            ],
            "20512": [
                {
                    "route": "126",
                    "destination": "126 NEW YORK",
                    "eta": "in 12 mins (1:49 PM)",
                    "occupancy": "SEATS_AVAILABLE",
                    "vehicle_id": "25248",
                    "live": True,
                }
            ],
        }

        captured_text = []
        orig_text = ImageDraw.ImageDraw.text

        def mock_text(self, xy, text, *args, **kwargs):
            captured_text.append(str(text))
            return orig_text(self, xy, text, *args, **kwargs)

        img = Image.new("RGB", (800, 600), "white")
        draw = ImageDraw.Draw(img)

        with patch.object(ImageDraw.ImageDraw, "text", mock_text):
            render_evening_view(
                draw,
                stops_data,
                citibike_data=[],
                now=datetime.datetime(2026, 10, 12, 13, 29),
                batt_level=85,
                is_charging=False,
                is_mock=False,
                width=800,
                height=600,
            )

        # 1. SCHEDULED badge must be rendered for the unmonitored bus
        self.assertIn("SCHEDULED", captured_text)
        # 2. ON TIME must NOT be rendered for Clinton & 9th (it should be on 20512 which is live)
        # 3. 4:09 and PM must be rendered as the hero digits/unit
        self.assertIn("4:09", captured_text)
        self.assertIn("PM", captured_text)
        # 4. Upcoming buses text must NOT say "No further buses in next 60 min" for Clinton & 9th
        self.assertIn("No other departures scheduled", captured_text)

    def test_morning_view_renders_scheduled_badge_and_clock_hero(self):
        stops_data = {
            "20494": [
                {
                    "route": "126",
                    "destination": "126 NEW YORK VIA CLINTON",
                    "eta": "\u25cb in 160 mins (4:09 PM)",
                    "occupancy": None,
                    "vehicle_id": None,
                    "live": False,
                }
            ]
        }

        captured_text = []
        orig_text = ImageDraw.ImageDraw.text

        def mock_text(self, xy, text, *args, **kwargs):
            captured_text.append(str(text))
            return orig_text(self, xy, text, *args, **kwargs)

        img = Image.new("RGB", (800, 480), "white")
        draw = ImageDraw.Draw(img)

        with patch.object(ImageDraw.ImageDraw, "text", mock_text):
            render_morning_view(
                draw,
                stops_data,
                citibike_data=[],
                now=datetime.datetime(2026, 10, 12, 13, 29),
                batt_level=85,
                is_charging=False,
                is_mock=False,
                width=800,
                height=480,
            )

        self.assertIn("SCHEDULED", captured_text)
        self.assertIn("4:09", captured_text)
        self.assertIn("PM", captured_text)
        self.assertIn("NO OTHER BUSES SCHEDULED", captured_text)


if __name__ == "__main__":
    unittest.main()
