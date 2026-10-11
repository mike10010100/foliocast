"""
Vector Weather Iconography for E-Ink Displays.
Renders high-contrast, scalable black-and-white meteorological glyphs
compatible with Pillow and ScaledDraw.
"""

import math
from typing import Any, Optional


def draw_cloud(
    draw: Any,
    cx: int,
    cy: int,
    w: int,
    h: int,
    fill: str = "white",
    outline: str = "black",
    width: int = 2,
) -> None:
    """Draws a crisp flat-bottomed cloud with 3 upper puffs and black outline."""
    y_base = cy + int(h * 0.22)
    x_left = cx - int(w * 0.30)
    x_right = cx + int(w * 0.30)

    r_left = int(w * 0.17)
    r_mid = int(w * 0.25)
    r_right = int(w * 0.15)

    c_left = (cx - int(w * 0.18), y_base - r_left)
    c_mid = (cx + int(w * 0.04), y_base - int(h * 0.40))
    c_right = (cx + int(w * 0.22), y_base - r_right)

    ow = width if outline else 0

    def _draw_pieces(offset: int, col: str) -> None:
        draw.rounded_rectangle(
            [
                x_left - offset,
                y_base - r_left * 2 - offset,
                x_right + offset,
                y_base + offset,
            ],
            radius=r_left + offset,
            fill=col,
        )
        draw.ellipse(
            [
                c_left[0] - r_left - offset,
                c_left[1] - r_left - offset,
                c_left[0] + r_left + offset,
                c_left[1] + r_left + offset,
            ],
            fill=col,
        )
        draw.ellipse(
            [
                c_mid[0] - r_mid - offset,
                c_mid[1] - r_mid - offset,
                c_mid[0] + r_mid + offset,
                c_mid[1] + r_mid + offset,
            ],
            fill=col,
        )
        draw.ellipse(
            [
                c_right[0] - r_right - offset,
                c_right[1] - r_right - offset,
                c_right[0] + r_right + offset,
                c_right[1] + r_right + offset,
            ],
            fill=col,
        )

    if outline:
        _draw_pieces(ow, outline)
    _draw_pieces(0, fill)


def draw_sun(
    draw: Any,
    cx: int,
    cy: int,
    r_disc: int,
    ray_in: int,
    ray_out: int,
    fill: str = "black",
    ray_w: int = 2,
    angles: Optional[tuple[int, ...]] = None,
) -> None:
    """Draws a solid sun disc with radial rays."""
    draw.ellipse([cx - r_disc, cy - r_disc, cx + r_disc, cy + r_disc], fill=fill)
    ray_angles = angles or (0, 45, 90, 135, 180, 225, 270, 315)
    for deg in ray_angles:
        rad = math.radians(deg)
        rx0 = cx + math.cos(rad) * ray_in
        ry0 = cy + math.sin(rad) * ray_in
        rx1 = cx + math.cos(rad) * ray_out
        ry1 = cy + math.sin(rad) * ray_out
        draw.line(
            [(int(round(rx0)), int(round(ry0))), (int(round(rx1)), int(round(ry1)))],
            fill=fill,
            width=ray_w,
        )


def draw_snowflake(
    draw: Any,
    cx: int,
    cy: int,
    r: int,
    width: int = 1,
) -> None:
    """Draws a 6-point snowflake crystal."""
    for deg in (0, 60, 120):
        rad = math.radians(deg)
        dx = math.cos(rad) * r
        dy = math.sin(rad) * r
        draw.line(
            [(int(cx - dx), int(cy - dy)), (int(cx + dx), int(cy + dy))],
            fill="black",
            width=width,
        )
        for sign in (-1, 1):
            tx = cx + sign * dx * 0.65
            ty = cy + sign * dy * 0.65
            tdx = -dy * 0.4
            tdy = dx * 0.4
            draw.line(
                [
                    (int(round(tx - tdx)), int(round(ty - tdy))),
                    (int(round(tx + tdx)), int(round(ty + tdy))),
                ],
                fill="black",
                width=width,
            )


def draw_rain_streaks(
    draw: Any,
    cx: int,
    cy: int,
    count: int,
    length: int = 10,
    width: int = 2,
    gap: int = 8,
    angle_deg: int = 70,
) -> None:
    """Draws parallel diagonal rain streaks."""
    rad = math.radians(angle_deg)
    dx = math.cos(rad) * length
    dy = math.sin(rad) * length
    total_w = (count - 1) * gap
    start_x = cx - total_w / 2
    for i in range(count):
        sx = start_x + i * gap
        draw.line(
            [
                (int(round(sx)), int(round(cy))),
                (int(round(sx + dx)), int(round(cy + dy))),
            ],
            fill="black",
            width=width,
        )


def draw_lightning(
    draw: Any,
    cx: int,
    cy: int,
    scale: float = 1.0,
) -> None:
    """Draws a bold zigzag lightning bolt."""
    pts = [
        (cx + 2 * scale, cy - 8 * scale),
        (cx - 5 * scale, cy + 2 * scale),
        (cx - 1 * scale, cy + 2 * scale),
        (cx - 4 * scale, cy + 14 * scale),
        (cx + 6 * scale, cy),
        (cx + 1 * scale, cy),
    ]
    draw.polygon(pts, fill="black")


def draw_weather_icon(
    draw: Any,
    x: int,
    y: int,
    size: int = 64,
    glyph: Optional[str] = "SUN",
) -> None:
    """
    Renders a crisp vector meteorological icon inside the bounding box (x, y, x + size, y + size).
    Supports WMO weather code glyphs: SUN, MOSTLY_SUN, PARTLY_CLOUD, CLOUDY,
    DRIZZLE, LIGHT_RAIN, RAIN, HEAVY_RAIN, SHOWERS, THUNDER, SNOW, LIGHT_SNOW,
    HEAVY_SNOW, FREEZE_RAIN, FOG, WIND, and PRECIPITATION / UMBRELLA.
    """
    cx = x + size // 2
    cy = y + size // 2
    g = (glyph or "SUN").upper().strip()

    if g in ("SUN", "CLEAR"):
        r_disc = int(size * 0.20)
        draw_sun(
            draw,
            cx,
            cy,
            r_disc,
            int(size * 0.28),
            int(size * 0.44),
            fill="black",
            ray_w=max(2, int(size * 0.04)),
        )
    elif g in ("MOSTLY_SUN",):
        sun_cx = cx - int(size * 0.10)
        sun_cy = cy - int(size * 0.10)
        r_disc = int(size * 0.18)
        draw_sun(
            draw,
            sun_cx,
            sun_cy,
            r_disc,
            int(size * 0.24),
            int(size * 0.38),
            fill="black",
            ray_w=max(2, int(size * 0.04)),
            angles=(-180, -135, -90, -45, 0, 180, 225),
        )
        c_cx = cx + int(size * 0.14)
        c_cy = cy + int(size * 0.14)
        draw_cloud(
            draw,
            c_cx,
            c_cy,
            int(size * 0.62),
            int(size * 0.38),
            fill="white",
            outline="black",
            width=2,
        )
    elif g in ("PARTLY_CLOUD",):
        sun_cx = cx - int(size * 0.12)
        sun_cy = cy - int(size * 0.12)
        r_disc = int(size * 0.18)
        draw_sun(
            draw,
            sun_cx,
            sun_cy,
            r_disc,
            int(size * 0.25),
            int(size * 0.38),
            fill="black",
            ray_w=max(2, int(size * 0.04)),
            angles=(-180, -135, -90, -45, 0),
        )
        c_cx = cx + int(size * 0.10)
        c_cy = cy + int(size * 0.10)
        draw_cloud(
            draw,
            c_cx,
            c_cy,
            int(size * 0.72),
            int(size * 0.44),
            fill="white",
            outline="black",
            width=2,
        )
    elif g in ("CLOUDY", "CLOUD", "OVERCAST"):
        draw_cloud(
            draw,
            cx,
            cy,
            int(size * 0.85),
            int(size * 0.54),
            fill="white",
            outline="black",
            width=2,
        )
    elif g in ("RAIN", "LIGHT_RAIN", "HEAVY_RAIN", "DRIZZLE"):
        c_cy = cy - int(size * 0.10)
        draw_cloud(
            draw,
            cx,
            c_cy,
            int(size * 0.82),
            int(size * 0.52),
            fill="white",
            outline="black",
            width=2,
        )
        count = 2 if g in ("LIGHT_RAIN", "DRIZZLE") else (4 if g == "HEAVY_RAIN" else 3)
        rw = 1 if g == "DRIZZLE" else (3 if g == "HEAVY_RAIN" else 2)
        rl = int(size * 0.12) if g == "DRIZZLE" else int(size * 0.20)
        draw_rain_streaks(
            draw,
            cx,
            c_cy + int(size * 0.28),
            count,
            length=rl,
            width=rw,
            gap=int(size * 0.14),
        )
    elif g in ("SHOWERS",):
        sun_cx = cx - int(size * 0.14)
        sun_cy = cy - int(size * 0.14)
        r_disc = int(size * 0.15)
        draw_sun(
            draw,
            sun_cx,
            sun_cy,
            r_disc,
            int(size * 0.22),
            int(size * 0.32),
            fill="black",
            ray_w=max(2, int(size * 0.03)),
            angles=(-180, -135, -90, -45),
        )
        c_cx = cx + int(size * 0.08)
        c_cy = cy - int(size * 0.02)
        draw_cloud(
            draw,
            c_cx,
            c_cy,
            int(size * 0.74),
            int(size * 0.46),
            fill="white",
            outline="black",
            width=2,
        )
        draw_rain_streaks(
            draw,
            c_cx,
            c_cy + int(size * 0.26),
            3,
            length=int(size * 0.18),
            width=2,
            gap=int(size * 0.13),
        )
    elif g in ("THUNDER", "THUNDERSTORM"):
        c_cy = cy - int(size * 0.14)
        draw_cloud(
            draw,
            cx,
            c_cy,
            int(size * 0.82),
            int(size * 0.52),
            fill="white",
            outline="black",
            width=2,
        )
        draw_lightning(
            draw,
            cx - int(size * 0.02),
            c_cy + int(size * 0.25),
            scale=size / 48.0,
        )
    elif g in ("SNOW", "LIGHT_SNOW", "HEAVY_SNOW"):
        c_cy = cy - int(size * 0.10)
        draw_cloud(
            draw,
            cx,
            c_cy,
            int(size * 0.82),
            int(size * 0.52),
            fill="white",
            outline="black",
            width=2,
        )
        sn_y = c_cy + int(size * 0.30)
        count = 2 if g == "LIGHT_SNOW" else 3
        gap = int(size * 0.20)
        start_x = cx - ((count - 1) * gap) / 2
        for i in range(count):
            draw_snowflake(
                draw,
                int(round(start_x + i * gap)),
                sn_y,
                int(size * 0.08),
                width=max(1, int(size * 0.03)),
            )
    elif g in ("FREEZE_RAIN",):
        c_cy = cy - int(size * 0.10)
        draw_cloud(
            draw,
            cx,
            c_cy,
            int(size * 0.82),
            int(size * 0.52),
            fill="white",
            outline="black",
            width=2,
        )
        y_precip = c_cy + int(size * 0.28)
        draw_rain_streaks(
            draw,
            cx - int(size * 0.12),
            y_precip,
            1,
            length=int(size * 0.18),
            width=2,
        )
        draw_snowflake(
            draw,
            cx + int(size * 0.10),
            y_precip + int(size * 0.06),
            int(size * 0.08),
            width=max(1, int(size * 0.03)),
        )
    elif g in ("FOG",):
        c_cy = cy - int(size * 0.10)
        draw_cloud(
            draw,
            cx,
            c_cy,
            int(size * 0.76),
            int(size * 0.46),
            fill="white",
            outline="black",
            width=2,
        )
        fog_y = c_cy + int(size * 0.26)
        bw_list = [int(size * 0.55), int(size * 0.45), int(size * 0.35)]
        for i, bw in enumerate(bw_list):
            fy = fog_y + i * int(size * 0.09)
            draw.rounded_rectangle(
                [cx - bw // 2, fy, cx + bw // 2, fy + max(2, int(size * 0.04))],
                radius=2,
                fill="black",
            )
    elif g in ("WIND",):
        lines_y = [cy - int(size * 0.18), cy, cy + int(size * 0.18)]
        for i, ly in enumerate(lines_y):
            w_len = int(size * (0.60 - i * 0.08))
            draw.line(
                [(cx - w_len // 2, ly), (cx + w_len // 2, ly)],
                fill="black",
                width=2,
            )
    elif g in ("UMBRELLA", "PRECIPITATION"):
        u_y = cy - int(size * 0.12)
        u_w = int(size * 0.62)
        u_h = int(size * 0.30)
        draw.line([(cx, u_y - int(size * 0.08)), (cx, u_y)], fill="black", width=2)
        draw.pieslice(
            [cx - u_w // 2, u_y - u_h, cx + u_w // 2, u_y + u_h],
            start=180,
            end=0,
            fill="black",
        )
        draw.line([(cx - u_w // 2, u_y), (cx + u_w // 2, u_y)], fill="black", width=2)
        shaft_bot = cy + int(size * 0.26)
        draw.line([(cx, u_y), (cx, shaft_bot)], fill="black", width=2)
        draw.arc(
            [
                cx - int(size * 0.08),
                shaft_bot - int(size * 0.06),
                cx + int(size * 0.04),
                shaft_bot + int(size * 0.08),
            ],
            start=0,
            end=180,
            fill="black",
            width=2,
        )
        draw_rain_streaks(
            draw,
            cx - int(size * 0.32),
            cy - int(size * 0.05),
            1,
            length=int(size * 0.12),
            width=2,
        )
        draw_rain_streaks(
            draw,
            cx + int(size * 0.32),
            cy - int(size * 0.05),
            1,
            length=int(size * 0.12),
            width=2,
        )
    else:
        draw_cloud(
            draw,
            cx,
            cy,
            int(size * 0.82),
            int(size * 0.52),
            fill="white",
            outline="black",
            width=2,
        )
