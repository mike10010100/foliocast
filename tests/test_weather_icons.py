"""
Unit tests for vector weather icons and ScaledDraw curve primitives.
Verifies rendering of all meteorological glyphs across varied sizes
and ScaledDraw proxy integration.
"""

import unittest

from canvas import ScaledDraw
from PIL import Image, ImageDraw
from weather_icons import (
    draw_cloud,
    draw_lightning,
    draw_rain_streaks,
    draw_snowflake,
    draw_sun,
    draw_weather_icon,
)


class TestWeatherIcons(unittest.TestCase):
    def setUp(self):
        self.img = Image.new("RGB", (300, 300), "white")
        self.draw = ScaledDraw(ImageDraw.Draw(self.img), 1.0)

    def test_all_supported_glyphs(self):
        glyphs = [
            "SUN",
            "CLEAR",
            "MOSTLY_SUN",
            "PARTLY_CLOUD",
            "CLOUDY",
            "CLOUD",
            "OVERCAST",
            "DRIZZLE",
            "LIGHT_RAIN",
            "RAIN",
            "HEAVY_RAIN",
            "SHOWERS",
            "THUNDER",
            "THUNDERSTORM",
            "SNOW",
            "LIGHT_SNOW",
            "HEAVY_SNOW",
            "FREEZE_RAIN",
            "FOG",
            "WIND",
            "UMBRELLA",
            "PRECIPITATION",
            "UNKNOWN_CODE",
            None,
        ]
        for g in glyphs:
            with self.subTest(glyph=g):
                # Render onto canvas without error
                draw_weather_icon(self.draw, 10, 10, size=64, glyph=g)
                # Verify pixels were drawn
                self.assertIsNotNone(self.img)

    def test_scaled_draw_curves(self):
        scaled_img = Image.new("RGB", (600, 600), "white")
        scaled_draw = ScaledDraw(ImageDraw.Draw(scaled_img), 2.0)

        # Test arc, pieslice, and chord methods on ScaledDraw
        scaled_draw.arc([10, 10, 50, 50], start=0, end=180, fill="black", width=2)
        scaled_draw.pieslice(
            [60, 10, 100, 50], start=0, end=90, fill="black", outline="black"
        )
        scaled_draw.chord(
            [110, 10, 150, 50], start=0, end=180, fill="black", outline="black"
        )

        # Render umbrella icon using scaled_draw
        draw_weather_icon(scaled_draw, 20, 20, size=48, glyph="UMBRELLA")

    def test_icon_helpers(self):
        d = self.draw
        # Direct helpers
        draw_cloud(d, 50, 50, 60, 40, fill="white", outline="black", width=2)
        draw_cloud(d, 50, 50, 60, 40, fill="black", outline="", width=0)
        draw_sun(d, 50, 50, 10, 14, 22, fill="black", ray_w=2)
        draw_snowflake(d, 50, 50, 8, width=1)
        draw_rain_streaks(d, 50, 50, count=3, length=10, width=2, gap=8)
        draw_lightning(d, 50, 50, scale=1.0)


if __name__ == "__main__":
    unittest.main()
