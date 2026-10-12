import os
import sys
from datetime import datetime
from typing import Any, Optional

from bus_tracker import NJTransitBusTracker, normalize_arrival
from canvas import (
    DEFAULT_STOPS,
    HEIGHT,
    STATUS_EMPTY,
    STATUS_ERROR,
    STATUS_OK,
    STOPS,
    WIDTH,
    ScaledDraw,
    draw_battery_indicator,
    draw_bottom_button_bar,
    draw_brightness_button,
    draw_header_badge,
    draw_mock_badge,
    draw_status_strip,
    ellipsize_to_width,
    empty_state_message,
    get_canvas_stops,
    get_font,
    mock_badge_width,
    parse_minutes,
)
from citibike import CitiBikeTracker
from dashboard_dsl import RenderContext
from dashboards import REGISTRY
from evening_view import render_evening_view
from morning_view import render_morning_view
from PIL import Image, ImageDraw, ImageFont
from weather import WeatherTracker, get_mock_weather_data

__all__ = [
    "DEFAULT_STOPS",
    "HEIGHT",
    "ImageFont",
    "STATUS_EMPTY",
    "STATUS_ERROR",
    "STATUS_OK",
    "STOPS",
    "WIDTH",
    "ScaledDraw",
    "draw_battery_indicator",
    "draw_bottom_button_bar",
    "draw_brightness_button",
    "draw_header_badge",
    "draw_mock_badge",
    "draw_status_strip",
    "ellipsize_to_width",
    "empty_state_message",
    "get_canvas_stops",
    "get_font",
    "get_mock_data",
    "mock_badge_width",
    "os",
    "parse_minutes",
    "render_dashboard",
    "render_dashboard_sync",
    "resolve_view",
]


def resolve_view(view: str = "auto", hour: Optional[int] = None) -> str:
    """
    Resolves view mode across built-in presets and registered modular dashboards.
    - 'morning': Citi Bike Hero view (AM commute, 5:00 AM - 12:00 PM).
    - 'evening': Bus Hero view (PM commute / evening / night, 12:00 PM - 5:00 AM).
    - Any registered dashboard ID (e.g. 'weather', 'bus_focus', 'citibike_focus').
    - 'auto': Automatically switches based on current local hour.
    """
    v = (view or "auto").lower().strip()
    if v in ("morning", "citi", "citibike", "am"):
        return "morning"
    if v in ("evening", "bus", "pm", "afternoon", "night"):
        return "evening"

    # Check registered modular dashboards
    try:
        if REGISTRY.get(v) is not None:
            return v
    except Exception:
        pass

    if hour is None:
        hour = datetime.now().hour
    if 5 <= hour < 12:
        return "morning"
    return "evening"


def render_dashboard(
    stops_data: dict[str, list[dict[str, Any]]],
    citibike_data: Any = None,
    output_path: Any = "dashboard.png",
    view: str = "auto",
    is_mock: bool = False,
    batt_level: Optional[int] = None,
    is_charging: bool = False,
    stop_status: Optional[dict[str, str]] = None,
    width: int = WIDTH,
    height: int = HEIGHT,
    scale: float = 1.0,
    presentation: str = "interactive",
    status_note: str = "",
    available_views: Optional[list[str]] = None,
    weather_data: Any = None,
    custom_data: Optional[dict[str, Any]] = None,
    stops: Optional[list[dict[str, Any]]] = None,
    location_config: Optional[Any] = None,
) -> str:
    """
    Renders a high-contrast black-and-white image optimized for e-ink
    or low-power dashboard screens (default 800x480, or 800x600 for 4:3 displays).
    Supports built-in views and arbitrary modular dashboards.
    """
    if location_config is None:
        try:
            from location import get_location_config

            location_config = get_location_config()
        except ImportError:
            location_config = None

    active_stops = stops if stops is not None else get_canvas_stops(location_config)

    if citibike_data is None:
        enable_micro = (
            getattr(location_config, "enable_micromobility", True)
            if location_config
            else True
        )
        if not enable_micro:
            citibike_data = []
        else:
            try:
                from citibike_discovery import discover_citibike_stations

                lat = location_config.latitude if location_config else 40.7371
                lon = location_config.longitude if location_config else -74.0305
                max_st = (
                    getattr(location_config, "citibike_max_stations", 6)
                    if location_config
                    else 6
                )
                max_walk = (
                    getattr(location_config, "max_walk_minutes", 15)
                    if location_config
                    else 15
                )
                discovered = discover_citibike_stations(
                    latitude=lat,
                    longitude=lon,
                    max_stations=max_st,
                    max_walk_minutes=max_walk,
                    enable_micromobility=True,
                )
                if not discovered:
                    citibike_data = []
                else:
                    tracker = CitiBikeTracker(stations=discovered)
                    citibike_data = (
                        tracker.get_mock_data()
                        if is_mock
                        else tracker.get_station_status()
                    )
            except Exception:
                try:
                    tracker = CitiBikeTracker()
                    citibike_data = (
                        tracker.get_mock_data()
                        if is_mock
                        else tracker.get_station_status()
                    )
                except Exception:
                    citibike_data = []

    active_view = resolve_view(view)

    # Create native-resolution canvas; view code draws in logical coordinates.
    native_w = max(1, int(round(width * scale)))
    native_h = max(1, int(round(height * scale)))
    img = Image.new("RGB", (native_w, native_h), color="white")
    draw = ScaledDraw(ImageDraw.Draw(img), scale)
    now = datetime.now()

    if active_view == "morning":
        render_morning_view(
            draw,
            stops_data,
            citibike_data,
            now,
            batt_level=batt_level,
            is_charging=is_charging,
            is_mock=is_mock,
            stop_status=stop_status,
            width=width,
            height=height,
            stops=active_stops,
            location_config=location_config,
        )
    elif active_view == "evening":
        render_evening_view(
            draw,
            stops_data,
            citibike_data,
            now,
            batt_level=batt_level,
            is_charging=is_charging,
            is_mock=is_mock,
            stop_status=stop_status,
            width=width,
            height=height,
            stops=active_stops,
            location_config=location_config,
        )
    else:
        # Modular dashboard rendering via REGISTRY
        if weather_data is None:
            try:
                loc_name = (
                    getattr(location_config, "location_name", "Hoboken, NJ")
                    if location_config
                    else "Hoboken, NJ"
                )
                lat = location_config.latitude if location_config else None
                lon = location_config.longitude if location_config else None
                weather_data = (
                    get_mock_weather_data(location_name=loc_name)
                    if is_mock
                    else WeatherTracker(
                        latitude=lat, longitude=lon, location_name=loc_name
                    ).get_weather()
                )
            except Exception:
                weather_data = get_mock_weather_data() if is_mock else None

        ctx = RenderContext(
            now=now,
            stops_data=stops_data,
            stop_status=stop_status or {},
            citibike_data=citibike_data or [],
            weather_data=weather_data,
            custom_data=custom_data or {},
            batt_level=batt_level,
            is_charging=is_charging,
            presentation=presentation,
            status_note=status_note,
            active_view=active_view,
            available_views=available_views or [],
            is_mock=is_mock,
            width=width,
            height=height,
        )
        handled = REGISTRY.render(active_view, draw, ctx)
        if not handled:
            render_evening_view(
                draw,
                stops_data,
                citibike_data,
                now,
                batt_level=batt_level,
                is_charging=is_charging,
                is_mock=is_mock,
                stop_status=stop_status,
                width=width,
                height=height,
                stops=active_stops,
                location_config=location_config,
            )

    # Not interactive (idle-while-suspended or overnight): erase the button bar
    # and show a status strip so the panel does not masquerade as tappable.
    if presentation != "interactive":
        draw_status_strip(draw, width, height, note=status_note)

    img.save(output_path, "PNG")
    print(
        f"✓ Dashboard image successfully rendered [{active_view.upper()} VIEW]: {output_path} ({native_w}x{native_h}, scale={scale:g})"
    )
    return output_path


# Alias for synchronous rendering contract
render_dashboard_sync = render_dashboard


def get_mock_data(
    stops: Optional[list[dict[str, Any]]] = None,
) -> dict[str, list[dict[str, Any]]]:
    """Generates realistic peak-hour commute data for layout previewing."""
    base: dict[str, list[dict[str, Any]]] = {
        "20512": [
            {
                "route": "126",
                "destination": "126 NEW YORK",
                "eta": "in 5 mins (8:35 AM)",
                "occupancy": "SEATS_AVAILABLE",
                "vehicle_id": "25248",
            },
            {
                "route": "126",
                "destination": "126 NEW YORK",
                "eta": "in 17 mins (8:47 AM)",
                "occupancy": "HALF_EMPTY",
                "vehicle_id": "21045",
            },
        ],
        "20494": [
            {
                "route": "126",
                "destination": "126 NEW YORK VIA CLINTON",
                "eta": "in 12 mins (8:42 AM)",
                "occupancy": "EMPTY",
                "vehicle_id": "22119",
            },
            {
                "route": "126",
                "destination": "126 NEW YORK VIA CLINTON",
                "eta": "in 24 mins (8:54 AM)",
                "occupancy": "SEATS_AVAILABLE",
                "vehicle_id": "25301",
            },
        ],
    }
    if stops is None:
        return base

    result: dict[str, list[dict[str, Any]]] = {}
    for i, s in enumerate(stops):
        sid = str(s.get("id", ""))
        if sid in base:
            result[sid] = [dict(item) for item in base[sid]]
        else:
            route = str(s.get("route") or "126")
            dest = str(s.get("destination") or f"{route} NEW YORK")
            eta1 = f"in {4 + i * 7} mins"
            eta2 = f"in {16 + i * 8} mins"
            result[sid] = [
                {
                    "route": route,
                    "destination": dest,
                    "eta": eta1,
                    "occupancy": "SEATS_AVAILABLE",
                    "vehicle_id": str(25200 + i),
                },
                {
                    "route": route,
                    "destination": dest,
                    "eta": eta2,
                    "occupancy": "HALF_EMPTY",
                    "vehicle_id": str(21000 + i),
                },
            ]
    return result


if __name__ == "__main__":
    use_mock = "--mock" in sys.argv
    view_arg = "auto"
    for arg in sys.argv:
        if arg.startswith("--view="):
            view_arg = arg.split("=", 1)[1]
        elif arg in ("--morning", "-morning"):
            view_arg = "morning"
        elif arg in ("--evening", "-evening"):
            view_arg = "evening"

    stops_data = {}

    stop_status = {}

    if use_mock:
        print("Rendering with mock peak-commute data...")
        stops_data = get_mock_data()
        stop_status = {stop["id"]: STATUS_OK for stop in STOPS}
    else:
        print("Fetching live data from NJ Transit API...")
        tracker = NJTransitBusTracker()
        for stop in STOPS:
            sid = stop["id"]
            status, trips = tracker.get_arrivals_with_status(stop_id=sid, route="126")
            stops_data[sid] = [dict(normalize_arrival(t)) for t in trips]
            stop_status[sid] = status

    render_dashboard(
        stops_data,
        output_path="dashboard.png",
        view=view_arg,
        is_mock=use_mock,
        stop_status=stop_status,
    )
