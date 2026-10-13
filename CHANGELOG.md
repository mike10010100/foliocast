# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.42.5] - 2026-10-13

### Fixed

- **Test Suite Location Store Isolation & Local Config Preservation** (`tests/__init__.py`, `tests/test_dashboard_views.py`, `tests/test_server.py`, `tests/test_m4_geometry_adversarial.py`, `tests/test_m4_challenger_http_concurrency.py`, `tests/test_location_config.py`):
  - **Isolated Test Fixtures**: Added `IsolatedLocationMixin` and initialized `_global_test_loc_dir` along with `LOCATION_CONFIG` environment redirection in `tests/__init__.py` so tests always operate in clean temporary isolation and never read or write host configuration files.
  - **Eliminated Config Overwrite Leakage**: Removed rogue `reset_location_config()` calls during test teardown in `tests/test_m4_challenger_http_concurrency.py` and wrapped mutating test cases in `tests/test_dashboard_views.py`, `tests/test_server.py`, and `tests/test_m4_geometry_adversarial.py` with `IsolatedLocationMixin`.
  - **Restored User Location Configuration**: Restored user's configured location (`919 Park Ave`, `40.7482, -74.0305`) from cache, ensuring the active dashboard and API endpoints immediately reflect the user's config rather than default municipal landmarks.
  - **Regression Coverage**: Added `test_store_reset_preserves_custom_file_on_disk` and `test_repo_config_location_json_never_modified_by_test_operations` in `tests/test_location_config.py` ensuring store resets never mutate existing on-disk location files and test runs never modify repository configuration.

---

## [1.42.4] - 2026-10-12

### Fixed

- **Real-Testing Campaign Invariant Rectifications** (`server/canvas.py`, `server/dashboard_dsl.py`, `server/location.py`, `server/transit_provider.py`, `tests/test_real_testing_regressions.py`):
  - **Status Abbreviation Honesty**: Updated `format_hero_eta` to map unmonitored timetable and status arrivals (`Scheduled`, `Canceled`, `Delayed`) to canonical, readable transit abbreviations (`SCHED`, `CANC`, `DELAY`) instead of raw 7-character slicing that truncated `"Scheduled"` to `"Schedul"`. Updated codified test assertions in `tests/test_hero_eta_and_badges.py`.
  - **Zero-Minute Walk Support**: Allowed `walk_min=0` across `LocationConfig` stops overrides and `Hoboken126Provider.resolve_stops`, supporting users residing directly at or adjacent to transit stops in alignment with `docs/api.md` and transit catalog distance math.
  - **Weather Hero Layout Containment**: Bounded `wx.condition` and daily high/low temperatures against card right boundaries using `ellipsize_to_width`, preventing long descriptions (e.g. WMO 99 `Thunderstorm with heavy hail`) from overflowing card boundaries and colliding with adjacent metric cards.
  - **Header Subtitle Containment**: Constrained `HeaderWidget` subtitles to available left space, preventing visual overlap with battery and time indicators.
  - **Regression Verification Suite**: Added `tests/test_real_testing_regressions.py` preserving failure cases discovered during ground-up real-testing execution.

---

## [1.42.3] - 2026-10-12

### Fixed

- **Off-Peak Transit Countdown, Status Badge, and Horizon Copy Mismatch** (`server/canvas.py`, `server/evening_view.py`, `server/morning_view.py`, `tests/test_hero_eta_and_badges.py`):
  - **Clock Time Hero for Far-Off Departures**: Replaced raw triple-digit minute countdowns (e.g. `160 MIN`) with human-readable departure clock times (e.g. `4:09 PM` or `2h 40m`) when next arrival is 60+ minutes away (`format_hero_eta`), with proportional typography and baseline alignment that eliminates visual glitches.
  - **Badge Telemetry Honesty (`SCHEDULED` vs `ON TIME`)**: Centralized badge resolution (`resolve_badge`, `is_arrival_live`) across morning and evening views. Prevented unmonitored static schedule departures lacking active vehicle telemetry from claiming `ON TIME`; unmonitored trips now accurately display `SCHEDULED`.
  - **Footer Copy Horizon Consistency**: Eliminated contradictory copy where cards with departures beyond the hour reported `"No further buses in next 60 min"`. Updated empty upcoming list copy to `"No other departures scheduled"` when the initial departure is beyond 60 minutes or unmonitored.
  - **Real-Testing Verification & Regression Coverage**: Added end-to-end regression and unit test suite in `tests/test_hero_eta_and_badges.py` validating hero formatting, live status detection, badge resolution, and dashboard image rendering.

---

## [1.42.2] - 2026-10-12

### Changed

- **Streamlined Dashboard Views & Hardware Button Alignment** (`server/dashboards.py`, `server/server.py`, `server/render_dashboard.py`, `config/dashboards/`):
  - Aligned desktop web dashboard navigation 1:1 with Kindle hardware touch buttons: `[ BUSES ]`, `[ CITI BIKE ]`, and `[ WEATHER ]`.
  - Reorganized redundant single-service focus layouts (`bus_focus.json` and `citibike_focus.json`) into `config/dashboards.example/` as custom DSL references with dedicated documentation (`config/dashboards.example/README.md`).
  - Added backward-compatible fallback aliases for `bus_focus` / `buses` -> `evening` and `citibike_focus` / `bikes` -> `morning` in `DashboardRegistry.get()`, `resolve_view()`, and server query routing.
  - Cleaned up example DSL definitions by removing duplicate top header nodes to prevent vertical text collisions when combining hero widgets with full-page displays.

### Fixed

- **Web Dashboard UX Hazards & Accessibility Remediation** (`server/server.py`):
  - **Non-Destructive Auto-Refresh**: Removed the hard 30-second `<meta http-equiv="refresh">` tag that wiped active user input in the Schedule JSON editor and collapsed details drawers. Implemented smart in-place image refresh (`setInterval`) that updates dashboard visuals without page reloads while inputs or editor drawers are active.
  - **Inline Accessible Diagnostics Modal**: Replaced asynchronous `window.open()` popups (frequently blocked by modern browser popup blockers) with an accessible `<dialog id="diagModal">` container and live log viewer.
  - **Unified Non-Blocking Notifications**: Replaced blocking native browser `alert()` dialogs with an animated `#toastNotification` status banner for all token saves, tracker toggles, fleet broadcasts, and device action queues.
  - **Form Semantics & Accessibility Compliance**: Wrapped the control token input and action button in a semantic `<form id="tokenForm">` with `autocomplete="current-password"`, and added standard `name` and `aria-label` attributes to all fleet and schedule `<select>` controls to eliminate browser DOM audit warnings.
  - **Responsive Fleet Table Action Cell**: Added `.device-actions-cell` CSS rule allowing action/diag/mode control groups to wrap cleanly on narrower viewports without horizontal table overflow.

---

## [1.42.1] - 2026-10-12

### Fixed

- **Weather Dashboard Precipitation 100% Boundary Collision** (`server/dashboard_dsl.py`):
  - Fixed an edge case where precipitation probability reaching 100% caused the percentage text (`100%`) to collide with or overflow past the right border of the metric card container across standard (800x480) and tall (800x600) layouts.
  - Implemented dynamic typography fitting to scale down font size when 3-digit percentages exceed available card inner width, maintaining vertical alignment with the umbrella glyph.
  - Right-aligned the progress meter scale `100%` label to prevent horizontal overshoot past the meter bar boundary.
  - Added real-testing reproduction script (`scripts/reproduce_precip_collision.py`) and regression test suites in `tests/test_dashboards.py`, `tests/test_render_dashboard.py`, and `tests/test_server_dashboard_http.py`.

---

## [1.42.0] - 2026-10-12

### Changed

- **FolioCast Clean Slate Protocol & Service Standardization** (`server/discovery.py`, `server/server.py`, `client-go/discovery.go`, `client-go/launcher/`):
  - Standardized UDP discovery protocol strictly on `FOLIOCAST_DISCOVER` and `FOLIOCAST_OFFER`, deprecating legacy transit tracker / bus tracker probe shims.
  - Streamlined mDNS service registration strictly to `_foliocast._tcp.local.`.
  - Standardized `/identity` endpoint response strictly to `{"service": "foliocast", "version": ...}`.
  - Promoted `FolioCast.sh` to primary Kindle launcher script while maintaining `TransitTracker.sh` as a relative symlink for legacy Kindle home screen shortcut compatibility.
  - Standardized client binary cross-compilation target to `foliocast-arm`, staging both `/foliocast-arm` and `/tracker-arm` routes on the server for zero-downtime OTA transitions.

### Added

- **Kindle USB One-Click Installer** (`scripts/install_kindle_usb.sh`):
  - Created automated Kindle Paperwhite installer script to detect USB-mounted Kindle filesystems, deploy `FolioCast.sh` and `TransitTracker.sh` to documents, build and stage `foliocast-arm`, and configure `foliocast_server.txt`.
  - Integrated script validation into `make check-sh`.

---

## [1.41.0] - 2026-10-11

### Changed

- **FolioCast Container Architecture & Stack Rebranding** (`docker-compose.yml`, `Dockerfile`, `scripts/deploy.sh`, `.github/workflows/ci.yml`):
  - Renamed primary Docker service, container name, and image targets to `foliocast` (`foliocast:v1.41.0` and `foliocast:latest`).
  - Migrated Docker Compose project to `foliocast` with dedicated named volume `foliocast-cache`.
  - Updated unprivileged container runtime user and group to `foliocast`.
  - Updated CI workflows and deployment scripts to orchestrate the `foliocast` stack.

- **Dual-Stack Discovery & Identity Backward Compatibility** (`server/discovery.py`, `server/server.py`, `client-go/discovery.go`, `client-go/launcher/TransitTracker.sh`):
  - Enabled dual UDP discovery probes and offers (`FOLIOCAST_DISCOVER` / `FOLIOCAST_OFFER` alongside `TRANSIT_TRACKER_DISCOVER` / `TRANSIT_TRACKER_OFFER`).
  - Added dual mDNS registration for both `_foliocast._tcp.local.` and `_transittracker._tcp.local.`.
  - Updated `/identity` endpoint to report `foliocast` service identity with backwards-compatible `legacy_service: transit-tracker`.
  - Provided `client-go/launcher/FolioCast.sh` launcher entrypoint.
  - Updated Go module path to `github.com/mike10010100/foliocast/client-go`.

---

## [1.40.2] - 2026-10-11

### Changed

- **Mise Toolchain & Linter Modernization** (`.golangci.yml`, `client-go/actions.go`):
  - Migrated `.golangci.yml` to the `version: "2"` configuration schema required by modern `golangci-lint` (v2.14.0+).
  - Modernized `client-go/actions.go` string building to use `fmt.Fprintf` over `b.WriteString(fmt.Sprintf(...))` conforming to `staticcheck` QF1012.
  - Verified end-to-end compatibility across Go 1.26, Python 3.11, shellcheck, and hadolint via local `mise` environment.

---

## [1.40.1] - 2026-10-11

### Changed

- **Scrub Personal Location Defaults & Anonymize Civic Fallbacks** (`server/location.py`, `server/weather.py`, `server/morning_view.py`, `server/evening_view.py`, `config/location.example.json`):
  - Replaced hardcoded personal address defaults with municipal civic landmark: **Hoboken City Hall** (`94 Washington St`, `40.7371, -74.0305`).
  - Anonymized default dashboard header banners to civic labels (`HOBOKEN CITY HALL • E-BIKE PRIORITY & 126 BUS`).
  - Updated all documentation examples, API schemas, and test suites to use public municipal coordinates and stops.

---

## [1.40.0] - 2026-10-11

### Added

- **Location Configuration & Store Architecture** (`server/location.py`, `server/paths.py`, `config/location.example.json`):
  - Added `LocationConfig` dataclass supporting user-configured coordinates, location names, addresses, routes, destinations, and walking distance thresholds.
  - Built thread-safe `LocationConfigStore` supporting stat-based hot reload, atomic temporary-file replacement, and multi-tier configuration precedence (hardcoded defaults -> `config/location.json` / `$LOCATION_CONFIG` -> `TRACKER_*` environment variables).
  - Provided clean out-of-the-box defaults for Hoboken, NJ with Route 126 and Hoboken Citi Bike stations when no config is provided.
  - Committed documented configuration template in `config/location.example.json`.

- **Live Location & Transit Management REST API** (`server/server.py`):
  - Added `GET /api/location` open endpoint providing real-time telemetry inspection of active location parameters, dynamically resolved bus stops, and nearest Citi Bike docks.
  - Added `POST /api/location` control endpoint authenticated via `X-Tracker-Token` (validated using `TRACKER_CONTROL_TOKEN`) for live runtime configuration updates, supporting JSON and form payloads with automatic data cache invalidation and atomic persistence.

- **Citi Bike GBFS Station Auto-Discovery Engine** (`server/citibike_discovery.py`, `server/data/citibike_stations_seed.json`):
  - Integrated live GBFS `station_information.json` resolver with 24-hour disk caching (`cache/citibike_stations.json`) and graceful fallback.
  - Bundled an offline seed cache (`server/data/citibike_stations_seed.json`) with 2,500+ NYC/NJ stations to guarantee deterministic CI execution and fast container initialization.
  - Implemented pedestrian geometry engine computing Haversine great-circle distance with a 1.25 urban circuity factor and 80 m/min walking speed.
  - Implemented station name normalizer converting raw cross-street titles into clean, legible intersection labels.
  - Implemented graceful out-of-coverage handling returning `[]` when coordinates are beyond micro-mobility coverage.

- **Extensible Multi-Modal Transit Stop Provider Interface** (`server/transit_provider.py`, `server/transit_catalog.py`):
  - Architected abstract `TransitStopProvider` interface supporting dynamic registry, decorator-based provider registration, and multi-agency transit extension (Hoboken, Jersey City, NYC MTA).
  - Implemented `Hoboken126Provider` with curated Route 126 catalog for Washington St and Clinton St corridors.
  - Implemented dual-corridor inbound pairing algorithm pairing the closest Washington St stop with the closest Clinton St stop with calculated walking minutes.
  - Added support for explicit custom stop overrides (`stops_override`) bypassing proximity calculations.

- **Dynamic Dashboard Layout Adaptation & Weather Wiring** (`server/weather.py`, `server/morning_view.py`, `server/evening_view.py`, `server/render_dashboard.py`):
  - Connected `WeatherTracker` coordinates and location naming directly to active `LocationConfig`.
  - Added dynamic header badges, route titles, and subheadings across morning and evening dashboard views.
  - Adapted `morning_view.py` layout to automatically expand bus departures into high-visibility hero cards when Citi Bike is absent or micro-mobility is disabled, eliminating empty grids.

- **End-to-End Real-Testing Verification Pipeline** (`.agents/skills/real-testing/`):
  - Integrated `real-testing` behavioral verification methodology exercising live daemon HTTP endpoints (`/api/location`, `/dashboard.png`), varied input matrices, failure injection, and independent system invariants.

### Fixed

- **Citi Bike Empty Station List Fallback Bug** (`server/citibike.py`):
  - Fixed falsy evaluation bug where empty station list `[]` incorrectly triggered `stations or DEFAULT_STATIONS`, ensuring out-of-coverage or disabled micro-mobility cleanly returns zero stations.

- **Location Config Atomic Write Race Condition** (`server/location.py`):
  - Enforced POSIX atomic rename semantics and mutex locking during configuration persistence to prevent partial writes during concurrent requests.

---

## [1.39.5] - 2026-10-11

### Changed

- **Weather Dashboard Dead Space Elimination & Responsive Scaling** (`server/dashboard_dsl.py`, `server/dashboards.py`, `config/dashboards/weather.json`):
  - **Eliminated Dead Space on Native Kindle Paperwhite (800×600 / 1648×1236)**: Synchronized `config/dashboards/weather.json` and `_builtin_weather_spec` with exact fixed heights on header (`62px`) and button bar (`42px`), allocating proportional flex height (`1.7` : `1.0`) between the hero/radar row and the extended forecast strip.
  - **3-Column Telemetry Grid on Weather Hero**: On tall displays (`rect.h >= 240`), upgraded `WeatherHeroWidget` with larger vector iconography (`84px`), larger temperature typography (`72pt`), a horizontal dividing rule, and a dedicated 3-column telemetry grid (`FEELS LIKE`, `HUMIDITY`, `WIND SPEED`) with vertical dividers and daily temperature range context.
  - **Visual Precipitation Gauge on Radar Card**: Enhanced `MetricCardWidget` on tall screens with a proportional e-ink progress gauge (`0%`, `50%`, `100%` scale), larger umbrella glyph (`64px`), 56pt percentage readout, likelihood status description (`Precipitation highly likely`, `Scattered showers possible`, `Dry commute expected`), and horizontally aligned divider rule.
  - **Extended Forecast Breathing Room**: Converted `WeatherForecastWidget` to flex height, allowing the extended forecast strip to expand comfortably (`173px` on PW5 vs `128px` on 480p) with 56px weather icons, 16pt bold temperatures, legible condition text, and dynamic N-day banner headers.
  - **Cross-Platform Tofu Elimination**: Replaced Unicode emoji glyphs in the commute advisory banner with crisp vector/standard geometric glyphs (`▲`, `●`) to guarantee clean, sharp rendering without missing glyph boxes on embedded Linux and e-ink displays.

---

## [1.39.4] - 2026-10-11

### Added

- **Polyglot Runtime & Toolchain Management with mise** (`.mise.toml`): Added configuration pinning Go 1.26, Python 3.11, `golangci-lint`, `shellcheck`, and `hadolint`, with automatic `PYTHONPATH="server"` environment injection.
- **Cross-Platform Launcher Test Support** (`tests/test_launcher.sh`): Made integration tests portable across macOS and Linux by gracefully skipping Linux ELF-only binary executions on non-Linux hosts while remaining 100% enforced in Linux CI.

### Changed

- **Clean-Clone Docker Compose Experience** (`docker-compose.yml`): Defaulted `ALLOW_UNSIGNED_OTA` to `1` and fallback `ota_signing_key` file to `/dev/null` for local development so `docker compose up -d` works immediately on fresh checkouts without requiring host keygen.
- **Documentation & Link Hygiene** (`docs/development.md`, `docs/hardware_kindle.md`, `README.md`):
  - Fixed hardcoded machine paths (`file:///home/mike10010100/...`) into clean relative links.
  - Documented `mise` quick-start instructions in `docs/development.md`.
  - Synchronized `README.md` bottom button bar diagram and touch controls table with the actual 4-button layout (`BUSES`, `CITI BIKE`, `WEATHER`, `↻ REFRESH`) and `(☼)` brightness toggle.
  - Clarified Kindle binary compilation requirements when running under Option B (Local Python server).
- **Modernized Python Tooling Target** (`pyproject.toml`): Updated Mypy target to Python 3.11 to match runtime and eliminate deprecation warnings.
- **Expanded Environment Template** (`.env.example`): Added comprehensive documentation for server port, timezone, control tokens, client modes, schedule configuration, and signing parameters.

---

## [1.39.3] - 2026-10-11

### Changed

- **Desktop Web Dashboard Full-Resolution Kindle Screen by Default** (`server/server.py`):
  - Upgraded the desktop web dashboard view (`GET /` and `GET /index.html`) to default to the native Kindle Paperwhite 5 high-DPI display resolution (1648×1236, `scale=2.06`, `rotate=0`, unrotated landscape) rather than the compact 800×480 screen.
  - Added responsive CSS scaling (`max-height: 82vh`, `max-width: 95vw`, `object-fit: contain`) so the 1648×1236 dashboard comfortably fits laptop and desktop viewports without excessive vertical scrolling while retaining 300 PPI clarity.
  - Added a **Resolution** switcher (`Kindle PW5 Native (1648x1236)` vs `Standard (800x480)`) and direct image links for both native landscape and hardware-rotated portrait buffers.
  - Propagated `screen`, `present`, and `mock` query parameters across the View Mode switcher links (`Auto`, `Morning`, `Evening`, `Weather`, etc.).
  - Preserved browser preview fleet isolation: browser previews fetching full-resolution Kindle images without telemetry do not register dummy devices in the fleet registry.

---

## [1.39.2] - 2026-10-11

### Added

- **Vector Weather Iconography Engine** (`server/weather_icons.py`): Built a dedicated, scalable vector meteorological icon rendering library for e-ink dashboards. Generates crisp, high-contrast black-and-white vector glyphs for all WMO weather interpretation codes (`SUN`, `CLEAR`, `MOSTLY_SUN`, `PARTLY_CLOUD`, `CLOUDY`, `OVERCAST`, `DRIZZLE`, `LIGHT_RAIN`, `RAIN`, `HEAVY_RAIN`, `SHOWERS`, `THUNDER`, `THUNDERSTORM`, `SNOW`, `LIGHT_SNOW`, `HEAVY_SNOW`, `FREEZE_RAIN`, `FOG`, `WIND`, `UMBRELLA`, `PRECIPITATION`).
- **ScaledDraw Vector Curves** (`server/canvas.py`): Added `arc()`, `pieslice()`, and `chord()` proxy methods to `ScaledDraw` to support curved vector weather iconography and high-DPI scaling across native panel resolutions.

### Changed

- **Weather Dashboard Visual Parity & Layout Overhaul** (`server/dashboard_dsl.py`, `server/dashboards.py`): Redesigned the built-in weather dashboard to achieve visual parity with the Morning and Evening transit views:
  - **Header Alignment & Separator Rule**: Enforced 20px page margins, adaptive title sizing, and the iconic 2px black horizontal header divider line (`y = 62`).
  - **Card Pill Banners & 2px Borders**: Upgraded all weather cards (`WeatherHeroWidget`, `MetricCardWidget`, `WeatherForecastWidget`) to use standard 2px black borders (`radius=10`) with `#f2f2f2` pill headers and dividing rules.
  - **Hero Condition & Commute Advisory**: Added prominent 72x72 vector condition iconography, bold temperature typography, and a bottom commute advisory banner (`FAVORABLE COMMUTE CONDITIONS`, `RAIN EXPECTED`, `BREEZY`, `CHILLY`).
  - **Precipitation Card Iconography & Status**: Added 52x52 umbrella/droplet iconography and dynamic status pills (`DRY CONDITIONS`, `CHANCE OF RAIN`, `RAIN EXPECTED`).
  - **4-Day Forecast Strip**: Styled the 4-day outlook to match the bottom bus/citibike transit strips, featuring a `#f4f4f4` section banner, vertical column dividers, per-day vector weather icons, temperatures, and rain probabilities.

---

## [1.39.1] - 2026-10-11

### Changed

- **Top-Right Header Brightness Toggle** (`server/canvas.py`, `server/morning_view.py`, `server/evening_view.py`, `server/dashboard_dsl.py`): Moved frontlight brightness toggle to the top-right header, positioned immediately to the left of the time and date in a compact button with crisp sun-like iconography (central disc and 8 radial rays scaled natively via `ScaledDraw.ellipse`). Supported across morning, evening, and modular DSL dashboards with `show_brightness` toggle.
- **Bottom Bar Weather Dashboard Button** (`server/canvas.py`, `server/dashboard_dsl.py`, `client-go/gesture.go`, `client-go/input.go`): Replaced the bottom button bar's brightness button with a dedicated `WEATHER` view button (`[ BUSES ] [ CITI BIKE ] [ WEATHER ] [ ↻ REFRESH ]`). Active view is highlighted with inverted fill when displaying the weather dashboard.
- **Kindle Gesture Routing for Weather and Brightness** (`client-go/gesture.go`, `client-go/input.go`): Added `OnWeatherTap` to switch to `weather` view upon bottom bar tap, and `OnBrightnessTap` (with `OnLightTap` compatibility) to trigger frontlight cycling upon tapping the top-right brightness button zone.

---

## [1.39.0] - 2026-10-11

### Added

- **Modular Dashboard Architecture & Declarative Layout DSL** (`server/dashboard_dsl.py`, `server/dashboards.py`): Built a flexbox-inspired declarative layout engine (`VStack`, `HStack`, `Box`, `WidgetNode`) supporting universal widgets (`HeaderWidget`, `MetricCardWidget`, `EntityListWidget`, `TextNoticeWidget`, `ButtonBarWidget`) and specialized transit/weather widgets (`BusHeroWidget`, `BusBarWidget`, `CitiBikeHeroWidget`, `CitiBikeBarWidget`, `WeatherHeroWidget`, `WeatherForecastWidget`).
- **Open-Meteo Weather Telemetry Engine** (`server/weather.py`): Integrated Open-Meteo public API telemetry for Hoboken, NJ (zero API keys required) providing live temperature, "feels like", conditions, WMO weather interpretation codes, humidity, precipitation probability, and 4-day daily forecasts with TTL caching and resilient offline fallback.
- **Pluggable Data Sources Engine** (`server/data_sources.py`): Unified data abstraction across `SystemDataSource`, `NJTransitDataSource`, `CitiBikeDataSource`, `WeatherDataSource`, `StaticDataSource`, and `HttpJsonDataSource` (enabling arbitrary external REST/JSON endpoints such as Home Assistant, IoT sensors, and webhooks with `${ENV_VAR}` expansion and JSONPath/dot-path extraction).
- **Dashboard REST & Streaming Endpoints** (`server/server.py`):
  - `GET /dashboards`: Lists all registered built-in and user-defined dashboards.
  - `GET /dashboards/<id>`: Returns specification JSON for a dashboard.
  - `GET /dashboards/<id>.png`: Directly renders and streams PNG image for any dashboard with Kindle PW5 rotation, high-DPI scaling, and conditional ETag 304 caching.
  - `GET /dashboards/<id>/data`: Returns live or mock telemetry JSON payload for a dashboard view.
  - `POST /dashboards/<id>`: Authenticated control endpoint (`X-Tracker-Token`) to dynamically create and persist custom dashboard layouts in `config/dashboards/<id>.json`.
- **Pre-Configured Modular Presets** (`config/dashboards/`): Included out-of-the-box specifications for `weather.json` (Hoboken weather hero and multi-day forecast), `bus_focus.json` (Route 126 departures with stop status), and `citibike_focus.json` (Citi Bike neighborhood docks).
- **Multi-View Schedule State Machine Integration** (`server/state_machine.py`, `server/schedule.py`): Extended schedule phases and windows to support `view`, `views` (tuple of allowed view modes for sequential touch cycling), and `interaction_view` (view displayed on power button wake or screen touch). Shipped in `X-Tracker-Policy` via `views=...`.
- **Kindle Touch Multi-View Cycling** (`client-go/main.go`, `client-go/interaction.go`): Kindle client strictly parses `views=` in `X-Tracker-Policy` and cycles sequentially through all assigned views on touch interaction, with seamless 2-way fallback to `morning`/`evening` when unconfigured.

### Changed

- **Web Dashboard View Switcher** (`server/server.py`): Dynamically lists all registered dashboard views in the web UI header instead of hardcoded 3 links, enabling direct preview of weather, transit focus, and custom user views.

---

## [1.38.1] - 2026-10-10

### Documentation

- **Documentation Rectification Sweep**: Performed an end-to-end rectification sweep across `README.md` and all guides in `docs/` (`README.md`, `architecture.md`, `api.md`, `hardware_kindle.md`, `security.md`, `development.md`).
- **New User Onboarding & Progressive Disclosure**: Restructured root `README.md` with an instant <2-minute Quick Start, visual dashboard preview layout, simplified Kindle setup steps, and progressive disclosure moving deep kernel/cryptographic internals into dedicated topic guides.
- **Documentation Hub**: Transformed `docs/README.md` into an onboarding navigation hub organized by user persona (new users, Kindle deployers, operators/sysadmins, security auditors, and developers) with a terminology glossary and troubleshooting FAQ.
- **Architecture & Client Alignment**: Synchronized `docs/architecture.md` with current codebase changes, documenting hidden dotfile `.tracker_client_id.txt` storage, web dashboard schedule editor and persistence fallback (`ConfigStore`), and updated Go client subsystem responsibilities.
- **API Reference & Example Modernization**: Updated `docs/api.md` with current version tags (`1.38.0`/`1.38.1`), documented all control actions for `POST /action` and execution modes for `POST /mode`, and provided concrete `curl` invocation examples with `X-Tracker-Token`.
- **Security & Dual-Format Signing**: Updated `docs/security.md` to document server dual-format response signing (`transit-tracker-resp-v2` and legacy `transit-tracker-resp-v1`) for backward compatibility, accompanied by plain-English explanations of constant-time side-channel defenses.
- **Hardware & Troubleshooting Guidance**: Enhanced `docs/hardware_kindle.md` with a step-by-step installation walkthrough, tactile button table, and a dedicated troubleshooting section for offline discovery and e-ink conditional refresh behaviors.
- **Developer Guide Metrics**: Aligned `docs/development.md` with current test suite counts (414 Python unit tests, 10-tier launcher tests) and verified Mermaid diagram compliance across all documentation files.

---

## [1.38.0] - 2026-10-10

### Added

- **Web Dashboard State Machine Schedule Management (`GET /`)**: Added an interactive Schedule Management section to the desktop webpage dashboard. Displays active phase, target cadence, commute lighting, schedule source, upcoming 24h transitions timeline, and an active window rules table.
- **Quick Phase & Fast-Poll Override**: Introduced dashboard controls to temporarily override the active phase (`peak`, `offpeak`, `overnight`, etc.) or return to scheduled operation (`auto`), alongside a 60s fast-poll toggle, authenticated via `X-Tracker-Token`.
- **In-Browser Schedule JSON Editor**: Integrated an editable, syntax-checked schedule configuration editor with server-side schema validation, save & apply, reload from server, and reset-to-defaults capabilities.
- **Schedule Mutation API (`POST /schedule`)**: Added authenticated control endpoint for setting runtime overrides, clearing overrides, resetting to defaults, and atomically saving new schedule configurations.
- **Resilient Config Persistence with Read-Only Fallback**: `ConfigStore.save_config` atomically persists schedule changes to `SCHEDULE_CONFIG`, with automatic fallback to `CACHE_DIR/schedule.json` when running in read-only container environments. Updated `docker-compose.yml` to mount `./config` read-write.

---

## [1.37.1] - 2026-10-10

### Fixed

- **Response Signing Backward Compatibility (`transit-tracker-resp-v1` & `v2`)**: Added server-side protocol negotiation and dual signature support in `server/identity.py` and `server/server.py`. Older deployed clients (such as `v1.35.x`) that only know `transit-tracker-resp-v1` (12 signed headers) are authenticated with `v1` signatures rather than rejected, allowing them to render dashboards and receive OTA updates seamlessly.
- **Client Dual Format Verification**: Updated `client-go/internal/otasig/otasig.go` to verify against `transit-tracker-resp-v2` first, gracefully falling back to `transit-tracker-resp-v1` for backward compatibility.
- **Kindle Library File Hiding & Migration**: Migrated Kindle client ID storage in `client-go/client_id.go` to `/mnt/us/documents/.tracker_client_id.txt` (hidden dotfile) so the Kindle ebook indexer no longer indexes the UUID as a document book on the Home/Library screen. Automatically migrates and removes legacy unhidden `/mnt/us/documents/tracker_client_id.txt` on startup.

---

## [1.37.0] - 2026-10-10

### Added

- **Client Interaction State Machine** (`client-go/interaction.go`): Formalized client-side interaction modes into an event-driven overlay state machine (`idle -> session -> hold`). Pure transition function with complete test matrix and 100% statement coverage.
- **Unified Response Format `transit-tracker-resp-v2` Client Verification**: Client verifies response signatures under `transit-tracker-resp-v2`, authenticating all response headers including `X-Tracker-Policy` for end-to-end cryptographic integrity.
- **Strict Policy Parsing & Clamping**: `parsePolicy` decodes `X-Tracker-Policy` with fail-safe bounds clamping on session timeout, fast poll hold, manual hold, and frontlight intensity/warmth. Covered by continuous native Go fuzzing (`FuzzParsePolicy`).
- **Phase-Boundary Clamped RTC Wakes**: In sleep mode (`runSleepLoop`), the hardware RTC wakealarm is clamped to `min(interval, until - now)` based on the active policy's phase transition deadline, ensuring the device wakes promptly when a phase transitions (e.g. morning peak) without oversleeping.
- **Policy-Governed Suspend**: Device suspend-to-RAM in sleep mode is explicitly gated by the server's policy (`suspend=0` stays awake on wall clock).

### Changed

- Refactored scattered interaction flags (`interacting`, `lastDataInteraction`, `manualLightTime`, `manualViewTime`) into the centralized interaction overlay.
- Removed hardcoded commute hours fallback in `client-go/schedule.go` in favor of last-known policy state and exponential backoff retry.
- Session auto-lighting and hold suppression directly integrate with overlay state and policy tunables.

---

## [1.36.0] - 2026-10-10

### Added

- **Configurable Schedule State Machine** (`server/state_machine.py`): the peak/off-peak/overnight schedule is now a declarative state machine. Named phases set the poll interval, presentation, status-strip text (with an `{until}` placeholder), frontlight, realtime feeds and suspend permission. Ordered, day-of-week-aware windows select the phase (first match wins; windows that wrap past midnight belong to the day they start on). Windows can also set the `auto` view.
- **`schedule.json` Configuration**: loaded from `$SCHEDULE_CONFIG` (default `/app/config/schedule.json`) and deep-merged onto the built-in defaults, so only changed keys are needed. It is hot-reloaded when its mtime changes. Validation is strict and fail-safe: an invalid file is rejected as a whole and the last good config stays active. Includes `config/schedule.example.json`.
- **`GET /schedule`** (requires `X-Tracker-Token`): config source, any load error, the current phase and its end, the next 24 h of transitions, and the effective config.
- **Response Format `transit-tracker-resp-v2` and `X-Tracker-Policy`**: responses include a cryptographically signed `X-Tracker-Policy` header carrying the phase, next transition timestamp (`until`), suspend permission, and interaction-overlay timeouts. Shared response test vector updated.
- **`FORCE_PHASE`** testing override to pin a phase.
- Control panel shows the current phase and when it ends.

### Changed

- `server/schedule.py` is now a backward-compatible facade over the state machine. Presentation, poll interval, lighting, status note and realtime gating for a request all come from one resolved state. The `sys.modules["server"]` monkeypatch hooks and the module-level `FORCE_FAST_POLL` / `OVERNIGHT_*` constants are removed.
- `docker-compose.yml` passes the legacy schedule env vars through only when they are set. Previously their hardcoded defaults would have overridden `schedule.json`. The compose file also mounts `./config` read-only.
- The legacy env vars (`PEAK_*`, `OVERNIGHT_*`, `OFFPEAK_INTERVAL`, `OVERNIGHT_INTERVAL`) still work and take precedence over the file. A property test checks them against the historical logic.

---

## [1.35.13] - 2026-10-10

### Fixed

- **Hermetic Multi-Device Web Interface Unit Test**: Fixed a time-of-day flake in `tests/test_server_http.py` (`test_fleet_overview_multi_device_rendering`) where devices seen 1 hour ago were classified as online during overnight hours (22:00–06:00 UTC) due to the dynamic 3600s deep-eco poll interval (2.5x cutoff = 9000s). Devices intended to be offline are now set to 24 hours in the past, ensuring test hermeticity across all timezones and times of day.
- **GTFS Index Rebuild Thread Cleanup in Tests**: In `tests/test_gtfs_bus.py` (`test_ensure_index_branches`), explicitly join the background rebuild thread before temporary directory context cleanup to eliminate directory deletion race conditions.

## [1.35.12] - 2026-10-10

### Changed

- **Architecture Overview Diagram Layout**: Redesigned the Mermaid architecture diagram in `README.md` into a vertically aligned 3-tier structure (External Transit Telemetry -> Host Python Server -> Kindle Paperwhite 5). Eliminates side-by-side subgraph crowding, crooked edges, and overlapping labels for a clean, readable presentation.

---

## [1.35.11] - 2026-10-10

### Added

- **Automated Mermaid Diagram Validation**: Added standalone validator `scripts/check_mermaid.py` and unit test suite `tests/test_docs_mermaid.py` ensuring all Markdown documentation diagrams (`README.md`, `docs/`) conform to Mermaid syntax rules (preventing unquoted delimiters in edge labels, unquoted nested delimiters in node labels, unclosed subgraphs, and mismatched blocks).
- **Mermaid Makefile & CI Quality Gates**: Added `make check-mermaid` target, integrated into `make lint`, and added automated validation step in `.github/workflows/ci.yml`.

### Fixed

- **README Architecture Overview Diagram**: Wrapped edge labels containing parentheses and special characters (`(Signed Binary & Manifest)`) in double quotes, fixing GitHub rich render parser error (`got 'PS'`).
- **Cross-Platform Test Font & Stress Resilience**: Updated font fallback paths in `tests/test_render_dashboard.py` and connection retry backlog handling in `tests/test_challenger_m2_harness.py` for macOS compatibility.

---

## [1.35.10] - 2026-10-10

### Added

- **Client Version & Firmware Telemetry**: Go client now attaches `X-Tracker-Client-Version: <Version>` and `X-Tracker-Firmware: <ReadFirmwareVersion>` headers across all polls, logs, diagnostics, and OTA requests.
- **Diagnostics Version Ingestion Fallback**: Server now extracts client and Kindle OS firmware versions from diagnostic uploads (`/diag`) even when request headers are omitted.

### Fixed

- **Fleet Overview Device Isolation**: Excluded web browser image previews (`/dashboard.png` with no Kindle headers or client parameters) from auto-registering in the device registry as `default`, preventing browser traffic from polluting the fleet overview.
- **Kindle OS Firmware Detection**: Added cached firmware version extraction in `client-go` parsing `/etc/prettyversion.txt` and `/etc/version`, stripping build metadata hashes like `(~~otaVersion~~)`.

## [1.35.9] - 2026-10-10

### Added

- **Go Client Native Fuzzing (`testing.F`)**: Implemented zero-dependency native Go fuzz test suites covering Linux evdev input event decoding (`FuzzParseInputEvents`) and cryptographic OTA signature/manifest/cert/semver validation (`FuzzVerifyManifest`, `FuzzVerifyCert`, `FuzzParseSemver`, `FuzzVerifyResponse`). Added `make fuzz` target and CI smoke test stage.
- **Python Property-Based Testing (`hypothesis`)**: Added randomized property-based test harness (`tests/test_properties.py`) validating dashboard rendering layout invariants, schedule/commute lighting bounds, and nonce/header deterministic protocol envelopes.
- **Targeted Mutation Testing (`mutmut`)**: Integrated scoped mutation testing for the server security and identity layer (`server/identity.py`), achieving high test kill rates with zero mutant survival in nonce validation. Added `make mutate-py` target and CI quality gate.

### Fixed

- **Defensive Evdev Buffer Bounds**: Clamped length bounds in `client-go/events.go` to prevent out-of-bounds slice indexing on malformed or truncated input buffers.
- **Resilient View Field Extraction**: Handled missing `walk_min`, `classic`, `ebikes`, and `docks` station keys gracefully in `server/morning_view.py` and `server/evening_view.py`.
- **CRLF Injection Prevention**: Enforced strict CR and LF rejection in `build_response_message` in `server/identity.py` to match Go client verification and spec §3 requirements.

## [1.35.8] - 2026-10-10

### Changed

- **CI Action Upgrades**: Upgraded `actions/setup-go` to `@b7ad1dad31e06c5925ef5d2fc7ad053ef454303e` (v7.0.0) and `hadolint/hadolint-action` to `@06be81baf89a55ffd0e24b8f04a4185738dd3387` (v3.5.0) via grouped Dependabot update.

## [1.35.7] - 2026-10-10

### Changed

- **CI Workflow Modernization**: Upgraded `actions/checkout` to `@3d3c42e5aac5ba805825da76410c181273ba90b1` (v7.0.1) and `actions/setup-python` to `@5fda3b95a4ea91299a34e894583c3862153e4b97` (v7.0.0), resolving Node.js 20 deprecation warnings on GitHub Actions runners while preserving commit SHA cryptographic pinning.
- **Dependabot Batching & Strategy**: Added update groups (`github-actions`, `go-dependencies`, `python-dependencies`) and `versioning-strategy: increase-if-necessary` to `.github/dependabot.yml` to prevent automated PR spam and eliminate conflicting multi-PR dependency races.

## [1.35.6] - 2026-10-10

### Security

- **Launcher Integrity Verification (SEC-01 / ADV-01)**: Mandated SHA-256 digest validation against `tracker-arm.manifest` before binary execution in `TransitTracker.sh`, rejecting unverified or missing manifests.
- **Control Plane Authentication (SEC-02 / H1)**: Enforced `X-Tracker-Token` authorization check on `GET /devices` endpoint, eliminating unauthenticated fleet telemetry exposure.
- **Dependency Cleansing & Lockfile Purge (SEC-03 / H2)**: Removed unused and vulnerable `requirements.lock` from the repository root.
- **Dependency Vulnerability Audits & govulncheck (SEC-04 / H3)**: Updated Python dependencies to patched minimums, integrated `govulncheck` in Go CI pipeline and `Makefile`, and hardened audit gates.
- **Bounded Registry Memory & Log Storage (SEC-05 / M1 / ADV-03)**: Capped device registry capacity to `MAX_REGISTERED_DEVICES` (64) with oldest-offline eviction, and capped per-device log and diagnostic files with automatic tail-rotation.
- **HTTP Smuggling & Connection Desync Protection (SEC-06 / M2)**: Set explicit `Connection: close` and `close_connection = True` on 4xx/403 errors and body truncation conditions in `server.py`.
- **Default Production BUSDV2 Endpoint (SEC-07 / M3)**: Changed `DEFAULT_BASE_URL` from `testpcsdata.njtransit.com` to production `https://pcsdata.njtransit.com` to prevent credential exposure to test environments.
- **Secure File Permissions (SEC-09 / M5)**: Enforced `chmod 600` for `.env` files and updated setup documentation.
- **Strict Content Security Policy & Security Headers (SEC-12 / L5 / ADV-05)**: Added `frame-ancestors 'none'`, `object-src 'none'`, and `base-uri 'none'` to CSP; enforced `X-Frame-Options: DENY` and `X-Content-Type-Options: nosniff`.
- **Cache Thread Safety (SEC-12 / L1)**: Synchronized `_data_cache["time"]` access under `_data_lock` when constructing render cache keys.

### Added

- **Fleet Maintenance Actions (SEC-11 / ADV-04)**: Implemented `restart`, `reboot`, `update`, and `clear_backup` maintenance actions in Kindle Go client `deviceActions`.

### Changed

- **Non-Blocking GTFS Cold-Start (SEC-10 / M6)**: Updated `ensure_index(wait=False)` to asynchronously trigger background rebuilds rather than blocking incoming HTTP threads on cold start.
- **Commute Lighting on HTTP 304 (SEC-12 / L3)**: Refactored `processControlHeaders` in `client-go` to apply frontlight brightness, warmth, and control commands even when visual dashboard content is unchanged (HTTP 304).
- **API & Architectural Documentation Alignment (SEC-08 / M4)**: Reconciled `README.md` and `docs/api.md` with `/devices` JSON schema, authentication requirements, and available device actions.

## [1.35.5] - 2026-10-10

### Added

- **Unified Verification Pipeline**: Added automated verification scripts and gates across Go (93% statement coverage gate) and Python (92% branch coverage gate).
- **Consolidated Documentation**: Organized full technical documentation architecture under `docs/` (`architecture.md`, `security.md`, `api.md`, `hardware_kindle.md`, `development.md`).
- **Comprehensive Quality Tooling**: Enforced `gofmt`, `go vet`, `golangci-lint`, `mypy`, `ruff`, `shellcheck`, and `hadolint` across all codebases.
- **Armv7 Signed Release Verification**: Cryptographic Ed25519 signing validation pipeline for OTA manifests and server identity certificates.

### Changed

- **CI Workflow Modernization**: Upgraded GitHub Actions verification suite to Go 1.26 toolchain and hardened container smoke tests.
- **Docker Non-Root Hardening**: Runtime execution under unprivileged `tracker` system user and strict format compatibility in `docker top` inspections.
- **Gesture and Power Management Cleanup**: Cleaned up gesture detector callbacks, uptime parsers, and powerd suspend helpers for zero linter warnings.
