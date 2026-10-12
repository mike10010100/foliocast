import re
from datetime import datetime
from typing import Any, Optional

from canvas import (
    HEIGHT,
    STATUS_ERROR,
    STOPS,
    WIDTH,
    draw_battery_indicator,
    draw_bottom_button_bar,
    draw_brightness_button,
    draw_header_badge,
    draw_mock_badge,
    ellipsize_to_width,
    empty_state_message,
    get_font,
    mock_badge_width,
    parse_minutes,
)


def render_morning_view(
    draw: Any,
    stops_data: dict[str, list[dict[str, Any]]],
    citibike_data: Any,
    now: datetime,
    batt_level: Optional[int],
    is_charging: bool,
    is_mock: bool,
    stop_status: Optional[dict[str, str]] = None,
    width: int = WIDTH,
    height: int = HEIGHT,
    stops: Optional[list[dict[str, Any]]] = None,
    location_config: Optional[Any] = None,
):
    """
    Morning Commute View:
    When Citi Bike docks are present, dock status is the primary hero display
    and transit departures are shown in a compact bottom bar.
    When Citi Bike is absent, bus departure cards expand into full-height hero cards.
    """
    has_citibike = bool(citibike_data)
    active_stops = stops if stops is not None else STOPS
    is_tall = height >= 580

    font_title = get_font(21, bold=True)
    font_header_sub = get_font(12, bold=False)
    font_time = get_font(18, bold=True)
    font_card_title = get_font(16 if is_tall else 15, bold=True)
    font_walk = get_font(11, bold=True)
    font_hero_num = get_font(58 if is_tall else 52, bold=True)
    font_hero_label = get_font(13, bold=True)
    font_sub_stat = get_font(14 if is_tall else 13, bold=False)
    font_badge = get_font(11, bold=True)
    font_bus_bar_title = get_font(11, bold=True)
    font_bus_stop = get_font(14 if is_tall else 13, bold=True)
    font_bus_eta = get_font(14 if is_tall else 13, bold=True)
    font_bus_meta = get_font(13 if is_tall else 12, bold=False)

    font_stop_name = get_font(20, bold=True)
    font_countdown_num = get_font(62 if is_tall else 58, bold=True)
    font_countdown_unit = get_font(22, bold=True)
    font_detail = get_font(13, bold=False)
    font_footer = get_font(11, bold=False)

    now_time_str = now.strftime("%-I:%M %p")
    now_date_str = now.strftime("%A, %b %-d")

    time_bbox = draw.textbbox((0, 0), now_time_str, font=font_time)
    time_w = time_bbox[2] - time_bbox[0]
    time_x = width - 20 - time_w
    draw.text((time_x, 15), now_time_str, fill="black", font=font_time)

    date_bbox = draw.textbbox((0, 0), now_date_str, font=font_header_sub)
    date_w = date_bbox[2] - date_bbox[0]
    date_x = width - 20 - date_w
    draw.text((date_x, 39), now_date_str, fill="#555555", font=font_header_sub)

    # Brightness toggle button immediately to left of time and date
    time_date_left = min(time_x, date_x)
    bright_size = 30
    bright_x0 = time_date_left - bright_size - 10
    draw_brightness_button(draw, bright_x0, 16, size=bright_size)

    right_boundary = bright_x0
    if is_mock:
        badge_font = get_font(11, bold=True)
        mw = mock_badge_width(draw, badge_font)
        mock_x = bright_x0 - mw - 10
        draw_mock_badge(draw, mock_x, 36, badge_font)
        right_boundary = mock_x

    batt_x = right_boundary
    if batt_level is not None:
        font_batt = get_font(13, bold=True)
        label = f"{batt_level}%"
        bbox = draw.textbbox((0, 0), label, font=font_batt)
        label_w = bbox[2] - bbox[0]
        bolt_w = 12 if is_charging else 0
        total_batt_w = bolt_w + label_w + 6 + 28 + 3
        batt_x = right_boundary - total_batt_w - 14
        draw_battery_indicator(
            draw, batt_x, 16, batt_level, is_charging=is_charging, font=font_batt
        )

    if has_citibike:
        b_x1 = draw_header_badge(draw, 20, 14, "CITI BIKE", font_title, pad_x=12)
        city_name = str(
            getattr(location_config, "city", "Hoboken")
            if location_config
            else "Hoboken"
        ).upper()
        if location_config is None or city_name == "HOBOKEN":
            morning_title = "HOBOKEN MORNING DOCKS"
        else:
            morning_title = f"{city_name} MORNING DOCKS"
        max_title_w = (batt_x - 16) - (b_x1 + 12)
        tb = draw.textbbox((0, 0), morning_title, font=font_title)
        if (tb[2] - tb[0]) > max_title_w:
            morning_title = "MORNING DOCKS"
        draw.text((b_x1 + 12, 15), morning_title, fill="black", font=font_title)

        if location_config is None:
            sub_text = "HOBOKEN CITY HALL • E-BIKE PRIORITY & 126 BUS"
        else:
            loc_name = str(
                getattr(location_config, "location_name", "Hoboken City Hall")
            ).upper()
            route_val = str(getattr(location_config, "route", "126"))
            sub_text = f"{loc_name} • E-BIKE PRIORITY & {route_val} BUS"
        sub_text = ellipsize_to_width(
            draw, sub_text, font_header_sub, max(50, max_title_w)
        )
        draw.text((b_x1 + 12, 39), sub_text, fill="#555555", font=font_header_sub)
    else:
        route_str = str(
            getattr(location_config, "route", "126") if location_config else "126"
        )
        b_x1 = draw_header_badge(draw, 20, 14, route_str, font_title, pad_x=16)

        city_name = str(
            getattr(location_config, "city", "Hoboken")
            if location_config
            else "Hoboken"
        ).upper()
        dest_name = str(
            getattr(location_config, "destination", "NYC Port Authority")
            if location_config
            else "NYC PORT AUTHORITY"
        ).upper()
        morning_title = f"{city_name} → {dest_name}"
        max_title_w = (batt_x - 16) - (b_x1 + 12)
        morning_title = ellipsize_to_width(
            draw, morning_title, font_title, max(50, max_title_w)
        )
        draw.text((b_x1 + 12, 15), morning_title, fill="black", font=font_title)

        loc_name = str(
            getattr(location_config, "location_name", "Hoboken City Hall")
            if location_config
            else "Hoboken City Hall"
        ).upper()
        agency = str(
            getattr(location_config, "transit_agency", "NJ TRANSIT")
            if location_config
            else "NJ TRANSIT"
        ).upper()
        sub_text = f"{loc_name} • {agency} {route_str} REAL-TIME"
        sub_text = ellipsize_to_width(
            draw, sub_text, font_header_sub, max(50, max_title_w)
        )
        draw.text((b_x1 + 12, 39), sub_text, fill="#555555", font=font_header_sub)

    draw.line([(20, 62), (width - 20, 62)], fill="black", width=2)

    if has_citibike:
        cb_y0 = 70
        cb_y1 = 416 if is_tall else 346
        cb_count = max(1, min(3, len(citibike_data)))
        gap = 11
        col_w = (width - 40 - (cb_count - 1) * gap) // cb_count

        for i, c in enumerate(citibike_data[:3]):
            cx0 = 20 + i * (col_w + gap)
            cx1 = cx0 + col_w

            draw.rounded_rectangle(
                [cx0, cb_y0, cx1, cb_y1],
                radius=10,
                fill="white",
                outline="black",
                width=2,
            )

            pill_h = 44
            draw.rounded_rectangle(
                [cx0, cb_y0, cx1, cb_y0 + pill_h],
                radius=10,
                fill="#f2f2f2",
                outline="black",
                width=2,
            )
            draw.rectangle(
                [cx0 + 1, cb_y0 + pill_h - 12, cx1 - 1, cb_y0 + pill_h],
                fill="#f2f2f2",
            )
            draw.line(
                [(cx0, cb_y0 + pill_h), (cx1, cb_y0 + pill_h)],
                fill="black",
                width=2,
            )

            walk_text = f"{c.get('walk_min', 0)} MIN"
            wb = draw.textbbox((0, 0), walk_text, font=font_walk)
            ww = wb[2] - wb[0]
            badge_x0 = cx1 - ww - 16
            draw.rounded_rectangle(
                [badge_x0, cb_y0 + 11, cx1 - 8, cb_y0 + 33],
                radius=4,
                fill="black",
            )
            draw.text(
                (cx1 - ww - 12, cb_y0 + 15), walk_text, fill="white", font=font_walk
            )

            card_title_font = font_card_title
            max_title_w = badge_x0 - (cx0 + 10) - 6
            for size in [16 if is_tall else 15, 14, 13, 12]:
                candidate_font = get_font(size, bold=True)
                tb = draw.textbbox((0, 0), c["name"].upper(), font=candidate_font)
                if (tb[2] - tb[0]) <= max_title_w:
                    card_title_font = candidate_font
                    break
            else:
                card_title_font = get_font(11, bold=True)

            title_line = ellipsize_to_width(
                draw, c["name"].upper(), card_title_font, max_title_w
            )
            draw.text(
                (cx0 + 10, cb_y0 + 6), title_line, fill="black", font=card_title_font
            )

            if c.get("is_offline"):
                draw.text(
                    (cx0 + 14, cb_y0 + (90 if is_tall else 80)),
                    "STATION OFFLINE",
                    fill="#666666",
                    font=font_card_title,
                )
                draw.text(
                    (cx0 + 14, cb_y0 + (125 if is_tall else 110)),
                    "Temporarily not renting",
                    fill="#888888",
                    font=font_sub_stat,
                )
            else:
                stat_y = cb_y0 + (64 if is_tall else 54)
                draw.text(
                    (cx0 + 12, stat_y),
                    str(c["ebikes"]),
                    fill="black",
                    font=font_hero_num,
                )
                num_box = draw.textbbox(
                    (cx0 + 12, stat_y), str(c["ebikes"]), font=font_hero_num
                )
                draw.text(
                    (num_box[2] + 8, stat_y + 16),
                    "E-BIKES",
                    fill="black",
                    font=font_hero_label,
                )
                draw.text(
                    (num_box[2] + 8, stat_y + 34),
                    "AVAILABLE",
                    fill="#555555",
                    font=font_walk,
                )

                div_y = stat_y + (86 if is_tall else 70)
                draw.line(
                    [(cx0 + 10, div_y), (cx1 - 10, div_y)], fill="#e0e0e0", width=1
                )

                draw.text(
                    (cx0 + 12, div_y + (16 if is_tall else 12)),
                    f"{c.get('classic', 0)} Classic Bikes",
                    fill="#333333",
                    font=font_sub_stat,
                )
                draw.text(
                    (cx0 + 12, div_y + (40 if is_tall else 32)),
                    f"{c.get('docks', 0)} Open Docks",
                    fill="#333333",
                    font=font_sub_stat,
                )

                badge_box_y0 = cb_y1 - (46 if is_tall else 42)
                badge_box_y1 = cb_y1 - (12 if is_tall else 12)
                draw.rounded_rectangle(
                    [cx0 + 10, badge_box_y0, cx1 - 10, badge_box_y1],
                    radius=6,
                    fill="#f8f8f8",
                    outline="black",
                    width=1,
                )
                if c["ebikes"] >= 4:
                    status_label = "E-BIKES READY"
                elif c["ebikes"] > 0:
                    status_label = "LOW E-BIKES"
                elif c["docks"] == 0:
                    status_label = "STATION FULL"
                else:
                    status_label = "NO E-BIKES"
                draw.text(
                    (cx0 + 18, badge_box_y0 + (9 if is_tall else 8)),
                    status_label,
                    fill="black",
                    font=font_badge,
                )

        bus_y0 = 422 if is_tall else 348
        bus_y1 = 542 if is_tall else 424
        draw.rounded_rectangle(
            [20, bus_y0, width - 20, bus_y1],
            radius=10,
            fill="white",
            outline="black",
            width=2,
        )

        header_h = 26 if is_tall else 24
        draw.rounded_rectangle(
            [20, bus_y0, width - 20, bus_y0 + header_h],
            radius=10,
            fill="#f4f4f4",
            outline="black",
            width=2,
        )
        draw.rectangle([21, bus_y0 + 14, width - 21, bus_y0 + header_h], fill="#f4f4f4")
        draw.line(
            [(20, bus_y0 + header_h), (width - 20, bus_y0 + header_h)],
            fill="black",
            width=1,
        )

        if location_config is None:
            bus_bar_title = "NJ TRANSIT 126 BUS • UPCOMING PORT AUTHORITY ARRIVALS"
        else:
            agency = str(
                getattr(location_config, "transit_agency", "NJ TRANSIT")
            ).upper()
            route_val = str(getattr(location_config, "route", "126"))
            dest_val = str(
                getattr(location_config, "destination", "PORT AUTHORITY")
            ).upper()
            if dest_val in ("NYC PORT AUTHORITY", "PORT AUTHORITY"):
                dest_val = "PORT AUTHORITY"
            bus_bar_title = f"{agency} {route_val} BUS • UPCOMING {dest_val} ARRIVALS"
        max_bus_bar_title_w = (width - 20 - 14) - 34
        bus_bar_title = ellipsize_to_width(
            draw, bus_bar_title, font_bus_bar_title, max_bus_bar_title_w
        )
        draw.text(
            (34, bus_y0 + (6 if is_tall else 5)),
            bus_bar_title,
            fill="#444444",
            font=font_bus_bar_title,
        )

        # Row offsets below the section header. The compact (800x480) box has only
        # 52px of content height, so its rows must sit tighter than the tall one;
        # using the tall offsets here pushed the "Following" line past the border.
        content_top = bus_y0 + header_h
        if is_tall:
            row_name, row_next, row_follow, row_third, row_empty = (
                10,
                32,
                50,
                68,
                34,
            )
        else:
            row_name, row_next, row_follow, row_empty = 2, 17, 34, 20

        num_stops = max(1, min(2, len(active_stops)))
        bus_col_w = (width - 40) // num_stops
        for i, stop_cfg in enumerate(active_stops[:num_stops]):
            sid = str(stop_cfg["id"])
            stop_name = str(stop_cfg["name"])
            walk_min = int(stop_cfg.get("walk_min", 0))
            bx0 = 20 + i * bus_col_w
            bx1 = bx0 + bus_col_w
            if i > 0:
                draw.line(
                    [(bx0, bus_y0 + header_h + 6), (bx0, bus_y1 - 6)],
                    fill="#dddddd",
                    width=1,
                )

            stop_name_y = content_top + row_name
            walk_badge = f"{walk_min}m walk"
            wb = draw.textbbox((0, 0), walk_badge, font=font_walk)
            ww = wb[2] - wb[0]
            draw.rounded_rectangle(
                [bx1 - ww - 18, stop_name_y - 2, bx1 - 10, stop_name_y + 14],
                radius=4,
                fill="#eeeeee",
                outline="black",
                width=1,
            )
            draw.text(
                (bx1 - ww - 14, stop_name_y), walk_badge, fill="black", font=font_walk
            )

            max_title_w = (bx1 - ww - 22) - (bx0 + 14)
            stop_name_str = ellipsize_to_width(
                draw, stop_name.upper(), font_bus_stop, max_title_w
            )
            draw.text(
                (bx0 + 14, stop_name_y),
                stop_name_str,
                fill="black",
                font=font_bus_stop,
            )

            # Column interior; text must not cross into the neighbouring column.
            col_max_w = (bx1 - 12) - (bx0 + 14)

            arrivals = stops_data.get(sid, [])
            if arrivals:
                first_bus = arrivals[0]
                eta = first_bus.get("eta", "")
                b_num = (
                    f" (Bus #{first_bus['vehicle_id']})"
                    if first_bus.get("vehicle_id")
                    else ""
                )
                next_line = ellipsize_to_width(
                    draw, f"Next: {eta}{b_num}", font_bus_eta, col_max_w
                )
                draw.text(
                    (bx0 + 14, content_top + row_next),
                    next_line,
                    fill="black",
                    font=font_bus_eta,
                )
                if len(arrivals) > 1:
                    next_eta = arrivals[1].get("eta", "")
                    follow_line = ellipsize_to_width(
                        draw, f"Following: {next_eta}", font_bus_meta, col_max_w
                    )
                    draw.text(
                        (bx0 + 14, content_top + row_follow),
                        follow_line,
                        fill="#555555",
                        font=font_bus_meta,
                    )
                if is_tall and len(arrivals) > 2:
                    third_eta = arrivals[2].get("eta", "")
                    third_line = ellipsize_to_width(
                        draw, f"Upcoming: {third_eta}", font_bus_meta, col_max_w
                    )
                    draw.text(
                        (bx0 + 14, content_top + row_third),
                        third_line,
                        fill="#777777",
                        font=font_bus_meta,
                    )
            else:
                status = (stop_status or {}).get(sid)
                msg, color = empty_state_message(status)
                msg_font = font_bus_meta if status == STATUS_ERROR else font_bus_eta
                msg = ellipsize_to_width(draw, msg, msg_font, col_max_w)
                draw.text(
                    (bx0 + 14, content_top + row_empty),
                    msg,
                    fill=color,
                    font=msg_font,
                )

    else:
        # Case B: Citi Bike is absent - Full-height adaptive bus hero cards
        card_y0 = 70
        card_y1 = 542 if is_tall else 424
        num_stops = max(1, min(3, len(active_stops)))

        if num_stops == 1:
            col_w = width - 40
            xs = [20]
        elif num_stops == 2:
            col_w = (width - 40 - 20) // 2
            xs = [20, 20 + col_w + 20]
        else:
            gap = 14
            col_w = (width - 40 - (num_stops - 1) * gap) // num_stops
            xs = [20 + i * (col_w + gap) for i in range(num_stops)]

        for i, stop_cfg in enumerate(active_stops[:num_stops]):
            x0 = xs[i]
            x1 = x0 + col_w
            y0 = card_y0
            y1 = card_y1

            draw.rounded_rectangle(
                [x0, y0, x1, y1],
                radius=10,
                fill="white",
                outline="black",
                width=2,
            )

            pill_h = 48 if is_tall else 44
            draw.rounded_rectangle(
                [x0, y0, x1, y0 + pill_h],
                radius=10,
                fill="#f2f2f2",
                outline="black",
                width=2,
            )
            draw.rectangle(
                [x0 + 1, y0 + pill_h - 12, x1 - 1, y0 + pill_h],
                fill="#f2f2f2",
            )
            draw.line([(x0, y0 + pill_h), (x1, y0 + pill_h)], fill="black", width=2)

            walk_min = int(stop_cfg.get("walk_min", 0))
            walk_text = f"{walk_min} MIN WALK"
            wb = draw.textbbox((0, 0), walk_text, font=font_walk)
            ww = wb[2] - wb[0]
            walk_btn_h = 24 if is_tall else 22
            walk_btn_y = y0 + (12 if is_tall else 11)
            draw.rounded_rectangle(
                [x1 - ww - 20, walk_btn_y, x1 - 10, walk_btn_y + walk_btn_h],
                radius=5,
                fill="black",
            )
            draw.text(
                (x1 - ww - 15, walk_btn_y + (5 if is_tall else 4)),
                walk_text,
                fill="white",
                font=font_walk,
            )

            max_stop_title_w = (x1 - ww - 25) - (x0 + 12)
            stop_name_str = ellipsize_to_width(
                draw, stop_cfg["name"].upper(), font_stop_name, max_stop_title_w
            )
            draw.text(
                (x0 + 12, y0 + (6 if is_tall else 5)),
                stop_name_str,
                fill="black",
                font=font_stop_name,
            )

            stop_sub = str(stop_cfg.get("subtitle", f"Stop #{stop_cfg.get('id', '')}"))
            stop_sub_str = ellipsize_to_width(
                draw, stop_sub, font_header_sub, max_stop_title_w
            )
            draw.text(
                (x0 + 12, y0 + (28 if is_tall else 26)),
                stop_sub_str,
                fill="#555555",
                font=font_header_sub,
            )

            sid = str(stop_cfg["id"])
            arrivals = stops_data.get(sid, [])
            if not arrivals:
                status = (stop_status or {}).get(sid)
                if status == STATUS_ERROR:
                    headline, subtext, headline_color = (
                        "LIVE DATA UNAVAILABLE",
                        "Could not reach transit feed.\nRetrying automatically.",
                        "#aa0000",
                    )
                else:
                    headline, subtext, headline_color = (
                        "NO UPCOMING DEPARTURES",
                        "No departures currently tracked\nfor this stop.",
                        "#444444",
                    )
                empty_font = (
                    get_font(13, bold=True)
                    if num_stops >= 3
                    else (font_stop_name if num_stops > 1 else font_title)
                )
                empty_x = x0 + (16 if num_stops >= 3 else 24)
                headline_str = ellipsize_to_width(
                    draw, headline, empty_font, (x1 - 12) - empty_x
                )
                draw.text(
                    (empty_x, y0 + (90 if is_tall else 70)),
                    headline_str,
                    fill=headline_color,
                    font=empty_font,
                )
                sub_font = get_font(11, bold=False) if num_stops >= 3 else font_detail
                subtext_lines = [
                    ellipsize_to_width(draw, sline, sub_font, (x1 - 12) - empty_x)
                    for sline in subtext.split("\n")
                ]
                draw.text(
                    (empty_x, y0 + (125 if is_tall else 105)),
                    "\n".join(subtext_lines),
                    fill=("#aa0000" if status == STATUS_ERROR else "#666666"),
                    font=sub_font,
                )
                box_h0 = y1 - (88 if is_tall else 72)
                box_h1 = y1 - 14
                draw.rounded_rectangle(
                    [x0 + 12, box_h0, x1 - 12, box_h1],
                    radius=7,
                    fill="#fafafa",
                    outline="#bbbbbb",
                    width=1,
                )
                tip = (
                    "Check your network / server connection"
                    if status == STATUS_ERROR
                    else "Tip: Check transit agency timetables"
                )
                tip_font = get_font(10, bold=False) if num_stops >= 3 else font_footer
                tip_str = ellipsize_to_width(
                    draw,
                    tip,
                    tip_font,
                    (x1 - 16) - (x0 + (16 if num_stops >= 3 else 20)),
                )
                draw.text(
                    (
                        x0 + (16 if num_stops >= 3 else 20),
                        box_h0 + (18 if is_tall else 16),
                    ),
                    tip_str,
                    fill="#666666",
                    font=tip_font,
                )
            else:
                first_bus = arrivals[0]
                first_eta_raw = first_bus.get("eta", "")
                first_min = parse_minutes(first_eta_raw)
                cy = y0 + (62 if is_tall else 56)

                if first_min is not None:
                    if first_min == 0:
                        cd_str = "DUE"
                        unit_str = ""
                    else:
                        cd_str = str(first_min)
                        unit_str = "MIN"
                else:
                    time_match = re.search(
                        r"\b(\d{1,2}:\d{2}(?:\s*[AP]M)?)\b",
                        first_eta_raw,
                        re.IGNORECASE,
                    )
                    if time_match:
                        cd_str = time_match.group(1)
                    else:
                        cd_str = first_eta_raw[:7].strip() if first_eta_raw else "--"
                    unit_str = ""

                f_num = (
                    get_font(44 if is_tall else 40, bold=True)
                    if num_stops >= 3
                    else font_countdown_num
                )
                f_unit = (
                    get_font(16 if is_tall else 15, bold=True)
                    if num_stops >= 3
                    else font_countdown_unit
                )
                x_text_offset = 12 if num_stops >= 3 else 16
                draw.text((x0 + x_text_offset, cy), cd_str, fill="black", font=f_num)
                c_bbox = draw.textbbox((x0 + x_text_offset, cy), cd_str, font=f_num)
                unit_x = c_bbox[2] + 4

                if unit_str:
                    draw.text(
                        (
                            unit_x,
                            cy
                            + (20 if num_stops >= 3 else (34 if not is_tall else 38)),
                        ),
                        unit_str,
                        fill="black",
                        font=f_unit,
                    )

                badge_y = cy + (10 if num_stops >= 3 else 14)
                if first_min is not None:
                    if (
                        "board" in first_eta_raw.lower()
                        or "all aboard" in first_eta_raw.lower()
                    ):
                        badge_label = "ALL ABOARD"
                        badge_bg, badge_fg = "black", "white"
                    elif first_min <= walk_min:
                        badge_label = "RUN!" if num_stops >= 3 else "RUN! LEAVING SOON"
                        badge_bg, badge_fg = "black", "white"
                    elif first_min <= walk_min + 3:
                        badge_label = "WALK NOW"
                        badge_bg, badge_fg = "black", "white"
                    elif first_min <= walk_min + 7:
                        badge_label = "GET READY"
                        badge_bg, badge_fg = "#f0f0f0", "black"
                    else:
                        badge_label = "ON TIME"
                        badge_bg, badge_fg = "#f0f0f0", "black"

                    f_badge = get_font(10, bold=True) if num_stops >= 3 else font_badge
                    bb = draw.textbbox((0, 0), badge_label, font=f_badge)
                    bw = bb[2] - bb[0]
                    badge_x = x1 - bw - (16 if num_stops >= 3 else 24)
                    badge_h = 22 if num_stops >= 3 else 24
                    draw.rounded_rectangle(
                        [
                            badge_x,
                            badge_y,
                            badge_x + bw + (10 if num_stops >= 3 else 14),
                            badge_y + badge_h,
                        ],
                        radius=5,
                        fill=badge_bg,
                        outline="black",
                        width=1 if num_stops >= 3 else 2,
                    )
                    draw.text(
                        (badge_x + (5 if num_stops >= 3 else 7), badge_y + 4),
                        badge_label,
                        fill=badge_fg,
                        font=f_badge,
                    )

                card_text_max_w = (x1 - 10) - (x0 + x_text_offset)
                sched_str = ellipsize_to_width(
                    draw,
                    f"Estimated: {first_eta_raw}",
                    font_detail,
                    card_text_max_w,
                )
                draw.text(
                    (x0 + x_text_offset, cy + (76 if not is_tall else 82)),
                    sched_str,
                    fill="#333333",
                    font=font_detail,
                )

                bus_num = first_bus.get("vehicle_id")
                load = first_bus.get("occupancy")
                if load == "EMPTY":
                    load_clean = "Seats Available"
                elif load:
                    load_clean = load.replace("_", " ").title()
                else:
                    load_clean = None
                if bus_num and load_clean:
                    bus_meta = f"Bus #{bus_num}  •  {load_clean}"
                elif bus_num:
                    bus_meta = f"Bus #{bus_num}"
                elif load_clean:
                    bus_meta = f"Status: {load_clean}"
                elif first_bus.get("live"):
                    bus_meta = "Live prediction"
                else:
                    bus_meta = "Scheduled — no live vehicle"
                bus_meta = ellipsize_to_width(
                    draw, bus_meta, font_detail, card_text_max_w
                )
                draw.text(
                    (x0 + x_text_offset, cy + (98 if not is_tall else 104)),
                    bus_meta,
                    fill="#444444",
                    font=font_detail,
                )

                box_y0 = y1 - (88 if is_tall else 72)
                box_y1 = y1 - 14
                draw.rounded_rectangle(
                    [x0 + 12, box_y0, x1 - 12, box_y1],
                    radius=7,
                    fill="#f8f8f8",
                    outline="black",
                    width=1,
                )
                inner_left = x0 + (16 if num_stops >= 3 else 20)
                inner_right = x1 - (12 if num_stops >= 3 else 14)
                inner_max_w = inner_right - inner_left

                if len(arrivals) > 1:
                    next_bus = arrivals[1]
                    next_eta = next_bus.get("eta", "Scheduled")
                    next_bus_num = (
                        f" (Bus #{next_bus['vehicle_id']})"
                        if next_bus.get("vehicle_id")
                        else ""
                    )
                    draw.text(
                        (inner_left, box_y0 + (8 if is_tall else 7)),
                        "UPCOMING BUSES:",
                        fill="#555555",
                        font=font_footer,
                    )
                    route_display = str(
                        next_bus.get("route")
                        or (
                            getattr(location_config, "route", "126")
                            if location_config
                            else "126"
                        )
                    )
                    dest_display = str(next_bus.get("destination") or "NYC")
                    line1 = ellipsize_to_width(
                        draw,
                        f"{route_display} to {dest_display} → {next_eta}{next_bus_num}",
                        font_footer,
                        inner_max_w,
                    )
                    draw.text(
                        (inner_left, box_y0 + (24 if is_tall else 22)),
                        line1,
                        fill="black",
                        font=font_footer,
                    )
                    if is_tall and len(arrivals) > 2:
                        third_bus = arrivals[2]
                        third_eta = third_bus.get("eta", "Scheduled")
                        third_line = ellipsize_to_width(
                            draw,
                            f"{route_display} to {dest_display} → {third_eta}",
                            font_footer,
                            inner_max_w,
                        )
                        draw.text(
                            (inner_left, box_y0 + 40),
                            third_line,
                            fill="#555555",
                            font=font_footer,
                        )
                    elif not is_tall and len(arrivals) > 2:
                        third_bus = arrivals[2]
                        third_eta = third_bus.get("eta", "")
                        if third_eta:
                            third_line = ellipsize_to_width(
                                draw,
                                f"Followed by: {third_eta}",
                                font_footer,
                                inner_max_w,
                            )
                            draw.text(
                                (inner_left, box_y0 + 37),
                                third_line,
                                fill="#777777",
                                font=font_footer,
                            )
                else:
                    draw.text(
                        (inner_left, box_y0 + (12 if is_tall else 10)),
                        "NO FURTHER BUSES TRACKED",
                        fill="#888888",
                        font=font_footer,
                    )
                    draw.text(
                        (inner_left, box_y0 + (28 if is_tall else 25)),
                        "Check schedule for late departures",
                        fill="#aaaaaa",
                        font=font_footer,
                    )

    draw_bottom_button_bar(draw, width, height, active_view="morning")
