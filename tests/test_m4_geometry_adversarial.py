"""Adversarial Layout Geometry, Dead Space & Text Containment Stress Test.

Specialized challenger test suite verifying:
- Dead space elimination in y=70..424 (480h) and y=70..542 (600h)
- 1-stop, 2-stop, 3-stop column geometry across morning & evening views
- Bounded card bottoms vs touch bar divider (y <= 544 for 600h, y <= 424 for 480h)
- Text containment under ultra-long, non-spaced, Unicode, and empty strings
- Default parameter parity (location_config=None vs LocationConfig())
- Handling of edge stop counts (0 stops, 4 stops)
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import datetime
from typing import Any

# Ensure server directory is on sys.path
_SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "server"))
if _SERVER_DIR not in sys.path:
    sys.path.insert(0, _SERVER_DIR)

from canvas import ScaledDraw  # noqa: E402
from evening_view import render_evening_view  # noqa: E402
from location import LOCATION_STORE, LocationConfig, reset_location_config  # noqa: E402
from morning_view import render_morning_view  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402


class DrawRecorder:
    """Interception wrapper to record all geometric shapes and text bounding boxes."""

    def __init__(self, width: int = 800, height: int = 480):
        self.width = width
        self.height = height
        self.img = Image.new("RGB", (width, height), "white")
        self.draw = ScaledDraw(ImageDraw.Draw(self.img), 1.0)
        self.rectangles: list[tuple[float, float, float, float]] = []
        self.rounded_rectangles: list[tuple[float, float, float, float]] = []
        self.texts: list[dict[str, Any]] = []

        self._orig_rect = ImageDraw.ImageDraw.rectangle
        self._orig_rrect = ImageDraw.ImageDraw.rounded_rectangle
        self._orig_text = ImageDraw.ImageDraw.text

    def __enter__(self) -> DrawRecorder:
        recorder = self

        def m_rect(d_self: Any, xy: Any, *a: Any, **k: Any) -> Any:
            recorder.rectangles.append(tuple(xy))
            return recorder._orig_rect(d_self, xy, *a, **k)

        def m_rrect(d_self: Any, xy: Any, *a: Any, **k: Any) -> Any:
            recorder.rounded_rectangles.append(tuple(xy))
            return recorder._orig_rrect(d_self, xy, *a, **k)

        def m_text(d_self: Any, xy: Any, text: str, *a: Any, **k: Any) -> Any:
            font = k.get("font")
            try:
                bbox = d_self.textbbox(xy, text, font=font) if font else None
            except Exception:
                bbox = None
            recorder.texts.append({"xy": tuple(xy), "text": str(text), "bbox": bbox})
            return recorder._orig_text(d_self, xy, text, *a, **k)

        ImageDraw.ImageDraw.rectangle = m_rect
        ImageDraw.ImageDraw.rounded_rectangle = m_rrect
        ImageDraw.ImageDraw.text = m_text
        return self

    def __exit__(self, *args: Any) -> None:
        ImageDraw.ImageDraw.rectangle = self._orig_rect
        ImageDraw.ImageDraw.rounded_rectangle = self._orig_rrect
        ImageDraw.ImageDraw.text = self._orig_text

    @property
    def all_containers(self) -> list[tuple[float, float, float, float]]:
        return self.rounded_rectangles + self.rectangles


class TestM4AdversarialGeometry(unittest.TestCase):
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

    def test_dead_space_elimination_morning_480_and_600(self):
        """Checks morning view without Citi Bike spans y=70..424 (480h) and y=70..542 (600h)."""
        for h, expected_y1 in [(480, 424), (600, 542)]:
            with DrawRecorder(800, h) as rec:
                render_morning_view(
                    rec.draw,
                    stops_data={},
                    citibike_data=[],
                    now=datetime(2026, 10, 11, 8, 30),
                    batt_level=80,
                    is_charging=False,
                    is_mock=False,
                    width=800,
                    height=h,
                )
                hero_cards = [
                    c
                    for c in rec.rounded_rectangles
                    if c[1] == 70 and c[3] == expected_y1
                ]
                self.assertGreaterEqual(
                    len(hero_cards),
                    1,
                    f"No hero cards found spanning y=70..{expected_y1} at height {h}",
                )
                for c in hero_cards:
                    self.assertEqual(c[1], 70)
                    self.assertEqual(c[3], expected_y1)

    def test_evening_cards_clear_touch_bar_divider(self):
        """Checks evening view hero cards strictly stay above touch bar divider at 428 / 548."""
        for h, max_y1 in [(480, 426), (600, 544)]:
            for cb in [
                [],
                [
                    {
                        "name": "Station",
                        "ebikes": 5,
                        "classic": 2,
                        "docks": 8,
                        "walk_min": 3,
                    }
                ],
            ]:
                with DrawRecorder(800, h) as rec:
                    render_evening_view(
                        rec.draw,
                        stops_data={},
                        citibike_data=cb,
                        now=datetime(2026, 10, 11, 18, 30),
                        batt_level=80,
                        is_charging=False,
                        is_mock=False,
                        width=800,
                        height=h,
                    )
                    hero_cards = [
                        c
                        for c in rec.rounded_rectangles
                        if c[1] in (70, 80) and c[3] > 200
                    ]
                    for c in hero_cards:
                        self.assertLessEqual(
                            c[3],
                            max_y1,
                            f"Evening card bottom {c[3]} exceeds max allowed {max_y1} (height={h}, cb={bool(cb)})",
                        )

    def test_column_layouts_1_2_3_stops_morning_empty_cb(self):
        """Verifies 1-stop (760px), 2-stop (370px each), 3-stop (244px each) column layout."""
        stops_1 = [{"id": "1", "name": "Washington & 9th", "walk_min": 5}]
        stops_2 = [
            {"id": "1", "name": "Washington & 9th", "walk_min": 5},
            {"id": "2", "name": "Clinton & 9th", "walk_min": 3},
        ]
        stops_3 = [
            {"id": "1", "name": "Washington & 9th", "walk_min": 5},
            {"id": "2", "name": "Clinton & 9th", "walk_min": 3},
            {"id": "3", "name": "Washington & 11th", "walk_min": 6},
        ]

        # 1-stop
        with DrawRecorder(800, 480) as rec:
            render_morning_view(
                rec.draw,
                stops_data={},
                citibike_data=[],
                now=datetime(2026, 10, 11, 8, 30),
                batt_level=80,
                is_charging=False,
                is_mock=False,
                width=800,
                height=480,
                stops=stops_1,
            )
            cards = [c for c in rec.rounded_rectangles if c[1] == 70 and c[3] == 424]
            self.assertEqual(len(cards), 1)
            self.assertEqual(cards[0], (20.0, 70.0, 780.0, 424.0))

        # 2-stop
        with DrawRecorder(800, 480) as rec:
            render_morning_view(
                rec.draw,
                stops_data={},
                citibike_data=[],
                now=datetime(2026, 10, 11, 8, 30),
                batt_level=80,
                is_charging=False,
                is_mock=False,
                width=800,
                height=480,
                stops=stops_2,
            )
            cards = [c for c in rec.rounded_rectangles if c[1] == 70 and c[3] == 424]
            self.assertEqual(len(cards), 2)
            self.assertEqual(cards[0], (20.0, 70.0, 390.0, 424.0))
            self.assertEqual(cards[1], (410.0, 70.0, 780.0, 424.0))

        # 3-stop
        with DrawRecorder(800, 480) as rec:
            render_morning_view(
                rec.draw,
                stops_data={},
                citibike_data=[],
                now=datetime(2026, 10, 11, 8, 30),
                batt_level=80,
                is_charging=False,
                is_mock=False,
                width=800,
                height=480,
                stops=stops_3,
            )
            cards = [c for c in rec.rounded_rectangles if c[1] == 70 and c[3] == 424]
            self.assertEqual(len(cards), 3)
            self.assertEqual(cards[0], (20.0, 70.0, 264.0, 424.0))
            self.assertEqual(cards[1], (278.0, 70.0, 522.0, 424.0))
            self.assertEqual(cards[2], (536.0, 70.0, 780.0, 424.0))

        # 3-stop tall 600h
        with DrawRecorder(800, 600) as rec:
            render_morning_view(
                rec.draw,
                stops_data={},
                citibike_data=[],
                now=datetime(2026, 10, 11, 8, 30),
                batt_level=80,
                is_charging=False,
                is_mock=False,
                width=800,
                height=600,
                stops=stops_3,
            )
            cards = [c for c in rec.rounded_rectangles if c[1] == 70 and c[3] == 542]
            self.assertEqual(len(cards), 3)
            self.assertEqual(cards[0], (20.0, 70.0, 264.0, 542.0))
            self.assertEqual(cards[1], (278.0, 70.0, 522.0, 542.0))
            self.assertEqual(cards[2], (536.0, 70.0, 780.0, 542.0))

    def test_clamped_stops_behavior(self):
        """Verifies passing >3 stops clamps cleanly to 3 stops without exceeding boundaries."""
        stops_4 = [
            {"id": "1", "name": "Stop 1", "walk_min": 1},
            {"id": "2", "name": "Stop 2", "walk_min": 2},
            {"id": "3", "name": "Stop 3", "walk_min": 3},
            {"id": "4", "name": "Stop 4", "walk_min": 4},
        ]
        with DrawRecorder(800, 480) as rec:
            render_morning_view(
                rec.draw,
                stops_data={},
                citibike_data=[],
                now=datetime(2026, 10, 11, 8, 30),
                batt_level=80,
                is_charging=False,
                is_mock=False,
                width=800,
                height=480,
                stops=stops_4,
            )
            cards = [c for c in rec.rounded_rectangles if c[1] == 70 and c[3] == 424]
            self.assertEqual(len(cards), 3)
            self.assertEqual(cards[2][2], 780.0)

    def test_text_containment_under_unbroken_and_unicode_strings(self):
        """Adversarially stresses text containment using 120-char continuous string and Unicode."""
        unbroken_long = "W" * 120
        unicode_long = "Café St 🚲 & Metro Bus 🚌 " * 10
        cfg_adv = LocationConfig(
            route="ROUTE-EXTREME-EXPRESS-126",
            destination=unbroken_long,
            location_name=unicode_long,
            city="NEW-YORK-METRO-DISTRICT",
        )
        stops_adv = [
            {
                "id": "1001",
                "name": unbroken_long,
                "subtitle": unicode_long,
                "walk_min": 999,
            },
            {
                "id": "1002",
                "name": unicode_long,
                "subtitle": unbroken_long,
                "walk_min": 0,
            },
        ]
        s_data = {
            "1001": [
                {
                    "route": unbroken_long,
                    "destination": unicode_long,
                    "eta": "in 999 mins (ContinuousUnbrokenScheduleTextWithoutSpaces)",
                    "vehicle_id": "99999",
                }
            ]
        }
        cb_adv = [
            {
                "name": unbroken_long,
                "ebikes": 99,
                "classic": 99,
                "docks": 99,
                "walk_min": 99,
            }
        ]

        for view_fn in [render_morning_view, render_evening_view]:
            for h in [480, 600]:
                for cb in [[], cb_adv]:
                    with DrawRecorder(800, h) as rec:
                        view_fn(
                            rec.draw,
                            stops_data=s_data,
                            citibike_data=cb,
                            now=datetime(2026, 10, 11, 8, 30),
                            batt_level=99,
                            is_charging=True,
                            is_mock=True,
                            width=800,
                            height=h,
                            location_config=cfg_adv,
                            stops=stops_adv,
                        )

                        for item in rec.texts:
                            bbox = item["bbox"]
                            text = item["text"]
                            xy = item["xy"]
                            if not bbox:
                                continue
                            left, top, right, bottom = bbox

                            # Screen bounds check
                            self.assertLessEqual(
                                right,
                                800,
                                f"Text {text[:30]!r} right edge {right} > 800 in {view_fn.__name__} (h={h})",
                            )
                            self.assertGreaterEqual(
                                left,
                                0,
                                f"Text {text[:30]!r} left edge {left} < 0 in {view_fn.__name__} (h={h})",
                            )
                            self.assertLessEqual(
                                bottom,
                                h,
                                f"Text {text[:30]!r} bottom edge {bottom} > {h} in {view_fn.__name__} (h={h})",
                            )
                            self.assertGreaterEqual(
                                top,
                                0,
                                f"Text {text[:30]!r} top edge {top} < 0 in {view_fn.__name__} (h={h})",
                            )

                            # Enclosing container bounds check
                            tx, ty = xy
                            enclosing = [
                                c
                                for c in rec.all_containers
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
                                    f"Text {text[:30]!r} right {right} > container {c} in {view_fn.__name__}",
                                )
                                self.assertLessEqual(
                                    bottom,
                                    c[3] + 1,
                                    f"Text {text[:30]!r} bottom {bottom} > container {c} in {view_fn.__name__}",
                                )

    def test_default_parity_pixel_and_text_equivalence(self):
        """Verifies strict pixel equivalence between location_config=None and LocationConfig()."""
        reset_location_config()
        fixed_dt = datetime(2026, 10, 11, 8, 30, 0)
        cb_mock = [
            {
                "name": "Clinton & 9th",
                "ebikes": 5,
                "classic": 2,
                "docks": 8,
                "walk_min": 3,
            }
        ]

        test_cases = [
            ("morning_cb_480", render_morning_view, cb_mock, 480),
            ("morning_nocb_480", render_morning_view, [], 480),
            ("morning_cb_600", render_morning_view, cb_mock, 600),
            ("morning_nocb_600", render_morning_view, [], 600),
            ("evening_cb_480", render_evening_view, cb_mock, 480),
            ("evening_nocb_480", render_evening_view, [], 480),
            ("evening_cb_600", render_evening_view, cb_mock, 600),
            ("evening_nocb_600", render_evening_view, [], 600),
        ]

        for name, view_fn, cb, h in test_cases:
            with DrawRecorder(800, h) as r1:
                view_fn(
                    r1.draw,
                    stops_data={},
                    citibike_data=cb,
                    now=fixed_dt,
                    batt_level=80,
                    is_charging=False,
                    is_mock=False,
                    width=800,
                    height=h,
                    location_config=None,
                )
            with DrawRecorder(800, h) as r2:
                view_fn(
                    r2.draw,
                    stops_data={},
                    citibike_data=cb,
                    now=fixed_dt,
                    batt_level=80,
                    is_charging=False,
                    is_mock=False,
                    width=800,
                    height=h,
                    location_config=LocationConfig(),
                )

            diff_texts = [
                (t1["text"], t2["text"])
                for t1, t2 in zip(r1.texts, r2.texts)
                if t1["text"] != t2["text"]
            ]
            self.assertEqual(
                diff_texts,
                [],
                f"Text differences detected between None and LocationConfig() in {name}",
            )
            self.assertEqual(
                list(r1.img.getdata()),
                list(r2.img.getdata()),
                f"Pixel discrepancy detected between None and LocationConfig() in {name}",
            )


if __name__ == "__main__":
    unittest.main()
