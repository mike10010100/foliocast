#!/usr/bin/env python3
"""
Reproduction script for precipitation 100% collision in weather dashboard.

Checks the containment invariant for the precipitation metric card:
When precipitation probability reaches 100%, the rendered percentage glyphs
and progress meter scale labels must stay strictly inside the card boundaries
with proper padding (at least 14px inner margin from the right edge), across
both standard (800x480) and tall / Kindle PW (800x600) layouts and system fonts.
"""

import os
import sys
from datetime import datetime

# Ensure server module is in python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "server"))

import dashboard_dsl
from dashboard_dsl import MetricCardWidget, Rect, RenderContext, WidgetNode
from dashboards import REGISTRY, parse_layout_node
from PIL import Image, ImageDraw, ImageFont
from weather import get_mock_weather_data


def find_metric_card(node, rect):
    from dashboard_dsl import HStack, VStack

    inner = node.get_inner_rect(rect)
    if isinstance(node, WidgetNode) and isinstance(node.widget, MetricCardWidget):
        return inner, node.widget
    elif isinstance(node, VStack):
        non_flex_h = sum(c.fixed_size or 0 for c in node.children)
        gap_total = (len(node.children) - 1) * node.gap
        avail_h = max(0, inner.h - non_flex_h - gap_total)
        total_flex = sum(c.flex for c in node.children if c.fixed_size is None) or 1.0
        curr_y = inner.y0
        for c in node.children:
            ch = (
                c.fixed_size
                if c.fixed_size is not None
                else int(round((c.flex / total_flex) * avail_h))
            )
            res = find_metric_card(c, Rect(inner.x0, curr_y, inner.x1, curr_y + ch))
            if res:
                return res
            curr_y += ch + node.gap
    elif isinstance(node, HStack):
        non_flex_w = sum(c.fixed_size or 0 for c in node.children)
        gap_total = (len(node.children) - 1) * node.gap
        avail_w = max(0, inner.w - non_flex_w - gap_total)
        total_flex = sum(c.flex for c in node.children if c.fixed_size is None) or 1.0
        curr_x = inner.x0
        for c in node.children:
            cw = (
                c.fixed_size
                if c.fixed_size is not None
                else int(round((c.flex / total_flex) * avail_w))
            )
            res = find_metric_card(c, Rect(curr_x, inner.y0, curr_x + cw, inner.y1))
            if res:
                return res
            curr_x += cw + node.gap
    return None


def run_reproduction():
    spec = REGISTRY.get("weather")
    if not spec:
        print("ERROR: weather specification not found in REGISTRY")
        sys.exit(1)

    root = parse_layout_node(spec.layout_data)

    failures = []
    print("=== Precipitation 100% Collision Check ===")

    fonts_to_test = [("System Font", None)]
    dejavu_path = "/Users/mike10010100/.local/share/mise/installs/python/3.11.14/lib/python3.11/site-packages/matplotlib/mpl-data/fonts/ttf/DejaVuSans-Bold.ttf"
    if os.path.exists(dejavu_path):
        fonts_to_test.append(("DejaVu Font (Linux/Docker)", dejavu_path))

    for font_label, font_path in fonts_to_test:
        for h, label in [(480, "Standard 800x480"), (600, "Kindle 4:3 800x600")]:
            test_tag = f"{label} - {font_label}"
            card_rect, widget = find_metric_card(root, Rect(0, 0, 800, h))

            # Instrument drawing to capture text bounding boxes
            captured_texts = []
            img = Image.new("RGB", (800, h), color="white")
            raw_draw = ImageDraw.Draw(img)

            orig_text = raw_draw.text

            def hooked_text(
                xy,
                text,
                *a,
                _rd=raw_draw,
                _cap=captured_texts,
                _orig=orig_text,
                **k,
            ):
                bbox = _rd.textbbox(xy, text, font=k.get("font"))
                _cap.append((xy, text, bbox, k.get("font")))
                return _orig(xy, text, *a, **k)

            raw_draw.text = hooked_text  # type: ignore

            wx = get_mock_weather_data()
            object.__setattr__(wx, "precip_prob", 100)

            ctx = RenderContext(
                now=datetime.now(),
                weather_data=wx,
                width=800,
                height=h,
            )

            if font_path:
                orig_get_font = dashboard_dsl.get_font

                def fake_get_font(size, bold=False, _fp=font_path):
                    f = ImageFont.truetype(_fp, size)
                    f._transit_path = _fp
                    f._transit_size = size
                    return f

                dashboard_dsl.get_font = fake_get_font
                try:
                    widget.render(raw_draw, card_rect, ctx)
                finally:
                    dashboard_dsl.get_font = orig_get_font
            else:
                widget.render(raw_draw, card_rect, ctx)

            # Check captured texts
            for _xy, text, bbox, _font in captured_texts:
                if "100%" in text or text == "100%":
                    text_right = bbox[2]
                    margin = card_rect.x1 - text_right
                    print(
                        f"[{test_tag}] text={text!r}: x0={bbox[0]}, x1={text_right} vs card.x1={card_rect.x1} (margin={margin}px)"
                    )
                    if margin < 14:
                        failures.append(
                            f"[{test_tag}] Text {text!r} margin to card border is {margin}px (< 14px required; collision/overflow!)"
                        )

    if failures:
        print("\nFAILURES DETECTED:")
        for f in failures:
            print(f"  ❌ {f}")
        return False
    else:
        print(
            "\n✅ All precipitation texts are cleanly contained within card boundaries!"
        )
        return True


if __name__ == "__main__":
    success = run_reproduction()
    sys.exit(0 if success else 1)
