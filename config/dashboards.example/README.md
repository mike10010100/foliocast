# Modular Dashboard Examples

This directory contains reference templates demonstrating how to create custom e-ink dashboards using Foliocast's declarative layout DSL.

## Usage

To activate any custom dashboard:
1. Copy the desired `.json` specification file into `config/dashboards/`:
   ```bash
   cp config/dashboards.example/bus_focus.json config/dashboards/my_bus_board.json
   ```
2. The Foliocast server will automatically detect and register the new dashboard.
3. Access the dashboard via:
   - Web preview: `http://localhost:8000/?view=my_bus_board`
   - Direct image: `http://localhost:8000/dashboard.png?view=my_bus_board`
   - API spec: `http://localhost:8000/dashboards/my_bus_board`

## Layout Nodes & Widgets

Custom dashboards use a JSON tree structure with flexible containers and widgets:

- **Containers**:
  - `vstack`: Vertical container allocating children with optional `flex`, `padding_x`, `gap`.
  - `hstack`: Horizontal row dividing children with column gaps.
  - `box`: Card wrapper with borders, background fill, and padding.
- **Universal Widgets**:
  - `header`: Standard top status header with route badge, title, subtitle, clock, and battery.
  - `metric_card`: Single telemetry readout with value, unit, subtitle, and optional radar gauge.
  - `entity_list`: Tabular list of items with status pills and timestamps.
  - `text_notice`: Full-width banner or announcement box.
  - `button_bar`: Bottom touch bar matching Kindle hardware touch zones.
- **Specialized Transit & Weather Widgets**:
  - `weather_hero`: Prominent temperature readout, feels-like, and vector condition glyph.
  - `weather_forecast`: Multi-day extended weather outlook strip.
  - `bus_hero`: Route 126 bus departure countdown cards.
  - `bus_bar`: Compact single-line bus arrivals strip.
  - `citibike_hero`: Large Citi Bike station inventory cards.
  - `citibike_bar`: Compact single-line Citi Bike dock availability strip.
