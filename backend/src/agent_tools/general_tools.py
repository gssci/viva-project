import asyncio
import datetime
import logging
from typing import Any

import requests
import trafilatura
from langchain_community.tools import DuckDuckGoSearchRun
from langchain_community.utilities import DuckDuckGoSearchAPIWrapper
from langchain_core.tools import tool
from langchain_experimental.utilities import PythonREPL

logger = logging.getLogger(__name__)
python_repl = PythonREPL()

OPEN_METEO_GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

CURRENT_WEATHER_VARS = (
    "temperature_2m",
    "relative_humidity_2m",
    "apparent_temperature",
    "is_day",
    "precipitation",
    "rain",
    "showers",
    "snowfall",
    "weather_code",
    "cloud_cover",
    "pressure_msl",
    "surface_pressure",
    "wind_speed_10m",
    "wind_direction_10m",
    "wind_gusts_10m",
)

WEATHER_CODE_DESCRIPTIONS = {
    0: "clear sky",
    1: "mainly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "fog",
    48: "depositing rime fog",
    51: "light drizzle",
    53: "moderate drizzle",
    55: "dense drizzle",
    56: "light freezing drizzle",
    57: "dense freezing drizzle",
    61: "slight rain",
    63: "moderate rain",
    65: "heavy rain",
    66: "light freezing rain",
    67: "heavy freezing rain",
    71: "slight snow fall",
    73: "moderate snow fall",
    75: "heavy snow fall",
    77: "snow grains",
    80: "slight rain showers",
    81: "moderate rain showers",
    82: "violent rain showers",
    85: "slight snow showers",
    86: "heavy snow showers",
    95: "thunderstorm",
    96: "thunderstorm with slight hail",
    99: "thunderstorm with heavy hail",
}


def _request_json(url: str, params: dict[str, Any]) -> dict[str, Any]:
    response = requests.get(
        url,
        params=params,
        timeout=15,
        headers={"User-Agent": "Viva/0.1 (+https://open-meteo.com)"},
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("error"):
        raise ValueError(payload.get("reason", "Open-Meteo returned an error."))
    return payload


def _web_search_blocking(query: str, max_results: int) -> str:
    normalized_max_results = max(1, min(int(max_results), 10))
    logger.info(
        "Using LangChain DuckDuckGoSearchRun for %s, max_results=%s",
        query,
        normalized_max_results,
    )
    search = DuckDuckGoSearchRun(
        api_wrapper=DuckDuckGoSearchAPIWrapper(
            backend="duckduckgo",
            max_results=normalized_max_results,
            time=None,
        )
    )
    return search.invoke(query)


def _extract_webpage_text_blocking(url: str) -> str:
    logger.info("Using Trafilatura to fetch %s", url)
    downloaded = trafilatura.fetch_url(url)
    if downloaded:
        text = trafilatura.extract(downloaded)
        return text[:6000] if text else "No text extracted."
    return "Unable to download the page."


def _geocode_location_blocking(location: str) -> dict[str, Any]:
    logger.info("Geocoding weather location with Open-Meteo: %s", location)
    payload = _request_json(
        OPEN_METEO_GEOCODING_URL,
        {
            "name": location.strip(),
            "count": 1,
            "language": "en",
            "format": "json",
        },
    )
    results = payload.get("results") or []
    if not results:
        raise ValueError(f"No weather location found for {location!r}.")
    return results[0]


def _format_location_name(location: dict[str, Any]) -> str:
    parts = [
        location.get("name"),
        location.get("admin1"),
        location.get("country"),
    ]
    label_parts = []
    for part in parts:
        if part and part not in label_parts:
            label_parts.append(part)
    return ", ".join(label_parts)


def _format_value(
    current: dict[str, Any],
    units: dict[str, str],
    key: str,
    missing: str = "not available",
) -> str:
    value = current.get(key)
    if value is None:
        return missing
    unit = units.get(key, "")
    return f"{value} {unit}".strip()


def _wind_direction_to_compass(degrees: float | int | None) -> str:
    if degrees is None:
        return "unknown direction"
    directions = (
        "N",
        "NNE",
        "NE",
        "ENE",
        "E",
        "ESE",
        "SE",
        "SSE",
        "S",
        "SSW",
        "SW",
        "WSW",
        "W",
        "WNW",
        "NW",
        "NNW",
    )
    index = round(float(degrees) / 22.5) % len(directions)
    return directions[index]


def _resolve_weather_location(
    location: str,
    lat: float | None,
    lon: float | None,
) -> tuple[float, float, str, str]:
    cleaned_location = location.strip()
    if cleaned_location:
        geocoded_location = _geocode_location_blocking(cleaned_location)
        return (
            float(geocoded_location["latitude"]),
            float(geocoded_location["longitude"]),
            geocoded_location.get("timezone") or "auto",
            _format_location_name(geocoded_location),
        )

    if lat is None or lon is None:
        raise ValueError("Provide a location name or both lat and lon coordinates.")

    return float(lat), float(lon), "auto", f"{float(lat):.4f}, {float(lon):.4f}"


def _get_weather_blocking(
    location: str = "",
    lat: float | None = None,
    lon: float | None = None,
) -> str:
    latitude, longitude, timezone, location_label = _resolve_weather_location(
        location,
        lat,
        lon,
    )
    logger.info(
        "Fetching Open-Meteo weather for %s (%s, %s)",
        location_label,
        latitude,
        longitude,
    )
    payload = _request_json(
        OPEN_METEO_FORECAST_URL,
        {
            "latitude": latitude,
            "longitude": longitude,
            "current": ",".join(CURRENT_WEATHER_VARS),
            "timezone": timezone,
            "forecast_days": 1,
        },
    )
    current = payload.get("current") or {}
    units = payload.get("current_units") or {}
    if not current:
        return "Weather data is not available."

    weather_code = current.get("weather_code")
    conditions = WEATHER_CODE_DESCRIPTIONS.get(weather_code, "unknown conditions")
    daylight = (
        "daytime"
        if current.get("is_day") == 1
        else "nighttime"
        if current.get("is_day") == 0
        else "unknown daylight"
    )
    wind_direction = current.get("wind_direction_10m")
    compass_direction = _wind_direction_to_compass(wind_direction)

    return "\n".join(
        [
            f"Current weather for {location_label}",
            f"Coordinates: {latitude:.4f}, {longitude:.4f}",
            f"Observed at: {current.get('time', 'unknown local time')}",
            f"Conditions: {conditions} ({daylight})",
            "Temperature: "
            f"{_format_value(current, units, 'temperature_2m')} "
            f"(feels like {_format_value(current, units, 'apparent_temperature')})",
            f"Humidity: {_format_value(current, units, 'relative_humidity_2m')}",
            f"Cloud cover: {_format_value(current, units, 'cloud_cover')}",
            f"Precipitation: {_format_value(current, units, 'precipitation')}",
            f"Rain: {_format_value(current, units, 'rain')}",
            f"Showers: {_format_value(current, units, 'showers')}",
            f"Snowfall: {_format_value(current, units, 'snowfall')}",
            "Wind: "
            f"{_format_value(current, units, 'wind_speed_10m')} "
            f"from {compass_direction} ({wind_direction} "
            f"{units.get('wind_direction_10m', 'degrees')})",
            f"Wind gusts: {_format_value(current, units, 'wind_gusts_10m')}",
            f"Mean sea-level pressure: {_format_value(current, units, 'pressure_msl')}",
            f"Surface pressure: {_format_value(current, units, 'surface_pressure')}",
            "Source: Open-Meteo Forecast API and Geocoding API.",
        ]
    )


@tool
async def get_current_datetime() -> str:
    """Returns the current system date and time."""
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@tool
async def web_search(query: str, max_results: int = 5) -> str:
    """Runs a web search and returns the top results."""
    try:
        return await asyncio.to_thread(_web_search_blocking, query, max_results)
    except Exception as exc:
        return f"Web search failed: {exc}"


@tool
async def extract_webpage_text(url: str) -> str:
    """Extracts clean reader-mode text from a web page, ignoring ads and menus.
    Use this tool when you want to read the content of a search result."""
    try:
        return await asyncio.to_thread(_extract_webpage_text_blocking, url)
    except Exception as exc:
        return f"Text extraction failed: {exc}"


@tool
async def get_weather(
    location: str = "",
    lat: float | None = None,
    lon: float | None = None,
) -> str:
    """Gets current weather for a city/place name or for latitude/longitude coordinates."""
    try:
        return await asyncio.to_thread(_get_weather_blocking, location, lat, lon)
    except Exception as exc:
        return f"Weather retrieval failed: {exc}"


@tool
def python_repl_tool(code: str) -> str:
    """A Python shell.

    Use this to execute python commands.

    Input should be a valid python command.

    If you want to see the output of a value, you should print it out with `print(...)`.
    """
    return python_repl.run(code)


general_tools = [
    get_current_datetime,
    web_search,
    extract_webpage_text,
    get_weather,
    python_repl_tool,
]


__all__ = [
    "extract_webpage_text",
    "general_tools",
    "get_current_datetime",
    "get_weather",
    "python_repl_tool",
    "web_search",
]
