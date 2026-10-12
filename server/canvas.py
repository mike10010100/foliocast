import datetime
import math
import os
import re
from typing import Any, Optional

from PIL import ImageDraw, ImageFont

# Design-space canvas dimensions. All layout math in this module is expressed
# in this logical 800px-wide coordinate space; ScaledDraw translates it to the
# actual (possibly much larger) native canvas so we never resample a bitmap.
WIDTH = 800
HEIGHT = 480


class ScaledDraw:
    """
    A transparent ImageDraw proxy that renders a logical-coordinate layout onto
    a larger native canvas.

    Every view function draws in the 800px logical design space. Wrapping the
    real ImageDraw in this proxy lets us render at the panel's true resolution
    (e.g. 1648x1236 for a Kindle PW5) with crisp native text instead of
    LANCZOS-upscaling an 800px bitmap.

    Coordinates, outline widths and corner radii are multiplied by `scale`.
    Fonts are reconstructed at `size * scale` (cached) so glyphs are rendered
    natively. `textbbox` divides its result back into logical units so callers
    (and the ellipsize helper) keep operating in one consistent space.
    """

    def __init__(self, draw: ImageDraw.ImageDraw, scale: float = 1.0) -> None:
        self._d = draw
        self._s = float(scale)
        self._font_cache: dict[tuple[str, int], Any] = {}

    def _pt(self, p: Any) -> tuple[float, float]:
        return (p[0] * self._s, p[1] * self._s)

    def _box(self, xy: Any) -> Any:
        """Accepts [(x0,y0),(x1,y1)] or flat [x0,y0,x1,y1] and scales it."""
        if len(xy) == 4 and not hasattr(xy[0], "__len__"):
            return [xy[0] * self._s, xy[1] * self._s, xy[2] * self._s, xy[3] * self._s]
        return [self._pt(xy[0]), self._pt(xy[1])]

    def _outline(self, w: Optional[float]) -> Any:
        if w is None:
            return None
        return max(1, int(round(w * self._s)))

    def _font(self, font: Any) -> Any:
        if font is None or self._s == 1.0:
            return font
        path = getattr(font, "_transit_path", None)
        size = getattr(font, "_transit_size", None)
        if path is None or size is None:
            return font
        key = (path, size)
        cached = self._font_cache.get(key)
        if cached is not None:
            return cached
        try:
            scaled: Any = ImageFont.truetype(path, max(1, int(round(size * self._s))))
            try:
                scaled._transit_path = path
                scaled._transit_size = max(1, int(round(size * self._s)))
            except Exception:
                pass
        except Exception:
            scaled = font
        self._font_cache[key] = scaled
        return scaled

    def text(
        self, xy: Any, text: str, fill: Any = None, font: Any = None, **kwargs: Any
    ) -> None:
        self._d.text(self._pt(xy), text, fill=fill, font=self._font(font), **kwargs)

    def textbbox(
        self, xy: Any, text: str, font: Any = None, **kwargs: Any
    ) -> tuple[float, float, float, float]:
        bbox = self._d.textbbox(self._pt(xy), text, font=self._font(font), **kwargs)
        return tuple(v / self._s for v in bbox)  # type: ignore[return-value]

    def textlength(self, text: str, font: Any = None, **kwargs: Any) -> float:
        return self._d.textlength(text, font=self._font(font), **kwargs) / self._s

    def line(self, xy: Any, fill: Any = None, width: float = 1, **kwargs: Any) -> None:
        self._d.line(
            [self._pt(p) for p in xy], fill=fill, width=self._outline(width), **kwargs
        )

    def rectangle(
        self,
        xy: Any,
        fill: Any = None,
        outline: Any = None,
        width: float = 1,
        **kwargs: Any,
    ) -> None:
        self._d.rectangle(
            self._box(xy),
            fill=fill,
            outline=outline,
            width=self._outline(width),
            **kwargs,
        )

    def rounded_rectangle(
        self,
        xy: Any,
        radius: float = 0,
        fill: Any = None,
        outline: Any = None,
        width: float = 1,
        **kwargs: Any,
    ) -> None:
        self._d.rounded_rectangle(
            self._box(xy),
            radius=max(0, int(round(radius * self._s))),
            fill=fill,
            outline=outline,
            width=self._outline(width),
            **kwargs,
        )

    def polygon(
        self,
        xy: Any,
        fill: Any = None,
        outline: Any = None,
        width: float = 1,
        **kwargs: Any,
    ) -> None:
        self._d.polygon(
            [self._pt(p) for p in xy],
            fill=fill,
            outline=outline,
            width=self._outline(width),
            **kwargs,
        )

    def ellipse(
        self,
        xy: Any,
        fill: Any = None,
        outline: Any = None,
        width: float = 1,
        **kwargs: Any,
    ) -> None:
        self._d.ellipse(
            self._box(xy),
            fill=fill,
            outline=outline,
            width=self._outline(width),
            **kwargs,
        )

    def arc(
        self,
        xy: Any,
        start: float,
        end: float,
        fill: Any = None,
        width: float = 1,
        **kwargs: Any,
    ) -> None:
        self._d.arc(
            self._box(xy),
            start=start,
            end=end,
            fill=fill,
            width=self._outline(width),
            **kwargs,
        )

    def pieslice(
        self,
        xy: Any,
        start: float,
        end: float,
        fill: Any = None,
        outline: Any = None,
        width: float = 1,
        **kwargs: Any,
    ) -> None:
        self._d.pieslice(
            self._box(xy),
            start=start,
            end=end,
            fill=fill,
            outline=outline,
            width=self._outline(width),
            **kwargs,
        )

    def chord(
        self,
        xy: Any,
        start: float,
        end: float,
        fill: Any = None,
        outline: Any = None,
        width: float = 1,
        **kwargs: Any,
    ) -> None:
        self._d.chord(
            self._box(xy),
            start=start,
            end=end,
            fill=fill,
            outline=outline,
            width=self._outline(width),
            **kwargs,
        )


STOPS: list[dict[str, Any]] = [
    {
        "id": "20512",
        "name": "Washington & 9th",
        "subtitle": "Stop #20512 • via Lincoln Tunnel",
        "walk_min": 5,
    },
    {
        "id": "20494",
        "name": "Clinton & 9th",
        "subtitle": "Stop #20494 • via Clinton Ave",
        "walk_min": 3,
    },
]

DEFAULT_STOPS = STOPS


def get_canvas_stops(config: Optional[Any] = None) -> list[dict[str, Any]]:
    """Returns active transit stops for dashboard rendering.

    Evaluates user overrides, then dynamic TransitStopProvider resolution,
    falling back cleanly to default Hoboken STOPS.
    """
    if config is None:
        try:
            from location import get_location_config

            config = get_location_config()
        except ImportError:
            return [dict(s) for s in STOPS]

    if config is None:
        return [dict(s) for s in STOPS]

    # 1. User overrides in config
    stops_ov = getattr(config, "stops_override", None)
    if stops_ov is not None and isinstance(stops_ov, (list, tuple)):
        try:
            from transit_provider import get_transit_provider

            provider = get_transit_provider(
                city=getattr(config, "city", "Hoboken"),
                route=getattr(config, "route", "126"),
            )
            resolved = provider.resolve_stops(
                latitude=config.latitude,
                longitude=config.longitude,
                route=getattr(config, "route", "126"),
                overrides=list(stops_ov),
                fallback_to_default=True,
            )
            if resolved:
                return resolved
        except Exception:
            pass

    # 2. Dynamic provider resolution
    try:
        from transit_provider import get_transit_provider

        provider = get_transit_provider(
            city=getattr(config, "city", "Hoboken"),
            route=getattr(config, "route", "126"),
        )
        resolved = provider.resolve_stops(
            latitude=config.latitude,
            longitude=config.longitude,
            route=getattr(config, "route", "126"),
            fallback_to_default=True,
        )
        if resolved:
            return resolved
    except Exception:
        pass

    # 3. 100% Backward compatibility fallback
    return [dict(s) for s in STOPS]


def render_dashboard_sync(*args: Any, **kwargs: Any) -> Any:
    """Synchronously renders dashboard image matching render_dashboard."""
    from render_dashboard import render_dashboard

    return render_dashboard(*args, **kwargs)


def get_font(size: int, bold: bool = False) -> Any:
    """
    Attempts to load a clean sans-serif system font (Arial/Helvetica),
    falling back gracefully to Pillow's default font.
    """
    font_paths = [
        # Linux / Docker paths (fonts-dejavu-core)
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
        if bold
        else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf"
        if bold
        else "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        # macOS paths
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
        if bold
        else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/Supplemental/Trebuchet MS.ttf",
        "/System/Library/Fonts/SFNS.ttf",
        "/Library/Fonts/Arial.ttf",
    ]
    for p in font_paths:
        if os.path.exists(p):
            try:
                font: Any = ImageFont.truetype(p, size)
                # Tag so ScaledDraw can reconstruct this font at native size.
                font._transit_path = p
                font._transit_size = size
                return font
            except Exception:
                continue
    try:
        default_font: Any = ImageFont.load_default()
        try:
            default_font._transit_path = getattr(default_font, "path", None)
            default_font._transit_size = size
        except Exception:
            pass
        return default_font
    except Exception:
        return None


STATUS_OK = "ok"
STATUS_EMPTY = "empty"
STATUS_ERROR = "error"

_NO_BUS_MESSAGE = "No buses tracked in next hour"
_ERROR_MESSAGE = "Live data unavailable — retrying"


def empty_state_message(status: Optional[str]) -> tuple[str, str]:
    """
    Maps an upstream fetch status to the message (and colour) shown in an
    empty arrival card, so an upstream outage is never presented as
    'no buses'.
    """
    if status == STATUS_ERROR:
        return _ERROR_MESSAGE, "#aa0000"
    return _NO_BUS_MESSAGE, "#666666"


_DUE_WORDS_RE = re.compile(r"\b(approach\w*|due|now|all aboard|board|boarding)\b")


def parse_minutes(eta_text: Optional[str]) -> Optional[int]:
    """
    Extracts the arrival minute countdown from ETA strings like:
    'in 9 mins (11:36 PM)', 'in 3 mins', 'APPROACHING', 'All Aboard', etc.
    """
    if not eta_text:
        return None
    text = eta_text.lower()
    # Whole words only: "now" must not match inside "Unknown".
    if _DUE_WORDS_RE.search(text):
        return 0
    match = re.search(r"\b(\d+)\s*min", text)
    if match:
        return int(match.group(1))
    return None


def is_arrival_live(bus: dict[str, Any]) -> bool:
    """Determines whether a bus arrival record is backed by active real-time vehicle telemetry."""
    if bus.get("live") is False:
        return False
    if bus.get("live") is True:
        return True
    eta_raw = str(bus.get("eta") or "")
    if "\u25cb" in eta_raw:  # SCHED_MARK
        return False
    if "\u25cf" in eta_raw:  # LIVE_MARK
        return True
    if bus.get("vehicle_id"):
        return True
    return False


def format_hero_eta(first_bus: dict[str, Any]) -> tuple[str, str]:
    """
    Formats the primary hero countdown digits and unit string for an arrival.
    For arrivals under 60 minutes, returns active countdown (e.g. ('5', 'MIN') or ('DUE', '')).
    For arrivals 60+ minutes out, formats as human-readable departure clock time (e.g. ('4:09', 'PM'))
    or elapsed duration (e.g. ('2h 40m', '')) so users aren't confronted with '160 MIN'.
    """
    first_eta_raw = str(first_bus.get("eta") or "")
    first_min = parse_minutes(first_eta_raw)

    if first_min is not None:
        if first_min == 0:
            return "DUE", ""
        if first_min < 60:
            return str(first_min), "MIN"

        # 60+ minutes: extract clock time if available
        time_match = re.search(
            r"\b(\d{1,2}:\d{2})\s*([AP]M)?\b", first_eta_raw, re.IGNORECASE
        )
        if time_match:
            cd_str = time_match.group(1)
            unit_str = time_match.group(2).upper() if time_match.group(2) else ""
            return cd_str, unit_str
        if first_bus.get("epoch"):
            try:
                dt = datetime.datetime.fromtimestamp(float(first_bus["epoch"]))
                return dt.strftime("%I:%M").lstrip("0"), dt.strftime("%p")
            except Exception:
                pass
        h = first_min // 60
        m = first_min % 60
        return (f"{h}h {m:02d}m" if m else f"{h}h"), ""

    # first_min is None (clock time only, or non-minute status)
    time_match = re.search(
        r"\b(\d{1,2}:\d{2})\s*([AP]M)?\b", first_eta_raw, re.IGNORECASE
    )
    if time_match:
        cd_str = time_match.group(1)
        unit_str = time_match.group(2).upper() if time_match.group(2) else ""
        return cd_str, unit_str

    time_match_any = re.search(
        r"\b(\d{1,2}:\d{2}(?:\s*[AP]M)?)\b", first_eta_raw, re.IGNORECASE
    )
    if time_match_any:
        return time_match_any.group(1), ""

    return (first_eta_raw[:7].strip() if first_eta_raw else "--"), ""


def resolve_badge(
    first_bus: dict[str, Any], walk_min: int, compact: bool = False
) -> Optional[tuple[str, str, str]]:
    """
    Resolves the badge label, background color, and text color for an arrival card.
    Returns (label, bg, fg) or None if no badge should be shown.
    Distinguishes live tracked departures ('ON TIME') from unmonitored timetable runs ('SCHEDULED').
    """
    first_eta_raw = str(first_bus.get("eta") or "")
    first_min = parse_minutes(first_eta_raw)
    if first_min is None:
        return None

    if "board" in first_eta_raw.lower() or "all aboard" in first_eta_raw.lower():
        return "ALL ABOARD", "black", "white"
    if first_min <= walk_min:
        label = "RUN!" if compact else "RUN! LEAVING SOON"
        return label, "black", "white"
    if first_min <= walk_min + 3:
        return "WALK NOW", "black", "white"
    if first_min <= walk_min + 7:
        return "GET READY", "#f0f0f0", "black"

    # Beyond walk + 7: check whether vehicle telemetry is actively tracking this trip
    if is_arrival_live(first_bus):
        return "ON TIME", "#f0f0f0", "black"
    return "SCHEDULED", "#f0f0f0", "black"


def draw_header_badge(
    draw: Any,
    x0: int,
    y0: int,
    text: str,
    font: Any,
    pad_x: int = 14,
    pad_y: int = 5,
    radius: int = 6,
) -> int:
    """
    Draws an inverted black badge with white text, perfectly centered with generous padding.
    Returns the right edge (x1) of the badge bounding box.
    """
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    box_w = tw + 2 * pad_x
    box_h = 32
    box_x1 = x0 + box_w
    box_y1 = y0 + box_h
    draw.rounded_rectangle([x0, y0, box_x1, box_y1], radius=radius, fill="black")
    text_x = x0 + (box_w - tw) // 2 - bbox[0]
    text_y = y0 + (box_h - th) // 2 - bbox[1]
    draw.text((text_x, text_y), text, fill="white", font=font)
    return box_x1


def ellipsize_to_width(draw: Any, text: str, font: Any, max_width: int) -> str:
    """
    Truncates text with a trailing ellipsis so its rendered width never exceeds
    max_width. Returns the original string when it already fits (or when the
    budget is too small to place even an ellipsis).
    """
    if max_width <= 0 or not text:
        return text
    if draw.textbbox((0, 0), text, font=font)[2] <= max_width:
        return text
    ellipsis = "…"
    if draw.textbbox((0, 0), ellipsis, font=font)[2] > max_width:
        return ""
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if draw.textbbox((0, 0), text[:mid] + ellipsis, font=font)[2] <= max_width:
            lo = mid
        else:
            hi = mid - 1
    return text[:lo].rstrip() + ellipsis


def mock_badge_width(draw: Any, font: Any) -> int:
    """Returns the width of a 'MOCK DATA' badge, to reserve header space."""
    bbox = draw.textbbox((0, 0), "MOCK DATA", font=font)
    return (bbox[2] - bbox[0]) + 16


def draw_mock_badge(draw: Any, x: int, y: int, font: Any = None) -> int:
    """
    Draws a prominent 'MOCK DATA' badge so fabricated preview data is never
    mistaken for live telemetry. Returns the right edge of the badge.
    """
    if font is None:
        font = get_font(11, bold=True)
    text = "MOCK DATA"
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    box_h = 22
    x1 = x + tw + 16
    draw.rounded_rectangle([x, y, x1, y + box_h], radius=4, fill="black")
    draw.text(
        (x + 8 - bbox[0], y + (box_h - (bbox[3] - bbox[1])) // 2 - bbox[1]),
        text,
        fill="white",
        font=font,
    )
    return x1


def draw_battery_indicator(
    draw: Any,
    x: int,
    y: int,
    level: Optional[int],
    is_charging: bool = False,
    font: Any = None,
) -> int:
    """
    Draws a clean, high-contrast e-ink battery icon with percentage text and optional charging bolt.
    xy specifies top-left of the overall indicator.
    Returns the total width drawn.
    """
    if level is None or level < 0:
        return 0

    curr_x = x

    if is_charging:
        bolt_pts = [
            (curr_x + 5, y),
            (curr_x + 1, y + 7),
            (curr_x + 4, y + 7),
            (curr_x + 2, y + 13),
            (curr_x + 8, y + 5),
            (curr_x + 5, y + 5),
        ]
        draw.polygon(bolt_pts, fill="black")
        curr_x += 12

    label = f"{level}%"
    if font:
        bbox = draw.textbbox((0, 0), label, font=font)
        label_w = bbox[2] - bbox[0]
        draw.text((curr_x, y), label, fill="black", font=font)
        curr_x += label_w + 6
    else:
        curr_x += 6

    bw, bh = 28, 14
    term_w, term_h = 3, 6
    icon_x = curr_x
    icon_y = y + 1

    draw.rounded_rectangle(
        [icon_x, icon_y, icon_x + bw, icon_y + bh], radius=3, outline="black", width=2
    )
    term_y = icon_y + (bh - term_h) // 2
    draw.rounded_rectangle(
        [icon_x + bw, term_y, icon_x + bw + term_w, term_y + term_h],
        radius=1,
        fill="black",
    )

    inner_pad = 3
    max_fill_w = bw - (inner_pad * 2) - 1
    fill_w = max(2, int(max_fill_w * (min(level, 100) / 100.0)))
    draw.rectangle(
        [
            icon_x + inner_pad,
            icon_y + inner_pad,
            icon_x + inner_pad + fill_w,
            icon_y + bh - inner_pad,
        ],
        fill="black",
    )

    return (icon_x + bw + term_w) - x


def draw_brightness_button(
    draw: Any,
    x: int,
    y: int,
    size: int = 30,
) -> tuple[int, int]:
    """
    Renders a small tactile brightness toggle button with simple sun-like iconography.
    Returns (x0, x1) horizontal bounding coordinates.
    """
    x0, y0 = x, y
    x1, y1 = x + size, y + size

    draw.rounded_rectangle(
        [x0, y0, x1, y1], radius=5, fill="#f4f4f4", outline="black", width=2
    )

    cx = x0 + size // 2
    cy = y0 + size // 2

    # Central sun disc
    r = 4
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill="black")

    # 8 sun rays extending outward
    ray_in = 6
    ray_out = 9
    for deg in (0, 45, 90, 135, 180, 225, 270, 315):
        rad = math.radians(deg)
        rx0 = cx + math.cos(rad) * ray_in
        ry0 = cy + math.sin(rad) * ray_in
        rx1 = cx + math.cos(rad) * ray_out
        ry1 = cy + math.sin(rad) * ray_out
        draw.line(
            [(int(round(rx0)), int(round(ry0))), (int(round(rx1)), int(round(ry1)))],
            fill="black",
            width=1,
        )

    return x0, x1


def draw_bottom_button_bar(
    draw: Any,
    width: int,
    height: int,
    active_view: str = "morning",
    font: Any = None,
) -> None:
    """
    Renders tactile touch buttons across the bottom edge of the dashboard:
    [ BUSES ] [ CITI BIKE ] [ WEATHER ] [ ↻ REFRESH ]
    The active view button is highlighted with inverted fill (black fill, white text).
    """
    is_tall = height >= 580
    btn_y0 = height - (44 if is_tall else 38)
    btn_y1 = height - (10 if is_tall else 8)
    btn_h = btn_y1 - btn_y0

    draw.line([(20, btn_y0 - 8), (width - 20, btn_y0 - 8)], fill="#bbbbbb", width=1)

    start_x = 20
    total_w = width - 40
    gap = 10

    if font is None:
        font = get_font(12, bold=True)

    is_bus = active_view in ("evening", "bus_focus", "buses")
    is_bike = active_view in ("morning", "citibike_focus", "bikes")
    is_weather = active_view in ("weather", "weather_view")

    buttons = [
        ("● BUSES" if is_bus else "BUSES", is_bus),
        ("● CITI BIKE" if is_bike else "CITI BIKE", is_bike),
        ("● WEATHER" if is_weather else "WEATHER", is_weather),
        ("↻ REFRESH", False),
    ]
    col_w = (total_w - (len(buttons) - 1) * gap) // len(buttons)

    for i, (label, active) in enumerate(buttons):
        x0 = start_x + i * (col_w + gap)
        x1 = x0 + col_w
        bg = "black" if active else "#f4f4f4"
        fg = "white" if active else "black"
        draw.rounded_rectangle(
            [x0, btn_y0, x1, btn_y1], radius=6, fill=bg, outline="black", width=2
        )
        bbox = draw.textbbox((0, 0), label, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        draw.text(
            (x0 + (col_w - tw) // 2, btn_y0 + (btn_h - th) // 2 - 1),
            label,
            fill=fg,
            font=font,
        )


def draw_status_strip(
    draw: Any,
    width: int,
    height: int,
    note: str = "",
) -> None:
    """
    Overpaints the bottom button bar with an inert status strip.

    Used whenever the panel is NOT currently interactive (idle-while-suspended
    or overnight dormant): drawing live buttons there would be deceptive,
    because a tap cannot wake the suspended SoC on this hardware. The strip
    states how to bring the dashboard to life (press the power button).
    """
    is_tall = height >= 580
    btn_y0 = height - (44 if is_tall else 38)
    btn_y1 = height - (10 if is_tall else 8)

    draw.rectangle([0, btn_y0 - 9, width, height], fill="white")
    draw.line([(20, btn_y0 - 8), (width - 20, btn_y0 - 8)], fill="#dddddd", width=1)

    label = note or "PRESS POWER BUTTON TO INTERACT"
    font = get_font(12, bold=True)
    draw.rounded_rectangle(
        [20, btn_y0, width - 20, btn_y1],
        radius=6,
        fill="#f2f2f2",
        outline="#999999",
        width=2,
    )
    bbox = draw.textbbox((0, 0), label, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    draw.text(
        (20 + (width - 40 - tw) // 2, btn_y0 + (btn_y1 - btn_y0 - th) // 2 - 1),
        label,
        fill="#666666",
        font=font,
    )
