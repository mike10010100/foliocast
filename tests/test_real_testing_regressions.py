"""
Regression test suite preserving failures discovered during real-testing campaign.

Invariants verified:
1. Status string honesty: Arrival records with non-clock, non-minute statuses like
   'Scheduled', 'Canceled', or 'Delayed' must produce standard, readable transit
   abbreviations ('SCHED', 'CANC', 'DELAY') rather than raw character truncations (e.g. 'Schedul').
2. Zero-minute walk support: Stops override must permit walk_min=0 for users
   residing directly at or adjacent to transit stops (matching docs/api.md and transit catalog).
3. Weather hero visual containment: Long condition descriptions (e.g. WMO 99 'Thunderstorm with heavy hail')
   must never overflow the card boundary or collide with adjacent metric cards across 800x480 and 800x600 layouts.
4. Header subtitle containment: Header subtitle must remain bounded within the available left title area.
"""

import unittest
from datetime import datetime

from canvas import ScaledDraw, format_hero_eta
from dashboard_dsl import HeaderWidget, Rect, RenderContext, WeatherHeroWidget
from location import parse_location_config
from PIL import Image, ImageDraw
from transit_provider import Hoboken126Provider
from weather import get_mock_weather_data


class TestRealTestingRegressions(unittest.TestCase):
    def test_format_hero_eta_status_abbreviations(self):
        """Verifies format_hero_eta maps transit statuses to standard abbreviations without word truncation."""
        self.assertEqual(format_hero_eta({"eta": "Scheduled"}), ("SCHED", ""))
        self.assertEqual(format_hero_eta({"eta": "scheduled"}), ("SCHED", ""))
        self.assertEqual(format_hero_eta({"eta": "Canceled"}), ("CANC", ""))
        self.assertEqual(format_hero_eta({"eta": "Cancelled"}), ("CANC", ""))
        self.assertEqual(format_hero_eta({"eta": "Delayed"}), ("DELAY", ""))

        # Still extracts clock time when embedded
        self.assertEqual(
            format_hero_eta({"eta": "Scheduled (4:09 PM)"}), ("4:09", "PM")
        )
        self.assertEqual(format_hero_eta({"eta": "Delayed (5:15 PM)"}), ("5:15", "PM"))

    def test_walk_min_zero_allowed_in_location_and_provider(self):
        """Verifies that walk_min=0 is accepted across location config and transit providers."""
        # LocationConfig parsing
        cfg = parse_location_config(
            {"stops_override": [{"id": "20508", "walk_min": 0, "distance_m": 0}]}
        )
        self.assertIsNotNone(cfg.stops_override)
        self.assertEqual(cfg.stops_override[0]["walk_min"], 0)  # type: ignore[index]

        # TransitProvider resolution
        provider = Hoboken126Provider()
        resolved = provider.resolve_stops(
            40.7371,
            -74.0305,
            overrides=[{"id": "20508", "walk_min": 0, "distance_m": 0}],
        )
        self.assertEqual(len(resolved), 1)
        self.assertEqual(resolved[0]["walk_min"], 0)

    def test_weather_hero_condition_containment(self):
        """Verifies that long weather conditions stay strictly inside the weather hero card."""
        widget = WeatherHeroWidget(show_details=True, border=True)

        for h in (480, 600):
            # In weather.json, weather_hero card is rect(20, y0, 525, y1)
            card_rect = Rect(20, 80, 525, 80 + (260 if h == 600 else 180))

            captured_texts = []
            img = Image.new("RGB", (800, h), "white")
            raw_draw = ImageDraw.Draw(img)
            draw = ScaledDraw(raw_draw, 1.0)

            orig_text = raw_draw.text

            def hooked_text(
                xy,
                text,
                *args,
                _rd=raw_draw,
                _cap=captured_texts,
                _orig=orig_text,
                **kwargs,
            ):
                bbox = _rd.textbbox(xy, text, font=kwargs.get("font"))
                _cap.append((text, xy, bbox))
                return _orig(xy, text, *args, **kwargs)

            raw_draw.text = hooked_text  # type: ignore[method-assign]

            wx = get_mock_weather_data()
            object.__setattr__(wx, "condition", "Thunderstorm with heavy hail")
            object.__setattr__(wx, "temp", 102)
            object.__setattr__(wx, "temp_max", 105)
            object.__setattr__(wx, "temp_min", 78)

            ctx = RenderContext(
                now=datetime(2026, 10, 12, 14, 0),
                weather_data=wx,
                width=800,
                height=h,
            )

            widget.render(draw, card_rect, ctx)

            # Check all captured texts
            for text, _xy, bbox in captured_texts:
                self.assertLessEqual(
                    bbox[2],
                    card_rect.x1 - 10,
                    f"Text {text!r} overflowed card right border (right={bbox[2]} > max={card_rect.x1 - 10}) at height={h}",
                )

    def test_header_widget_subtitle_containment(self):
        """Verifies that long header subtitles do not collide with battery/time elements."""
        long_sub = "VERY LONG DETAILED SUBTITLE EXCEEDING NORMAL BOUNDS FOR ADVERSARIAL TESTING"
        header = HeaderWidget(title="MAIN TITLE", subtitle=long_sub)

        captured_texts = []
        img = Image.new("RGB", (800, 480), "white")
        raw_draw = ImageDraw.Draw(img)
        draw = ScaledDraw(raw_draw, 1.0)

        orig_text = raw_draw.text

        def hooked_text(
            xy,
            text,
            *args,
            _rd=raw_draw,
            _cap=captured_texts,
            _orig=orig_text,
            **kwargs,
        ):
            bbox = _rd.textbbox(xy, text, font=kwargs.get("font"))
            _cap.append((text, xy, bbox))
            return _orig(xy, text, *args, **kwargs)

        raw_draw.text = hooked_text  # type: ignore[method-assign]

        ctx = RenderContext(
            now=datetime(2026, 10, 12, 14, 0),
            batt_level=85,
            is_charging=True,
            width=800,
            height=480,
        )

        header_rect = Rect(20, 10, 780, 72)
        header.render(draw, header_rect, ctx)

        sub_boxes = [
            bbox for text, _, bbox in captured_texts if text.startswith("VERY LONG")
        ]
        batt_boxes = [bbox for text, _, bbox in captured_texts if "%" in text]

        if sub_boxes and batt_boxes:
            sub_right = sub_boxes[0][2]
            batt_left = batt_boxes[0][0]
            self.assertLess(
                sub_right,
                batt_left,
                f"Subtitle right edge ({sub_right}) collided with battery indicator ({batt_left})",
            )


if __name__ == "__main__":
    unittest.main()
