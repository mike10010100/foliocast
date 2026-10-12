"""
Declarative E-Ink Design Language & Widget Layout Engine.
Provides layout containers (VStack, HStack, Box) and reusable high-contrast
widgets for transit, weather, metrics, and Home Assistant / IoT telemetry.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from canvas import (
    HEIGHT,
    STOPS,
    WIDTH,
    draw_battery_indicator,
    draw_bottom_button_bar,
    draw_brightness_button,
    draw_header_badge,
    draw_mock_badge,
    draw_status_strip,
    ellipsize_to_width,
    get_font,
    mock_badge_width,
)
from data_sources import resolve_field_path
from weather import WeatherSnapshot
from weather_icons import draw_weather_icon


@dataclass(frozen=True)
class Rect:
    """Bounding rectangle in logical design coordinates."""

    x0: int
    y0: int
    x1: int
    y1: int

    @property
    def w(self) -> int:
        return max(0, self.x1 - self.x0)

    @property
    def h(self) -> int:
        return max(0, self.y1 - self.y0)

    def inset(self, pad_x: int, pad_y: Optional[int] = None) -> "Rect":
        if pad_y is None:
            pad_y = pad_x
        return Rect(
            x0=self.x0 + pad_x,
            y0=self.y0 + pad_y,
            x1=max(self.x0 + pad_x, self.x1 - pad_x),
            y1=max(self.y0 + pad_y, self.y1 - pad_y),
        )


@dataclass
class RenderContext:
    """Telemetry data and rendering state provided to widgets during canvas drawing."""

    now: datetime
    stops_data: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    stop_status: dict[str, str] = field(default_factory=dict)
    citibike_data: list[dict[str, Any]] = field(default_factory=list)
    weather_data: Optional[WeatherSnapshot] = None
    custom_data: dict[str, Any] = field(default_factory=dict)
    batt_level: Optional[int] = None
    is_charging: bool = False
    presentation: str = "interactive"
    status_note: str = ""
    active_view: str = "morning"
    available_views: list[str] = field(default_factory=list)
    is_mock: bool = False
    width: int = WIDTH
    height: int = HEIGHT


class Widget:
    """Base class for all dashboard UI widgets."""

    def render(self, draw: Any, rect: Rect, ctx: RenderContext) -> None:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Universal Layout Containers
# ---------------------------------------------------------------------------


class LayoutNode:
    """A node in the declarative layout tree."""

    def __init__(
        self,
        flex: float = 1.0,
        fixed_size: Optional[int] = None,
        padding: int = 0,
        gap: int = 0,
        padding_x: Optional[int] = None,
        padding_y: Optional[int] = None,
    ) -> None:
        self.flex = flex
        self.fixed_size = fixed_size
        self.padding = padding
        self.gap = gap
        self.padding_x = padding_x if padding_x is not None else padding
        self.padding_y = padding_y if padding_y is not None else padding

    def get_inner_rect(self, rect: Rect) -> Rect:
        if self.padding_x > 0 or self.padding_y > 0:
            return rect.inset(self.padding_x, self.padding_y)
        return rect

    def layout_and_render(self, draw: Any, rect: Rect, ctx: RenderContext) -> None:
        raise NotImplementedError


class WidgetNode(LayoutNode):
    """A leaf layout node that wraps a Widget."""

    def __init__(
        self,
        widget: Widget,
        flex: float = 1.0,
        fixed_size: Optional[int] = None,
        padding: int = 0,
        padding_x: Optional[int] = None,
        padding_y: Optional[int] = None,
    ) -> None:
        super().__init__(
            flex=flex,
            fixed_size=fixed_size,
            padding=padding,
            padding_x=padding_x,
            padding_y=padding_y,
        )
        self.widget = widget

    def layout_and_render(self, draw: Any, rect: Rect, ctx: RenderContext) -> None:
        r = self.get_inner_rect(rect)
        self.widget.render(draw, r, ctx)


class VStack(LayoutNode):
    """Vertical stack container that divides height among child elements."""

    def __init__(
        self,
        children: Optional[list[LayoutNode]] = None,
        flex: float = 1.0,
        fixed_size: Optional[int] = None,
        padding: int = 0,
        gap: int = 0,
        padding_x: Optional[int] = None,
        padding_y: Optional[int] = None,
    ) -> None:
        super().__init__(
            flex=flex,
            fixed_size=fixed_size,
            padding=padding,
            gap=gap,
            padding_x=padding_x,
            padding_y=padding_y,
        )
        self.children = children or []

    def layout_and_render(self, draw: Any, rect: Rect, ctx: RenderContext) -> None:
        if not self.children:
            return

        r = self.get_inner_rect(rect)
        total_h = r.h
        total_gaps = (len(self.children) - 1) * self.gap
        avail_h = max(0, total_h - total_gaps)

        # Allocate fixed heights first
        fixed_sum = sum(c.fixed_size for c in self.children if c.fixed_size is not None)
        flex_avail_h = max(0, avail_h - fixed_sum)
        flex_sum = sum(
            c.flex for c in self.children if c.fixed_size is None and c.flex > 0
        )
        flex_sum = flex_sum if flex_sum > 0 else 1.0

        curr_y = r.y0
        for i, child in enumerate(self.children):
            if child.fixed_size is not None:
                child_h = child.fixed_size
            else:
                child_h = int(round((child.flex / flex_sum) * flex_avail_h))

            # Ensure last child fills available remainder
            if i == len(self.children) - 1:
                child_h = max(0, r.y1 - curr_y)

            child_rect = Rect(r.x0, curr_y, r.x1, min(r.y1, curr_y + child_h))
            child.layout_and_render(draw, child_rect, ctx)
            curr_y += child_h + self.gap


class HStack(LayoutNode):
    """Horizontal stack container that divides width among child elements."""

    def __init__(
        self,
        children: Optional[list[LayoutNode]] = None,
        flex: float = 1.0,
        fixed_size: Optional[int] = None,
        padding: int = 0,
        gap: int = 0,
        padding_x: Optional[int] = None,
        padding_y: Optional[int] = None,
    ) -> None:
        super().__init__(
            flex=flex,
            fixed_size=fixed_size,
            padding=padding,
            gap=gap,
            padding_x=padding_x,
            padding_y=padding_y,
        )
        self.children = children or []

    def layout_and_render(self, draw: Any, rect: Rect, ctx: RenderContext) -> None:
        if not self.children:
            return

        r = self.get_inner_rect(rect)
        total_w = r.w
        total_gaps = (len(self.children) - 1) * self.gap
        avail_w = max(0, total_w - total_gaps)

        # Allocate fixed widths first
        fixed_sum = sum(c.fixed_size for c in self.children if c.fixed_size is not None)
        flex_avail_w = max(0, avail_w - fixed_sum)
        flex_sum = sum(
            c.flex for c in self.children if c.fixed_size is None and c.flex > 0
        )
        flex_sum = flex_sum if flex_sum > 0 else 1.0

        curr_x = r.x0
        for i, child in enumerate(self.children):
            if child.fixed_size is not None:
                child_w = child.fixed_size
            else:
                child_w = int(round((child.flex / flex_sum) * flex_avail_w))

            if i == len(self.children) - 1:
                child_w = max(0, r.x1 - curr_x)

            child_rect = Rect(curr_x, r.y0, min(r.x1, curr_x + child_w), r.y1)
            child.layout_and_render(draw, child_rect, ctx)
            curr_x += child_w + self.gap


class Box(LayoutNode):
    """Container with an e-ink card border and background fill."""

    def __init__(
        self,
        child: LayoutNode,
        border: bool = True,
        fill: Optional[str] = None,
        radius: int = 6,
        border_width: int = 1,
        padding: int = 8,
        padding_x: Optional[int] = None,
        padding_y: Optional[int] = None,
        flex: float = 1.0,
        fixed_size: Optional[int] = None,
    ) -> None:
        super().__init__(
            flex=flex,
            fixed_size=fixed_size,
            padding=padding,
            padding_x=padding_x,
            padding_y=padding_y,
        )
        self.child = child
        self.border = border
        self.fill = fill
        self.radius = radius
        self.border_width = border_width

    def layout_and_render(self, draw: Any, rect: Rect, ctx: RenderContext) -> None:
        if self.fill or self.border:
            draw.rounded_rectangle(
                [rect.x0, rect.y0, rect.x1, rect.y1],
                radius=self.radius,
                fill=self.fill or "white",
                outline="black" if self.border else None,
                width=self.border_width if self.border else 0,
            )
        inner = self.get_inner_rect(rect)
        self.child.layout_and_render(draw, inner, ctx)


# ---------------------------------------------------------------------------
# Universal Widgets
# ---------------------------------------------------------------------------


class HeaderWidget(Widget):
    """Standard dashboard header with badge, title, time, date, battery, and mock tag."""

    def __init__(
        self,
        badge: str = "TRANSIT",
        title: str = "HOBOKEN DASHBOARD",
        subtitle: str = "LIVE TELEMETRY",
        show_time: bool = True,
        show_battery: bool = True,
        show_date: bool = True,
        show_brightness: bool = True,
        show_divider: bool = True,
    ) -> None:
        self.badge = badge
        self.title = title
        self.subtitle = subtitle
        self.show_time = show_time
        self.show_battery = show_battery
        self.show_date = show_date
        self.show_brightness = show_brightness
        self.show_divider = show_divider

    def render(self, draw: Any, rect: Rect, ctx: RenderContext) -> None:
        font_title = get_font(21, bold=True)
        font_sub = get_font(12, bold=False)
        font_time = get_font(18, bold=True)

        time_str = ctx.now.strftime("%-I:%M %p")
        date_str = ctx.now.strftime("%A, %b %-d")

        y_top = rect.y0 + (14 if rect.h >= 50 else max(1, (rect.h - 34) // 2))
        y_sub = y_top + 24

        # Top-right clock
        time_x = rect.x1
        if self.show_time:
            tb = draw.textbbox((0, 0), time_str, font=font_time)
            time_w = tb[2] - tb[0]
            time_x = rect.x1 - time_w
            draw.text((time_x, y_top + 1), time_str, fill="black", font=font_time)

        # Date string below time
        date_x = rect.x1
        if self.show_date:
            db = draw.textbbox((0, 0), date_str, font=font_sub)
            date_w = db[2] - db[0]
            date_x = rect.x1 - date_w
            draw.text((date_x, y_sub), date_str, fill="#555555", font=font_sub)

        # Brightness toggle button immediately to left of time and date
        time_date_left = min(time_x, date_x)
        bright_size = 30
        right_boundary = time_date_left
        if self.show_brightness:
            bright_x0 = time_date_left - bright_size - 10
            draw_brightness_button(draw, bright_x0, y_top + 2, size=bright_size)
            right_boundary = bright_x0

        # Mock badge if applicable
        if ctx.is_mock:
            font_mock = get_font(11, bold=True)
            mw = mock_badge_width(draw, font_mock)
            mock_x = int(right_boundary - mw - 10)
            draw_mock_badge(draw, mock_x, y_sub - 3, font=font_mock)
            right_boundary = mock_x

        # Battery indicator to left of brightness button / mock badge
        batt_x = right_boundary
        if self.show_battery and ctx.batt_level is not None:
            font_batt = get_font(13, bold=True)
            label = f"{ctx.batt_level}%"
            bbox = draw.textbbox((0, 0), label, font=font_batt)
            label_w = bbox[2] - bbox[0]
            bolt_w = 12 if ctx.is_charging else 0
            total_batt_w = bolt_w + label_w + 6 + 28 + 3
            batt_x = int(right_boundary - total_batt_w - 14)
            draw_battery_indicator(
                draw,
                batt_x,
                y_top + 2,
                ctx.batt_level,
                is_charging=ctx.is_charging,
                font=font_batt,
            )

        # Left badge + title
        bx1 = draw_header_badge(draw, rect.x0, y_top, self.badge, font_title, pad_x=12)
        title_text = ellipsize_to_width(
            draw, self.title, font_title, max(50, batt_x - bx1 - 20)
        )
        draw.text((bx1 + 12, y_top + 1), title_text, fill="black", font=font_title)
        draw.text((bx1 + 12, y_sub), self.subtitle, fill="#555555", font=font_sub)

        if self.show_divider:
            draw.line([(rect.x0, rect.y1), (rect.x1, rect.y1)], fill="black", width=2)


class MetricCardWidget(Widget):
    """
    Universal KPI / Metric Card:
    Displays a title, large value, unit, subtitle, and status pill.
    Can bind to custom_data, weather, battery, or transit fields.
    """

    def __init__(
        self,
        title: str,
        value: Any = None,
        source: Optional[str] = None,
        unit: str = "",
        subtitle: str = "",
        badge: Optional[str] = None,
        border: bool = True,
    ) -> None:
        self.title = title
        self.value = value
        self.source = source
        self.unit = unit
        self.subtitle = subtitle
        self.badge = badge
        self.border = border

    def _resolve_value(self, ctx: RenderContext) -> str:
        if self.source:
            # Check custom_data first
            val = resolve_field_path(ctx.custom_data, self.source)
            if val is not None:
                return str(val)
            # Check weather data
            if ctx.weather_data and self.source.startswith("weather."):
                w_field = self.source.split(".", 1)[1]
                val = getattr(ctx.weather_data, w_field, None)
                if val is not None:
                    return str(val)
            # Check special variables
            if self.source in ("battery", "battery_level"):
                return f"{ctx.batt_level or 0}"
            if self.source == "temp" and ctx.weather_data:
                return f"{ctx.weather_data.temp}"
            if self.source in ("precip_prob", "rain") and ctx.weather_data:
                return f"{ctx.weather_data.precip_prob}"
        if self.value is not None:
            return str(self.value)
        return "--"

    def render(self, draw: Any, rect: Rect, ctx: RenderContext) -> None:
        if self.border:
            draw.rounded_rectangle(
                [rect.x0, rect.y0, rect.x1, rect.y1],
                radius=10,
                fill="white",
                outline="black",
                width=2,
            )

        is_tall_card = rect.h >= 140
        pill_h = 42 if is_tall_card else 0

        if is_tall_card:
            draw.rounded_rectangle(
                [rect.x0, rect.y0, rect.x1, rect.y0 + pill_h],
                radius=10,
                fill="#f2f2f2",
                outline="black",
                width=2,
            )
            draw.rectangle(
                [rect.x0 + 1, rect.y0 + pill_h - 10, rect.x1 - 1, rect.y0 + pill_h],
                fill="#f2f2f2",
            )
            draw.line(
                [(rect.x0, rect.y0 + pill_h), (rect.x1, rect.y0 + pill_h)],
                fill="black",
                width=2,
            )

            font_pill_title = get_font(15, bold=True)
            draw.text(
                (rect.x0 + 14, rect.y0 + 11),
                self.title.upper(),
                fill="black",
                font=font_pill_title,
            )

            if self.badge:
                font_badge = get_font(11, bold=True)
                bb = draw.textbbox((0, 0), self.badge, font=font_badge)
                bw = bb[2] - bb[0]
                draw.rounded_rectangle(
                    [rect.x1 - bw - 20, rect.y0 + 10, rect.x1 - 10, rect.y0 + 32],
                    radius=4,
                    fill="black",
                )
                draw.text(
                    (rect.x1 - bw - 15, rect.y0 + 14),
                    self.badge,
                    fill="white",
                    font=font_badge,
                )
        else:
            pad = 12
            font_label = get_font(12, bold=True)
            draw.text(
                (rect.x0 + pad, rect.y0 + pad),
                self.title.upper(),
                fill="#555555",
                font=font_label,
            )
            if self.badge:
                font_badge = get_font(10, bold=True)
                bb = draw.textbbox((0, 0), self.badge, font=font_badge)
                bw = bb[2] - bb[0] + 12
                bx0 = rect.x1 - pad - bw
                draw.rounded_rectangle(
                    [bx0, rect.y0 + pad - 2, rect.x1 - pad, rect.y0 + pad + 14],
                    radius=4,
                    fill="black",
                )
                draw.text(
                    (bx0 + 6, rect.y0 + pad), self.badge, fill="white", font=font_badge
                )

        val_str = self._resolve_value(ctx)
        body_top = rect.y0 + (pill_h + 12 if is_tall_card else 26)

        is_precip = self.source in ("precip_prob", "rain") or self.title.upper() in (
            "PRECIPITATION",
            "RAIN",
        )
        if is_precip and is_tall_card:
            try:
                prob = int(val_str.rstrip("%"))
            except Exception:
                prob = 0

            is_very_tall = rect.h >= 240
            icon_s = 64 if is_very_tall else 52
            draw_weather_icon(
                draw,
                rect.x0 + (16 if is_very_tall else 14),
                body_top + 2,
                size=icon_s,
                glyph="UMBRELLA",
            )
            pval_str = f"{val_str}%" if not val_str.endswith("%") else val_str
            text_x = rect.x0 + (86 if is_very_tall else 72)
            max_text_x = rect.x1 - 16
            base_font_size = 56 if is_very_tall else 48
            font_size = base_font_size
            font_val = get_font(font_size, bold=True)
            tb = draw.textbbox((text_x, 0), pval_str, font=font_val)
            while tb[2] > max_text_x and font_size > 20:
                font_size -= 2
                font_val = get_font(font_size, bold=True)
                tb = draw.textbbox((text_x, 0), pval_str, font=font_val)

            y_offset = (base_font_size - font_size) // 3
            draw.text(
                (text_x, body_top - 2 + y_offset),
                pval_str,
                fill="black",
                font=font_val,
            )

            font_sub = get_font(12, bold=False)
            sub_text = self.subtitle or "Rain probability today"
            sub_y = body_top + (66 if is_very_tall else 62)
            draw.text(
                (rect.x0 + 16, sub_y),
                sub_text,
                fill="#555555",
                font=font_sub,
            )

            if is_very_tall:
                p_div_y = body_top + 84 + 14  # Matches div_y in WeatherHeroWidget
                draw.line(
                    [(rect.x0 + 16, p_div_y), (rect.x1 - 16, p_div_y)],
                    fill="#e0e0e0",
                    width=1,
                )
                meter_y0 = p_div_y + 14
                meter_h = 16
            else:
                meter_y0 = body_top + 84
                meter_h = 10

            mx0 = rect.x0 + 16
            mx1 = rect.x1 - 16
            meter_w = mx1 - mx0
            draw.rounded_rectangle(
                [mx0, meter_y0, mx1, meter_y0 + meter_h],
                radius=5 if is_very_tall else 4,
                fill="#eeeeee",
                outline="black",
                width=1,
            )
            fill_w = int(round(meter_w * (max(0, min(100, prob)) / 100.0)))
            if fill_w > 0:
                draw.rounded_rectangle(
                    [mx0, meter_y0, mx0 + fill_w, meter_y0 + meter_h],
                    radius=5 if is_very_tall else 4,
                    fill="black",
                )

            font_meter = get_font(10, bold=False)
            draw.text(
                (mx0, meter_y0 + meter_h + 3), "0%", fill="#777777", font=font_meter
            )
            bb_50 = draw.textbbox((0, 0), "50%", font=font_meter)
            w_50 = bb_50[2] - bb_50[0]
            draw.text(
                (mx0 + (meter_w - w_50) // 2, meter_y0 + meter_h + 3),
                "50%",
                fill="#777777",
                font=font_meter,
            )
            bb_100 = draw.textbbox((0, 0), "100%", font=font_meter)
            w_100 = bb_100[2] - bb_100[0]
            draw.text(
                (mx1 - w_100, meter_y0 + meter_h + 3),
                "100%",
                fill="#777777",
                font=font_meter,
            )

            if is_very_tall:
                if prob >= 70:
                    p_note = "Precipitation highly likely"
                elif prob >= 40:
                    p_note = "Scattered showers possible"
                elif prob >= 20:
                    p_note = "Isolated slight chance"
                else:
                    p_note = "Dry commute expected"
                draw.text(
                    (mx0, meter_y0 + meter_h + 26),
                    p_note,
                    fill="#222222",
                    font=get_font(12, bold=True),
                )

            bot_y0 = rect.y1 - 38
            bot_y1 = rect.y1 - 10
            if prob < 20:
                p_text = "DRY CONDITIONS"
                bg_col = "#f4f4f4"
                fg_col = "black"
            elif prob < 60:
                p_text = "CHANCE OF RAIN"
                bg_col = "#f4f4f4"
                fg_col = "black"
            else:
                p_text = "RAIN EXPECTED"
                bg_col = "black"
                fg_col = "white"

            draw.rounded_rectangle(
                [rect.x0 + 14, bot_y0, rect.x1 - 14, bot_y1],
                radius=6,
                fill=bg_col,
                outline="black",
                width=1,
            )
            font_pill = get_font(11, bold=True)
            p_bb = draw.textbbox((0, 0), p_text, font=font_pill)
            p_w = p_bb[2] - p_bb[0]
            draw.text(
                (rect.x0 + 14 + (rect.w - 28 - p_w) // 2, bot_y0 + 8),
                p_text,
                fill=fg_col,
                font=font_pill,
            )
            return

        pad = 12
        inner_w = rect.w - (pad * 2)
        font_val = get_font(44 if rect.h >= 110 else 36, bold=True)
        font_unit = get_font(18, bold=True)
        font_sub = get_font(11, bold=False)

        val_y = body_top
        vb = draw.textbbox((0, 0), val_str, font=font_val)
        vw = vb[2] - vb[0]
        draw.text((rect.x0 + pad, val_y), val_str, fill="black", font=font_val)

        if self.unit:
            draw.text(
                (rect.x0 + pad + vw + 4, val_y + 16),
                self.unit,
                fill="#444444",
                font=font_unit,
            )

        if self.subtitle:
            sub_y = rect.y1 - pad - 12
            sub_text = ellipsize_to_width(draw, self.subtitle, font_sub, inner_w)
            draw.text((rect.x0 + pad, sub_y), sub_text, fill="#666666", font=font_sub)


class EntityListWidget(Widget):
    """
    Displays a vertical list of entity states (Home Assistant entities or sensor rows).
    Each row has an entity name, optional secondary label, and state pill.
    """

    def __init__(self, entities: list[dict[str, Any]], border: bool = True) -> None:
        self.entities = entities
        self.border = border

    def render(self, draw: Any, rect: Rect, ctx: RenderContext) -> None:
        if self.border:
            draw.rounded_rectangle(
                [rect.x0, rect.y0, rect.x1, rect.y1],
                radius=6,
                fill="white",
                outline="black",
                width=1,
            )

        if not self.entities:
            return

        pad = 10
        row_h = (rect.h - (pad * 2)) // len(self.entities)
        font_name = get_font(13, bold=True)
        font_state = get_font(12, bold=True)
        font_sub = get_font(10, bold=False)

        for i, ent in enumerate(self.entities):
            y0 = rect.y0 + pad + i * row_h
            if i > 0:
                draw.line(
                    [(rect.x0 + pad, y0), (rect.x1 - pad, y0)], fill="#e0e0e0", width=1
                )

            name = ent.get("name", "Unknown")
            sub = ent.get("subtitle", "")
            raw_state = ent.get("state")
            source = ent.get("source")
            if source and not raw_state:
                raw_state = resolve_field_path(ctx.custom_data, source)
            state_str = str(raw_state or "off").upper()

            # Name and subtitle
            draw.text((rect.x0 + pad, y0 + 4), name, fill="black", font=font_name)
            if sub:
                draw.text((rect.x0 + pad, y0 + 20), sub, fill="#666666", font=font_sub)

            # State pill
            sb = draw.textbbox((0, 0), state_str, font=font_state)
            sw = sb[2] - sb[0] + 16
            sx0 = rect.x1 - pad - sw
            is_active = state_str in ("ON", "OPEN", "ACTIVE", "RUNNING", "HOME")
            draw.rounded_rectangle(
                [sx0, y0 + 6, rect.x1 - pad, y0 + 24],
                radius=4,
                fill="black" if is_active else "#f0f0f0",
                outline="black" if is_active else "#cccccc",
                width=1,
            )
            draw.text(
                (sx0 + 8, y0 + 8),
                state_str,
                fill="white" if is_active else "black",
                font=font_state,
            )


class TextNoticeWidget(Widget):
    """Formatted text card for travel alerts, announcements, or custom notices."""

    def __init__(
        self,
        title: str,
        body: str,
        border: bool = True,
        badge: Optional[str] = "NOTICE",
    ) -> None:
        self.title = title
        self.body = body
        self.border = border
        self.badge = badge

    def render(self, draw: Any, rect: Rect, ctx: RenderContext) -> None:
        if self.border:
            draw.rounded_rectangle(
                [rect.x0, rect.y0, rect.x1, rect.y1],
                radius=6,
                fill="white",
                outline="black",
                width=1,
            )

        pad = 12
        font_title = get_font(14, bold=True)
        font_body = get_font(12, bold=False)

        y = rect.y0 + pad
        if self.badge:
            font_badge = get_font(10, bold=True)
            bb = draw.textbbox((0, 0), self.badge, font=font_badge)
            bw = bb[2] - bb[0] + 12
            draw.rounded_rectangle(
                [rect.x0 + pad, y, rect.x0 + pad + bw, y + 16],
                radius=4,
                fill="black",
            )
            draw.text(
                (rect.x0 + pad + 6, y + 2), self.badge, fill="white", font=font_badge
            )
            draw.text(
                (rect.x0 + pad + bw + 8, y), self.title, fill="black", font=font_title
            )
            y += 24
        else:
            draw.text((rect.x0 + pad, y), self.title, fill="black", font=font_title)
            y += 20

        # Body text (wrapped)
        body_wrapped = ellipsize_to_width(
            draw, self.body, font_body, rect.w - (pad * 2)
        )
        draw.text((rect.x0 + pad, y), body_wrapped, fill="#333333", font=font_body)


class ButtonBarWidget(Widget):
    """
    Bottom tactile button bar or dormant status strip.
    Dynamically renders buttons for the active view set when interactive,
    or overpaints the status strip when dormant/idle.
    """

    def __init__(self, buttons: Optional[list[tuple[str, str]]] = None) -> None:
        self.custom_buttons = buttons

    def render(self, draw: Any, rect: Rect, ctx: RenderContext) -> None:
        if ctx.presentation != "interactive":
            draw_status_strip(draw, ctx.width, ctx.height, note=ctx.status_note)
            return

        if self.custom_buttons:
            # Custom buttons provided
            btn_list = self.custom_buttons
        elif ctx.available_views and len(ctx.available_views) > 1:
            # Generate buttons based on available views (up to 3 views + refresh)
            btn_list = []
            for v in ctx.available_views[:3]:
                label = v.replace("_", " ").upper()
                btn_list.append((label, v))
            btn_list.append(("↻ REFRESH", "refresh"))
        else:
            # Default to standard BUSES, CITI BIKE, and WEATHER
            draw_bottom_button_bar(
                draw,
                ctx.width,
                ctx.height,
                active_view=ctx.active_view,
            )
            return

        # Render custom button set
        is_tall = ctx.height >= 580
        btn_y0 = ctx.height - (44 if is_tall else 38)
        btn_y1 = ctx.height - (10 if is_tall else 8)
        btn_h = btn_y1 - btn_y0
        draw.line(
            [(20, btn_y0 - 8), (ctx.width - 20, btn_y0 - 8)], fill="#bbbbbb", width=1
        )

        start_x = 20
        total_w = ctx.width - 40
        gap = 10
        font = get_font(12, bold=True)
        col_w = (total_w - (len(btn_list) - 1) * gap) // len(btn_list)

        for i, (label, target_view) in enumerate(btn_list):
            is_active = target_view == ctx.active_view
            display_label = f"● {label}" if is_active else label
            x0 = start_x + i * (col_w + gap)
            x1 = x0 + col_w
            bg = "black" if is_active else "#f4f4f4"
            fg = "white" if is_active else "black"
            draw.rounded_rectangle(
                [x0, btn_y0, x1, btn_y1], radius=6, fill=bg, outline="black", width=2
            )
            bbox = draw.textbbox((0, 0), display_label, font=font)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
            draw.text(
                (x0 + (col_w - tw) // 2, btn_y0 + (btn_h - th) // 2 - 1),
                display_label,
                fill=fg,
                font=font,
            )


# ---------------------------------------------------------------------------
# Weather Widgets
# ---------------------------------------------------------------------------


class WeatherHeroWidget(Widget):
    """Prominent weather card showing current temperature, conditions, and daily stats."""

    def __init__(self, show_details: bool = True, border: bool = True) -> None:
        self.show_details = show_details
        self.border = border

    def render(self, draw: Any, rect: Rect, ctx: RenderContext) -> None:
        if self.border:
            draw.rounded_rectangle(
                [rect.x0, rect.y0, rect.x1, rect.y1],
                radius=10,
                fill="white",
                outline="black",
                width=2,
            )

        pill_h = 42
        draw.rounded_rectangle(
            [rect.x0, rect.y0, rect.x1, rect.y0 + pill_h],
            radius=10,
            fill="#f2f2f2",
            outline="black",
            width=2,
        )
        draw.rectangle(
            [rect.x0 + 1, rect.y0 + pill_h - 10, rect.x1 - 1, rect.y0 + pill_h],
            fill="#f2f2f2",
        )
        draw.line(
            [(rect.x0, rect.y0 + pill_h), (rect.x1, rect.y0 + pill_h)],
            fill="black",
            width=2,
        )

        font_pill_title = get_font(15, bold=True)
        draw.text(
            (rect.x0 + 14, rect.y0 + 11),
            "CURRENT CONDITIONS",
            fill="black",
            font=font_pill_title,
        )

        font_badge = get_font(11, bold=True)
        st_badge = "HOBOKEN, NJ"
        sbb = draw.textbbox((0, 0), st_badge, font=font_badge)
        sbw = sbb[2] - sbb[0]
        draw.rounded_rectangle(
            [rect.x1 - sbw - 22, rect.y0 + 10, rect.x1 - 10, rect.y0 + 32],
            radius=4,
            fill="black",
        )
        draw.text(
            (rect.x1 - sbw - 16, rect.y0 + 14),
            st_badge,
            fill="white",
            font=font_badge,
        )

        wx = ctx.weather_data
        if wx is None:
            font_msg = get_font(14, bold=True)
            draw.text(
                (rect.x0 + 16, rect.y0 + pill_h + 24),
                "Weather telemetry offline",
                fill="black",
                font=font_msg,
            )
            return

        body_top = rect.y0 + pill_h + (14 if rect.h >= 240 else 12)
        is_tall_hero = rect.h >= 240
        icon_size = 84 if is_tall_hero else (72 if rect.h >= 180 else 52)
        draw_weather_icon(
            draw,
            rect.x0 + (18 if is_tall_hero else 16),
            body_top - 2,
            size=icon_size,
            glyph=wx.condition_glyph,
        )

        # Temperature
        font_temp = get_font(
            72 if is_tall_hero else (60 if rect.h >= 180 else 48), bold=True
        )
        font_deg = get_font(
            28 if is_tall_hero else (24 if rect.h >= 180 else 20), bold=True
        )
        temp_x = rect.x0 + icon_size + 24
        temp_str = f"{wx.temp}"
        draw.text((temp_x, body_top - 6), temp_str, fill="black", font=font_temp)
        tb = draw.textbbox((0, 0), temp_str, font=font_temp)
        tw = tb[2] - tb[0]
        draw.text((temp_x + tw + 2, body_top), "°F", fill="black", font=font_deg)

        # Condition & High/Low right of temperature
        hl_x = temp_x + tw + (40 if is_tall_hero else 44)
        font_cond = get_font(22 if is_tall_hero else 18, bold=True)
        font_detail_bold = get_font(14 if is_tall_hero else 13, bold=True)
        draw.text((hl_x, body_top + 4), wx.condition, fill="black", font=font_cond)
        draw.text(
            (hl_x, body_top + (34 if is_tall_hero else 28)),
            f"High: {wx.temp_max}°  •  Low: {wx.temp_min}°",
            fill="#333333",
            font=font_detail_bold,
        )

        if is_tall_hero:
            # Divider below hero section
            div_y = body_top + icon_size + 14
            draw.line(
                [(rect.x0 + 16, div_y), (rect.x1 - 16, div_y)],
                fill="#e0e0e0",
                width=1,
            )

            # 3-column telemetry grid
            stat_y = div_y + 12
            col_w = (rect.w - 32) // 3
            c0_x = rect.x0 + 16
            c1_x = c0_x + col_w
            c2_x = c1_x + col_w

            font_stat_lbl = get_font(11, bold=True)
            font_stat_val = get_font(30, bold=True)
            font_stat_sub = get_font(12, bold=False)

            # Col 0: Feels like
            draw.text(
                (c0_x + 2, stat_y), "FEELS LIKE", fill="#666666", font=font_stat_lbl
            )
            draw.text(
                (c0_x + 2, stat_y + 18),
                f"{wx.apparent_temp}°",
                fill="black",
                font=font_stat_val,
            )
            draw.text(
                (c0_x + 2, stat_y + 56),
                f"Range: {wx.temp_min}°–{wx.temp_max}°",
                fill="#777777",
                font=font_stat_sub,
            )

            # Col 1: Humidity
            draw.line(
                [(c1_x - 6, div_y + 10), (c1_x - 6, div_y + 78)],
                fill="#e8e8e8",
                width=1,
            )
            draw.text(
                (c1_x + 8, stat_y), "HUMIDITY", fill="#666666", font=font_stat_lbl
            )
            draw.text(
                (c1_x + 8, stat_y + 18),
                f"{wx.humidity}%",
                fill="black",
                font=font_stat_val,
            )
            draw.text(
                (c1_x + 8, stat_y + 56),
                "Relative moisture",
                fill="#777777",
                font=font_stat_sub,
            )

            # Col 2: Wind
            draw.line(
                [(c2_x - 6, div_y + 10), (c2_x - 6, div_y + 78)],
                fill="#e8e8e8",
                width=1,
            )
            draw.text(
                (c2_x + 8, stat_y), "WIND SPEED", fill="#666666", font=font_stat_lbl
            )
            draw.text(
                (c2_x + 8, stat_y + 18),
                f"{wx.wind_speed} mph",
                fill="black",
                font=font_stat_val,
            )
            draw.text(
                (c2_x + 8, stat_y + 56),
                "Hudson waterfront",
                fill="#777777",
                font=font_stat_sub,
            )
        else:
            # Metrics row for compact card
            metrics_y = body_top + 78
            font_detail = get_font(13, bold=False)
            metrics_str = f"Feels like {wx.apparent_temp}°   •   Humidity: {wx.humidity}%   •   Wind: {wx.wind_speed} mph"
            draw.text(
                (rect.x0 + 18, metrics_y), metrics_str, fill="#444444", font=font_detail
            )

        # Bottom decision / status advisory banner
        if rect.h >= 180:
            bot_y0 = rect.y1 - 38
            bot_y1 = rect.y1 - 10
            draw.rounded_rectangle(
                [rect.x0 + 14, bot_y0, rect.x1 - 14, bot_y1],
                radius=6,
                fill="#f4f4f4",
                outline="black",
                width=1,
            )
            if wx.precip_prob >= 50:
                status_text = "▲ RAIN EXPECTED TODAY • CARRY UMBRELLA"
            elif wx.wind_speed >= 15:
                status_text = "● BREEZY ALONG THE HUDSON WATERFRONT"
            elif wx.temp <= 38:
                status_text = "● CHILLY COMMUTE • WINTER COAT RECOMMENDED"
            elif wx.temp >= 85:
                status_text = "● HIGH HEAT • STAY HYDRATED & COOL"
            else:
                status_text = "● FAVORABLE COMMUTE CONDITIONS IN HOBOKEN"

            st_bb = draw.textbbox((0, 0), status_text, font=font_badge)
            st_w = st_bb[2] - st_bb[0]
            draw.text(
                (rect.x0 + 14 + (rect.w - 28 - st_w) // 2, bot_y0 + 8),
                status_text,
                fill="black",
                font=font_badge,
            )


class WeatherForecastWidget(Widget):
    """Horizontal forecast strip showing upcoming daily weather forecasts."""

    def __init__(self, days: int = 4, border: bool = True) -> None:
        self.days = days
        self.border = border

    def render(self, draw: Any, rect: Rect, ctx: RenderContext) -> None:
        is_tall = rect.h >= 140
        if self.border:
            draw.rounded_rectangle(
                [rect.x0, rect.y0, rect.x1, rect.y1],
                radius=10,
                fill="white",
                outline="black",
                width=2,
            )
            banner_h = 28 if is_tall else 24
            draw.rounded_rectangle(
                [rect.x0, rect.y0, rect.x1, rect.y0 + banner_h],
                radius=10,
                fill="#f4f4f4",
                outline="black",
                width=2,
            )
            draw.rectangle(
                [
                    rect.x0 + 1,
                    rect.y0 + (14 if is_tall else 12),
                    rect.x1 - 1,
                    rect.y0 + banner_h,
                ],
                fill="#f4f4f4",
            )
            draw.line(
                [(rect.x0, rect.y0 + banner_h), (rect.x1, rect.y0 + banner_h)],
                fill="black",
                width=1,
            )
            banner_title = f"{self.days}-DAY OUTLOOK • MILE SQUARE EXTENDED FORECAST"
            draw.text(
                (
                    rect.x0 + 16 if is_tall else rect.x0 + 14,
                    rect.y0 + (7 if is_tall else 5),
                ),
                banner_title,
                fill="#444444",
                font=get_font(12 if is_tall else 11, bold=True),
            )
            fc_body_y0 = rect.y0 + banner_h
        else:
            fc_body_y0 = rect.y0

        wx = ctx.weather_data
        forecasts = wx.forecast if (wx and wx.forecast) else ()
        if not forecasts:
            return

        items = list(forecasts[: self.days])
        count = len(items)
        col_w = rect.w // count

        font_day = get_font(14 if is_tall else 13, bold=True)
        font_cond = get_font(12 if is_tall else 11, bold=False)
        font_hl = get_font(16 if is_tall else 13, bold=True)
        font_precip = get_font(12 if is_tall else 11, bold=True)

        for i, f in enumerate(items):
            cx0 = rect.x0 + i * col_w
            if i > 0:
                draw.line(
                    [
                        (cx0, fc_body_y0 + 8 if is_tall else fc_body_y0 + 6),
                        (cx0, rect.y1 - (8 if is_tall else 6)),
                    ],
                    fill="#dddddd",
                    width=1,
                )

            # Day name
            draw.text(
                (cx0 + (16 if is_tall else 14), fc_body_y0 + (12 if is_tall else 8)),
                f.day_name.upper(),
                fill="black",
                font=font_day,
            )

            # Weather icon
            icon_s = 56 if is_tall else (46 if rect.h >= 100 else 36)
            draw_weather_icon(
                draw,
                cx0 + (14 if is_tall else 12),
                fc_body_y0 + (38 if is_tall else 26),
                size=icon_s,
                glyph=f.condition_glyph,
            )

            # High / Low
            text_x = cx0 + (78 if is_tall else 66)
            draw.text(
                (text_x, fc_body_y0 + (38 if is_tall else 26)),
                f"{f.temp_max}° / {f.temp_min}°",
                fill="black",
                font=font_hl,
            )

            # Condition
            cond_short = ellipsize_to_width(
                draw, f.condition, font_cond, col_w - (86 if is_tall else 74)
            )
            draw.text(
                (text_x, fc_body_y0 + (64 if is_tall else 44)),
                cond_short,
                fill="#555555",
                font=font_cond,
            )

            # Rain probability
            rain_str = (
                f"{f.precip_probability}% rain"
                if f.precip_probability > 0
                else "0% rain"
            )
            draw.text(
                (text_x, fc_body_y0 + (86 if is_tall else 60)),
                rain_str,
                fill="#111111",
                font=font_precip,
            )


# ---------------------------------------------------------------------------
# Transit Widgets
# ---------------------------------------------------------------------------


class BusHeroWidget(Widget):
    """Prominent Route 126 bus departure countdown cards for specified stops."""

    def __init__(self, stops: Optional[list[str]] = None, route: str = "126") -> None:
        self.stops = stops or ["20512", "20494"]
        self.route = route

    def render(self, draw: Any, rect: Rect, ctx: RenderContext) -> None:
        from evening_view import render_evening_view

        # Delegate to battle-tested evening bus hero layout
        render_evening_view(
            draw,
            ctx.stops_data,
            ctx.citibike_data,
            ctx.now,
            batt_level=ctx.batt_level,
            is_charging=ctx.is_charging,
            is_mock=ctx.is_mock,
            stop_status=ctx.stop_status,
            width=ctx.width,
            height=ctx.height,
        )


class BusBarWidget(Widget):
    """Compact horizontal bus arrivals bar."""

    def __init__(self, stops: Optional[list[str]] = None, route: str = "126") -> None:
        self.stops = stops or ["20512", "20494"]
        self.route = route

    def render(self, draw: Any, rect: Rect, ctx: RenderContext) -> None:
        pad = 8
        draw.rounded_rectangle(
            [rect.x0, rect.y0, rect.x1, rect.y1],
            radius=6,
            fill="#f9f9f9",
            outline="black",
            width=1,
        )

        font_label = get_font(11, bold=True)
        font_stop = get_font(13, bold=True)
        font_eta = get_font(13, bold=True)

        draw.text(
            (rect.x0 + pad + 2, rect.y0 + 6),
            f"ROUTE {self.route} DEPARTURES TO NYC PORT AUTHORITY",
            fill="#555555",
            font=font_label,
        )

        col_w = (rect.w - (pad * 2)) // len(self.stops)
        for i, sid in enumerate(self.stops):
            cx0 = rect.x0 + pad + i * col_w
            stop_info = next(
                (s for s in STOPS if s["id"] == sid), {"name": f"Stop #{sid}"}
            )
            trips = ctx.stops_data.get(sid, [])
            eta_str = trips[0].get("eta", "No arrivals") if trips else "No arrivals"

            s_name = stop_info.get("name", sid)
            draw.text((cx0 + 2, rect.y0 + 26), s_name, fill="black", font=font_stop)
            draw.text((cx0 + 2, rect.y0 + 44), eta_str, fill="black", font=font_eta)


class CitiBikeHeroWidget(Widget):
    """Large Citi Bike cards showing available e-bikes, classic bikes, docks, and walk times."""

    def __init__(self, stations: Optional[list[str]] = None) -> None:
        self.stations = stations

    def render(self, draw: Any, rect: Rect, ctx: RenderContext) -> None:
        from morning_view import render_morning_view

        # Delegate to battle-tested morning view hero layout
        render_morning_view(
            draw,
            ctx.stops_data,
            ctx.citibike_data,
            ctx.now,
            batt_level=ctx.batt_level,
            is_charging=ctx.is_charging,
            is_mock=ctx.is_mock,
            stop_status=ctx.stop_status,
            width=ctx.width,
            height=ctx.height,
        )


class CitiBikeBarWidget(Widget):
    """Compact horizontal strip of Citi Bike station availability."""

    def __init__(self, stations: Optional[list[str]] = None) -> None:
        self.stations = stations

    def render(self, draw: Any, rect: Rect, ctx: RenderContext) -> None:
        if not ctx.citibike_data:
            return

        pad = 8
        draw.rounded_rectangle(
            [rect.x0, rect.y0, rect.x1, rect.y1],
            radius=6,
            fill="#f9f9f9",
            outline="black",
            width=1,
        )

        font_label = get_font(11, bold=True)
        draw.text(
            (rect.x0 + pad + 2, rect.y0 + 6),
            "CITI BIKE NEARBY DOCKS & E-BIKE AVAILABILITY",
            fill="#555555",
            font=font_label,
        )

        stations = ctx.citibike_data[:3]
        col_w = (rect.w - (pad * 2)) // len(stations)
        font_name = get_font(12, bold=True)
        font_stat = get_font(12, bold=False)

        for i, st in enumerate(stations):
            cx0 = rect.x0 + pad + i * col_w
            name = st.get("name", "Station")
            ebikes = st.get("ebikes", 0)
            docks = st.get("docks", 0)
            draw.text((cx0 + 2, rect.y0 + 26), name, fill="black", font=font_name)
            stat_text = f"⚡ {ebikes} e-bikes  •  {docks} docks"
            draw.text((cx0 + 2, rect.y0 + 44), stat_text, fill="black", font=font_stat)
