import os
import shutil
import tempfile
import unittest
from datetime import datetime

from canvas import ScaledDraw
from dashboard_dsl import (
    Box,
    BusBarWidget,
    ButtonBarWidget,
    CitiBikeBarWidget,
    EntityListWidget,
    HeaderWidget,
    HStack,
    MetricCardWidget,
    Rect,
    RenderContext,
    TextNoticeWidget,
    VStack,
    WeatherForecastWidget,
    WeatherHeroWidget,
    WidgetNode,
)
from dashboards import (
    DashboardError,
    DashboardRegistry,
    parse_layout_node,
    parse_widget,
    validate_dashboard_spec,
)
from PIL import Image, ImageDraw
from weather import get_mock_weather_data


class TestDashboardDSL(unittest.TestCase):
    def setUp(self):
        self.img = Image.new("RGB", (800, 480), "white")
        self.draw = ScaledDraw(ImageDraw.Draw(self.img), 1.0)
        self.ctx = RenderContext(
            now=datetime(2026, 10, 11, 8, 30),
            stops_data={
                "20512": [{"route": "126", "destination": "NY", "eta": "5 mins"}],
                "20494": [{"route": "126", "destination": "NY", "eta": "12 mins"}],
            },
            stop_status={"20512": "ok", "20494": "ok"},
            citibike_data=[{"name": "Clinton & 9th", "ebikes": 4, "docks": 10}],
            weather_data=get_mock_weather_data(),
            custom_data={"sensor": {"temp": 71, "door": "open"}},
            batt_level=85,
            is_charging=True,
            presentation="interactive",
            status_note="TEST NOTE",
            active_view="weather",
            available_views=["weather", "bus_focus"],
            is_mock=True,
            width=800,
            height=480,
        )

    def test_rect_properties_and_inset(self):
        r = Rect(10, 20, 110, 120)
        self.assertEqual(r.w, 100)
        self.assertEqual(r.h, 100)
        inner = r.inset(5)
        self.assertEqual(inner.x0, 15)
        self.assertEqual(inner.y0, 25)
        self.assertEqual(inner.x1, 105)
        self.assertEqual(inner.y1, 115)

    def test_layout_vstack_and_hstack(self):
        root = VStack(
            padding_x=20,
            padding_y=10,
            gap=10,
            children=[
                WidgetNode(HeaderWidget(title="TEST HEADER"), fixed_size=50),
                HStack(
                    flex=1.0,
                    gap=8,
                    padding_x=5,
                    children=[
                        WidgetNode(
                            MetricCardWidget(
                                title="TEMP", source="weather.temp", unit="°F"
                            )
                        ),
                        WidgetNode(
                            MetricCardWidget(title="DOOR", source="sensor.door")
                        ),
                    ],
                ),
                WidgetNode(ButtonBarWidget(), fixed_size=40),
            ],
        )
        # Verify it renders cleanly without raising exceptions
        root.layout_and_render(self.draw, Rect(0, 0, 800, 480), self.ctx)

    def test_box_container(self):
        box = Box(
            child=WidgetNode(TextNoticeWidget(title="Alert", body="Test message")),
            border=True,
            fill="#f0f0f0",
            padding=6,
        )
        box.layout_and_render(self.draw, Rect(20, 20, 300, 120), self.ctx)

    def test_header_widget_variations(self):
        # Full header
        hw = HeaderWidget(badge="TEST", title="TITLE", subtitle="SUB")
        hw.render(self.draw, Rect(20, 10, 780, 60), self.ctx)

        # Minimal header without battery or time
        hw_min = HeaderWidget(show_time=False, show_battery=False, show_date=False)
        hw_min.render(self.draw, Rect(20, 10, 780, 60), self.ctx)

    def test_metric_card_sources(self):
        card1 = MetricCardWidget(title="BATTERY", source="battery", unit="%")
        card1.render(self.draw, Rect(20, 20, 200, 120), self.ctx)

        card2 = MetricCardWidget(
            title="PRECIP", source="precip_prob", unit="%", badge="ALERT"
        )
        card2.render(self.draw, Rect(20, 20, 200, 120), self.ctx)

        card3 = MetricCardWidget(title="LITERAL", value="Active", subtitle="Sub text")
        card3.render(self.draw, Rect(20, 20, 200, 120), self.ctx)

    def test_entity_list_widget(self):
        el = EntityListWidget(
            entities=[
                {"name": "Front Door", "subtitle": "Sensor 1", "state": "open"},
                {"name": "Living Room AC", "source": "sensor.door"},
            ]
        )
        el.render(self.draw, Rect(20, 20, 300, 180), self.ctx)

    def test_weather_widgets(self):
        hero = WeatherHeroWidget()
        hero.render(self.draw, Rect(20, 20, 500, 200), self.ctx)

        # Weather hero on tall display (Kindle PW5)
        hero.render(self.draw, Rect(20, 20, 520, 320), self.ctx)

        # Weather hero with high precip advisory
        wx_rain = get_mock_weather_data()
        object.__setattr__(wx_rain, "precip_prob", 75)
        ctx_rain = RenderContext(now=datetime.now(), weather_data=wx_rain)
        hero.render(self.draw, Rect(20, 20, 500, 200), ctx_rain)
        hero.render(self.draw, Rect(20, 20, 520, 320), ctx_rain)

        # Weather hero with wind advisory
        wx_wind = get_mock_weather_data()
        object.__setattr__(wx_wind, "precip_prob", 10)
        object.__setattr__(wx_wind, "wind_speed", 22)
        ctx_wind = RenderContext(now=datetime.now(), weather_data=wx_wind)
        hero.render(self.draw, Rect(20, 20, 500, 200), ctx_wind)
        hero.render(self.draw, Rect(20, 20, 520, 320), ctx_wind)

        # Weather hero with cold advisory
        wx_cold = get_mock_weather_data()
        object.__setattr__(wx_cold, "precip_prob", 5)
        object.__setattr__(wx_cold, "wind_speed", 5)
        object.__setattr__(wx_cold, "temp", 32)
        ctx_cold = RenderContext(now=datetime.now(), weather_data=wx_cold)
        hero.render(self.draw, Rect(20, 20, 500, 200), ctx_cold)
        hero.render(self.draw, Rect(20, 20, 520, 320), ctx_cold)

        # Weather hero with heat advisory
        wx_hot = get_mock_weather_data()
        object.__setattr__(wx_hot, "precip_prob", 5)
        object.__setattr__(wx_hot, "wind_speed", 5)
        object.__setattr__(wx_hot, "temp", 92)
        ctx_hot = RenderContext(now=datetime.now(), weather_data=wx_hot)
        hero.render(self.draw, Rect(20, 20, 500, 200), ctx_hot)
        hero.render(self.draw, Rect(20, 20, 520, 320), ctx_hot)

        # Forecast with border and without border (tall and compact)
        forecast = WeatherForecastWidget(days=4, border=True)
        forecast.render(self.draw, Rect(20, 180, 780, 360), self.ctx)
        forecast.render(self.draw, Rect(20, 180, 780, 290), self.ctx)

        forecast_noborder = WeatherForecastWidget(days=3, border=False)
        forecast_noborder.render(self.draw, Rect(20, 180, 780, 290), self.ctx)

        # Compact forecast
        forecast_compact = WeatherForecastWidget(days=4, border=True)
        forecast_compact.render(self.draw, Rect(20, 180, 780, 260), self.ctx)

        # Offline weather hero
        ctx_no_wx = RenderContext(now=datetime.now())
        hero.render(self.draw, Rect(20, 20, 500, 160), ctx_no_wx)

        # Tall precipitation metric cards across probability tiers
        card_dry = MetricCardWidget(
            title="PRECIPITATION", source="precip_prob", unit="%", badge="RADAR"
        )
        card_dry.render(self.draw, Rect(20, 20, 240, 240), self.ctx)
        card_dry.render(self.draw, Rect(20, 20, 240, 300), self.ctx)

        # Mid probability tier (compact and very tall)
        wx_mid = get_mock_weather_data()
        object.__setattr__(wx_mid, "precip_prob", 40)
        ctx_mid = RenderContext(now=datetime.now(), weather_data=wx_mid)
        card_dry.render(self.draw, Rect(20, 20, 240, 240), ctx_mid)
        card_dry.render(self.draw, Rect(20, 20, 240, 300), ctx_mid)

        # Low probability tier (isolated slight chance)
        wx_low = get_mock_weather_data()
        object.__setattr__(wx_low, "precip_prob", 25)
        ctx_low = RenderContext(now=datetime.now(), weather_data=wx_low)
        card_dry.render(self.draw, Rect(20, 20, 240, 300), ctx_low)

        # High probability tier
        card_dry.render(self.draw, Rect(20, 20, 240, 240), ctx_rain)
        card_dry.render(self.draw, Rect(20, 20, 240, 300), ctx_rain)

        # 100% precipitation edge case (compact tall and very tall)
        wx_100 = get_mock_weather_data()
        object.__setattr__(wx_100, "precip_prob", 100)
        ctx_100 = RenderContext(now=datetime.now(), weather_data=wx_100)
        card_dry.render(self.draw, Rect(20, 20, 240, 240), ctx_100)
        card_dry.render(self.draw, Rect(20, 20, 240, 300), ctx_100)

    def test_transit_widgets(self):
        bus_bar = BusBarWidget()
        bus_bar.render(self.draw, Rect(20, 20, 760, 90), self.ctx)

        bike_bar = CitiBikeBarWidget()
        bike_bar.render(self.draw, Rect(20, 100, 760, 170), self.ctx)

    def test_button_bar_widget_dormant_and_interactive(self):
        bb = ButtonBarWidget()
        # Interactive mode
        bb.render(self.draw, Rect(0, 440, 800, 480), self.ctx)

        # Dormant mode (should paint status strip)
        ctx_dormant = RenderContext(
            now=datetime.now(),
            presentation="dormant",
            status_note="SLEEPING UNTIL 6:00 AM",
            width=800,
            height=480,
        )
        bb.render(self.draw, Rect(0, 440, 800, 480), ctx_dormant)

        # Custom buttons
        bb_custom = ButtonBarWidget(buttons=[("HOME", "home"), ("LIGHT", "light")])
        bb_custom.render(self.draw, Rect(0, 440, 800, 480), self.ctx)


class TestDashboardRegistry(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.registry = DashboardRegistry(dashboards_dir=self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_builtins_present(self):
        self.assertIsNotNone(self.registry.get("morning"))
        self.assertIsNotNone(self.registry.get("evening"))
        self.assertIsNotNone(self.registry.get("weather"))
        self.assertIsNotNone(self.registry.get("bus_focus"))
        self.assertIsNotNone(self.registry.get("citibike_focus"))
        self.assertTrue(len(self.registry.list_all()) >= 5)

    def test_validation_errors(self):
        with self.assertRaises(DashboardError):
            validate_dashboard_spec("not a dict")
        with self.assertRaises(DashboardError):
            validate_dashboard_spec({"id": "Invalid ID!", "title": "Test"})
        with self.assertRaises(DashboardError):
            validate_dashboard_spec({"id": "test", "title": ""})
        with self.assertRaises(DashboardError):
            validate_dashboard_spec(
                {"id": "test", "title": "Test", "layout": "invalid"}
            )
        with self.assertRaises(DashboardError):
            parse_widget({"type": "nonexistent_widget_type"})
        with self.assertRaises(DashboardError):
            parse_layout_node("not a dict")
        with self.assertRaises(DashboardError):
            parse_layout_node({"type": "box"})  # missing child

    def test_save_and_reload_custom_dashboard(self):
        custom_spec_data = {
            "id": "my_board",
            "title": "My Custom Dashboard",
            "description": "Testing custom registry",
            "layout": {
                "type": "vstack",
                "children": [
                    {"type": "header", "title": "MY BOARD"},
                    {"type": "metric_card", "title": "TEST", "value": 42},
                ],
            },
        }
        saved = self.registry.save_custom_dashboard(custom_spec_data)
        self.assertEqual(saved.id, "my_board")
        self.assertFalse(saved.is_builtin)

        # Retrieve
        fetched = self.registry.get("my_board")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.title, "My Custom Dashboard")

        # Test hot reload on file change
        self.assertTrue(os.path.exists(fetched.file_path))
        custom_spec_data["title"] = "Updated Dashboard Title"
        with open(fetched.file_path, "w", encoding="utf-8") as f:
            import json

            json.dump(custom_spec_data, f)
        os.utime(fetched.file_path, (saved.file_mtime + 5, saved.file_mtime + 5))

        reloaded = self.registry.get("my_board")
        self.assertEqual(reloaded.title, "Updated Dashboard Title")

    def test_render_via_registry(self):
        img = Image.new("RGB", (800, 480), "white")
        draw = ScaledDraw(ImageDraw.Draw(img), 1.0)
        ctx = RenderContext(
            now=datetime.now(),
            weather_data=get_mock_weather_data(),
            width=800,
            height=480,
        )
        rendered = self.registry.render("weather", draw, ctx)
        self.assertTrue(rendered)

        # Non-existent dashboard returns False
        self.assertFalse(self.registry.render("nonexistent", draw, ctx))

    def test_header_widget_brightness_toggle(self):
        img = Image.new("RGB", (800, 480), "white")
        draw = ScaledDraw(ImageDraw.Draw(img), 1.0)
        ctx = RenderContext(
            now=datetime.now(),
            batt_level=85,
            is_charging=False,
            is_mock=True,
            width=800,
            height=480,
        )

        header_with_bright = HeaderWidget(show_brightness=True)
        header_with_bright.render(draw, Rect(20, 10, 780, 60), ctx)

        header_without_bright = HeaderWidget(show_brightness=False, show_divider=False)
        header_without_bright.render(draw, Rect(20, 10, 780, 60), ctx)

        # Parse from widget spec
        parsed = parse_widget(
            {"type": "header", "show_brightness": False, "show_divider": False}
        )
        self.assertIsInstance(parsed, HeaderWidget)
        self.assertFalse(parsed.show_brightness)
        self.assertFalse(parsed.show_divider)

    def test_button_bar_widget_views(self):
        img = Image.new("RGB", (800, 480), "white")
        draw = ScaledDraw(ImageDraw.Draw(img), 1.0)
        ctx = RenderContext(
            now=datetime.now(),
            presentation="interactive",
            active_view="weather",
            available_views=["evening", "morning", "weather"],
            width=800,
            height=480,
        )
        bar = ButtonBarWidget()
        bar.render(draw, Rect(20, 436, 780, 472), ctx)

        # Non-interactive falls back to status strip
        ctx_dormant = RenderContext(
            now=datetime.now(),
            presentation="dormant",
            status_note="CUSTOM DORMANT NOTE",
            width=800,
            height=480,
        )
        bar.render(draw, Rect(20, 436, 780, 472), ctx_dormant)

    def test_precipitation_100_percent_containment(self):
        """
        Regression test: When precipitation percentage hits 100%, text must not collide
        with the card's right boundary across standard and tall layout geometries.
        """
        card = MetricCardWidget(
            title="PRECIPITATION", source="precip_prob", unit="%", badge="RADAR"
        )
        wx_100 = get_mock_weather_data()
        object.__setattr__(wx_100, "precip_prob", 100)
        ctx = RenderContext(now=datetime.now(), weather_data=wx_100)

        for rect in [
            Rect(539, 72, 780, 290),  # Standard 800x480 card geometry (w=241, h=218)
            Rect(539, 72, 780, 365),  # Tall 800x600 card geometry (w=241, h=293)
            Rect(50, 50, 250, 280),  # Narrow 200px wide card
        ]:
            img = Image.new("RGB", (800, 600), "white")
            raw_draw = ImageDraw.Draw(img)
            captured = []
            orig_text = raw_draw.text

            def record_text(
                xy, text, *a, _rd=raw_draw, _cap=captured, _orig=orig_text, **k
            ):
                bb = _rd.textbbox(xy, text, font=k.get("font"))
                _cap.append((text, bb))
                return _orig(xy, text, *a, **k)

            raw_draw.text = record_text  # type: ignore
            card.render(raw_draw, rect, ctx)

            # Ensure all text inside card stays within right margin (rect.x1 - 14)
            for text, bbox in captured:
                if "100%" in text or text == "100%":
                    self.assertLessEqual(
                        bbox[2],
                        rect.x1 - 14,
                        f"Text {text!r} (right={bbox[2]}) exceeded inner margin of card {rect}",
                    )
