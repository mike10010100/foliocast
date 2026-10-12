"""
Weather Telemetry Provider for Hoboken, NJ.
Fetches real-time weather and forecast data from Open-Meteo's public API
(zero API key required) with caching, rate limiting, and fallback mock data.
"""

import json
import logging
import threading
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger("weather")

# Default coordinates: Hoboken City Hall, Hoboken, NJ
DEFAULT_LATITUDE = 40.7371
DEFAULT_LONGITUDE = -74.0305
DEFAULT_CACHE_TTL = 900  # 15 minutes

# WMO Weather interpretation codes (WW)
# https://open-meteo.com/en/docs
WMO_CODE_MAP: dict[int, tuple[str, str]] = {
    0: ("Clear sky", "SUN"),
    1: ("Mainly clear", "MOSTLY_SUN"),
    2: ("Partly cloudy", "PARTLY_CLOUD"),
    3: ("Overcast", "CLOUDY"),
    45: ("Fog", "FOG"),
    48: ("Depositing rime fog", "FOG"),
    51: ("Light drizzle", "DRIZZLE"),
    53: ("Moderate drizzle", "DRIZZLE"),
    55: ("Dense drizzle", "RAIN"),
    56: ("Light freezing drizzle", "FREEZE_RAIN"),
    57: ("Dense freezing drizzle", "FREEZE_RAIN"),
    61: ("Slight rain", "LIGHT_RAIN"),
    63: ("Moderate rain", "RAIN"),
    65: ("Heavy rain", "HEAVY_RAIN"),
    66: ("Light freezing rain", "FREEZE_RAIN"),
    67: ("Heavy freezing rain", "FREEZE_RAIN"),
    71: ("Slight snow fall", "LIGHT_SNOW"),
    73: ("Moderate snow fall", "SNOW"),
    75: ("Heavy snow fall", "HEAVY_SNOW"),
    77: ("Snow grains", "SNOW"),
    80: ("Slight rain showers", "SHOWERS"),
    81: ("Moderate rain showers", "SHOWERS"),
    82: ("Violent rain showers", "HEAVY_RAIN"),
    85: ("Slight snow showers", "SNOW"),
    86: ("Heavy snow showers", "HEAVY_SNOW"),
    95: ("Thunderstorm", "THUNDER"),
    96: ("Thunderstorm with hail", "THUNDER"),
    99: ("Thunderstorm with heavy hail", "THUNDER"),
}


def interpret_wmo_code(code: int) -> tuple[str, str]:
    """Returns (description, condition_glyph_name) for a WMO weather code."""
    return WMO_CODE_MAP.get(code, ("Unknown", "CLOUD"))


@dataclass(frozen=True)
class DailyForecast:
    date_str: str  # YYYY-MM-DD
    day_name: str  # Mon, Tue, etc.
    temp_max: int  # °F
    temp_min: int  # °F
    condition: str
    condition_glyph: str
    precip_probability: int  # %


@dataclass(frozen=True)
class WeatherSnapshot:
    temp: int  # current °F
    apparent_temp: int  # "feels like" °F
    condition: str  # e.g. "Partly cloudy"
    condition_glyph: str  # e.g. "PARTLY_CLOUD"
    temp_max: int  # today's high °F
    temp_min: int  # today's low °F
    humidity: int  # %
    wind_speed: int  # mph
    precip_prob: int  # today's precipitation probability %
    forecast: tuple[DailyForecast, ...] = field(default_factory=tuple)
    status: str = "ok"  # "ok", "stale", "error"
    as_of: float = 0.0
    location_name: str = "Hoboken, NJ"

    def to_dict(self) -> dict[str, Any]:
        return {
            "temp": self.temp,
            "apparent_temp": self.apparent_temp,
            "condition": self.condition,
            "condition_glyph": self.condition_glyph,
            "temp_max": self.temp_max,
            "temp_min": self.temp_min,
            "humidity": self.humidity,
            "wind_speed": self.wind_speed,
            "precip_prob": self.precip_prob,
            "status": self.status,
            "as_of": self.as_of,
            "location_name": self.location_name,
            "forecast": [
                {
                    "date": f.date_str,
                    "day": f.day_name,
                    "temp_max": f.temp_max,
                    "temp_min": f.temp_min,
                    "condition": f.condition,
                    "condition_glyph": f.condition_glyph,
                    "precip_prob": f.precip_probability,
                }
                for f in self.forecast
            ],
        }


def get_mock_weather_data(
    location_name: Optional[str] = None,
) -> WeatherSnapshot:
    """Generates realistic weather data for preview and testing."""
    if location_name is None:
        try:
            from location import get_location_config

            cfg = get_location_config()
            location_name = (
                getattr(cfg, "location_name", "Hoboken, NJ") if cfg else "Hoboken, NJ"
            )
        except Exception:
            location_name = "Hoboken, NJ"

    now = datetime.now()
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    today_w = now.weekday()

    forecasts = [
        DailyForecast(
            date_str="2026-10-11",
            day_name="Today",
            temp_max=68,
            temp_min=52,
            condition="Partly cloudy",
            condition_glyph="PARTLY_CLOUD",
            precip_probability=15,
        ),
        DailyForecast(
            date_str="2026-10-12",
            day_name=day_names[(today_w + 1) % 7],
            temp_max=64,
            temp_min=48,
            condition="Clear sky",
            condition_glyph="SUN",
            precip_probability=5,
        ),
        DailyForecast(
            date_str="2026-10-13",
            day_name=day_names[(today_w + 2) % 7],
            temp_max=61,
            temp_min=50,
            condition="Slight rain",
            condition_glyph="LIGHT_RAIN",
            precip_probability=65,
        ),
        DailyForecast(
            date_str="2026-10-14",
            day_name=day_names[(today_w + 3) % 7],
            temp_max=59,
            temp_min=46,
            condition="Mainly clear",
            condition_glyph="MOSTLY_SUN",
            precip_probability=10,
        ),
    ]

    return WeatherSnapshot(
        temp=63,
        apparent_temp=62,
        condition="Partly cloudy",
        condition_glyph="PARTLY_CLOUD",
        temp_max=68,
        temp_min=52,
        humidity=58,
        wind_speed=8,
        precip_prob=15,
        forecast=tuple(forecasts),
        status="ok",
        as_of=time.time(),
        location_name=str(location_name or "Hoboken, NJ"),
    )


class WeatherTracker:
    """
    Fetches and caches weather telemetry from Open-Meteo.
    Thread-safe with TTL caching, dynamic coordinate updates, and graceful degradation.
    """

    def __init__(
        self,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        location_name: Optional[str] = None,
        cache_ttl: int = DEFAULT_CACHE_TTL,
        timeout: float = 5.0,
        location_store: Optional[Any] = None,
    ) -> None:
        self.cache_ttl = cache_ttl
        self.timeout = timeout
        self._lock = threading.Lock()
        self._cache: Optional[WeatherSnapshot] = None
        self._cache_time: float = 0.0
        self._location_store = location_store
        self._explicit_coords = latitude is not None and longitude is not None

        if self._explicit_coords:
            self.latitude = float(latitude)  # type: ignore[arg-type]
            self.longitude = float(longitude)  # type: ignore[arg-type]
            self.location_name = str(location_name or "Custom Location")
        else:
            cfg = self._get_active_location_config()
            self.latitude = float(cfg.latitude) if cfg else DEFAULT_LATITUDE
            self.longitude = float(cfg.longitude) if cfg else DEFAULT_LONGITUDE
            self.location_name = str(
                getattr(cfg, "location_name", getattr(cfg, "name", "Hoboken, NJ"))
                if cfg
                else "Hoboken, NJ"
            )

    def _get_active_location_config(self) -> Any:
        if self._location_store is not None:
            return self._location_store.get()
        try:
            from location import get_location_config

            return get_location_config()
        except ImportError:
            return None

    def set_location(
        self,
        lat: float,
        lon: float,
        location_name: Optional[str] = None,
    ) -> None:
        """Thread-safe update of weather coordinates; invalidates cache if changed."""
        with self._lock:
            coord_changed = (
                abs(self.latitude - float(lat)) > 1e-4
                or abs(self.longitude - float(lon)) > 1e-4
            )
            name_changed = (
                location_name is not None and self.location_name != location_name
            )
            self.latitude = float(lat)
            self.longitude = float(lon)
            if location_name is not None:
                self.location_name = str(location_name)
            if coord_changed or name_changed:
                self._cache = None
                self._cache_time = 0.0
                logger.info(
                    "WeatherTracker coordinates updated to (%.4f, %.4f, %s); cache invalidated",
                    self.latitude,
                    self.longitude,
                    self.location_name,
                )

    def update_location(
        self,
        latitude: float,
        longitude: float,
        location_name: Optional[str] = None,
    ) -> None:
        """Alias for set_location for contract compatibility."""
        self.set_location(lat=latitude, lon=longitude, location_name=location_name)

    def update_from_config(self, cfg: Any) -> None:
        """Thread-safe update using a LocationConfig instance."""
        if cfg is not None:
            self.set_location(
                lat=cfg.latitude,
                lon=cfg.longitude,
                location_name=getattr(cfg, "location_name", getattr(cfg, "name", None)),
            )

    def invalidate_cache(self) -> None:
        """Thread-safe cache invalidation forcing next get_weather() to fetch fresh."""
        with self._lock:
            self._cache = None
            self._cache_time = 0.0

    def get_weather(self, force_refresh: bool = False) -> WeatherSnapshot:
        """Fetches latest weather snapshot, dynamically refreshing coordinates if needed."""
        now = time.time()
        with self._lock:
            # Sync with LocationConfigStore if coordinates are dynamic
            if not self._explicit_coords:
                cfg = self._get_active_location_config()
                if cfg is not None:
                    cfg_lat = float(cfg.latitude)
                    cfg_lon = float(cfg.longitude)
                    cfg_name = str(
                        getattr(
                            cfg,
                            "location_name",
                            getattr(cfg, "name", self.location_name),
                        )
                    )
                    if (
                        abs(self.latitude - cfg_lat) > 1e-4
                        or abs(self.longitude - cfg_lon) > 1e-4
                        or self.location_name != cfg_name
                    ):
                        self.latitude = cfg_lat
                        self.longitude = cfg_lon
                        self.location_name = cfg_name
                        self._cache = None
                        self._cache_time = 0.0

            if (
                not force_refresh
                and self._cache is not None
                and (now - self._cache_time) < self.cache_ttl
            ):
                return self._cache

        # Fetch outside lock to prevent blocking concurrent readers during network I/O
        try:
            snapshot = self._fetch_live()
            with self._lock:
                self._cache = snapshot
                self._cache_time = now
            return snapshot
        except Exception as e:
            logger.warning("Weather fetch failed (%s); using cached/fallback data", e)
            with self._lock:
                if self._cache is not None:
                    # Return cached data marked stale
                    return WeatherSnapshot(
                        temp=self._cache.temp,
                        apparent_temp=self._cache.apparent_temp,
                        condition=self._cache.condition,
                        condition_glyph=self._cache.condition_glyph,
                        temp_max=self._cache.temp_max,
                        temp_min=self._cache.temp_min,
                        humidity=self._cache.humidity,
                        wind_speed=self._cache.wind_speed,
                        precip_prob=self._cache.precip_prob,
                        forecast=self._cache.forecast,
                        status="stale",
                        as_of=self._cache.as_of,
                        location_name=self.location_name,
                    )
            # No cache at all: return mock fallback marked error
            mock = get_mock_weather_data(location_name=self.location_name)
            return WeatherSnapshot(
                temp=mock.temp,
                apparent_temp=mock.apparent_temp,
                condition=mock.condition,
                condition_glyph=mock.condition_glyph,
                temp_max=mock.temp_max,
                temp_min=mock.temp_min,
                humidity=mock.humidity,
                wind_speed=mock.wind_speed,
                precip_prob=mock.precip_prob,
                forecast=mock.forecast,
                status="error",
                as_of=now,
                location_name=self.location_name,
            )

    def _fetch_live(self) -> WeatherSnapshot:
        params = {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "current": "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
            "temperature_unit": "fahrenheit",
            "wind_speed_unit": "mph",
            "precipitation_unit": "inch",
            "timezone": "auto",
        }
        url = f"https://api.open-meteo.com/v1/forecast?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "TransitTracker/1.0",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        current = data.get("current", {})
        daily = data.get("daily", {})

        weather_code = int(current.get("weather_code", 0))
        cond_text, cond_glyph = interpret_wmo_code(weather_code)

        cur_temp = int(round(float(current.get("temperature_2m", 60))))
        app_temp = int(round(float(current.get("apparent_temperature", cur_temp))))
        humidity = int(round(float(current.get("relative_humidity_2m", 50))))
        wind_speed = int(round(float(current.get("wind_speed_10m", 0))))

        times = daily.get("time", [])
        max_temps = daily.get("temperature_2m_max", [])
        min_temps = daily.get("temperature_2m_min", [])
        codes = daily.get("weather_code", [])
        precips = daily.get("precipitation_probability_max", [])

        today_max = int(round(max_temps[0])) if max_temps else cur_temp
        today_min = int(round(min_temps[0])) if min_temps else cur_temp
        today_precip = int(round(precips[0])) if precips else 0

        day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        forecast_list: list[DailyForecast] = []
        for i in range(min(5, len(times))):
            d_str = times[i]
            try:
                dt = datetime.strptime(d_str, "%Y-%m-%d")
                d_name = "Today" if i == 0 else day_names[dt.weekday()]
            except Exception:
                d_name = d_str

            d_code = int(codes[i]) if i < len(codes) else 0
            d_cond, d_glyph = interpret_wmo_code(d_code)
            d_max = int(round(max_temps[i])) if i < len(max_temps) else 0
            d_min = int(round(min_temps[i])) if i < len(min_temps) else 0
            d_precip = int(round(precips[i])) if i < len(precips) else 0

            forecast_list.append(
                DailyForecast(
                    date_str=d_str,
                    day_name=d_name,
                    temp_max=d_max,
                    temp_min=d_min,
                    condition=d_cond,
                    condition_glyph=d_glyph,
                    precip_probability=d_precip,
                )
            )

        return WeatherSnapshot(
            temp=cur_temp,
            apparent_temp=app_temp,
            condition=cond_text,
            condition_glyph=cond_glyph,
            temp_max=today_max,
            temp_min=today_min,
            humidity=humidity,
            wind_speed=wind_speed,
            precip_prob=today_precip,
            forecast=tuple(forecast_list),
            status="ok",
            as_of=time.time(),
            location_name=self.location_name,
        )


# Alias for architectural contract compliance (Requirement R4)
WeatherProvider = WeatherTracker

# Module singleton
WEATHER_TRACKER = WeatherTracker()
