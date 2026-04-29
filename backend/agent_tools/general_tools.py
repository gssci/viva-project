import asyncio
import datetime
import logging

import requests
import trafilatura
from ddgs import DDGS
from langchain_core.tools import tool
from langchain_experimental.utilities import PythonREPL


logger = logging.getLogger(__name__)
python_repl = PythonREPL()


def _web_search_blocking(query: str, max_results: int) -> str:
    logger.info("Using DDG to search for %s, max_results=%s", query, max_results)
    results = DDGS().text(query, max_results=max_results)
    return str(list(results))


def _extract_webpage_text_blocking(url: str) -> str:
    logger.info("Using Trafilatura to fetch %s", url)
    downloaded = trafilatura.fetch_url(url)
    if downloaded:
        text = trafilatura.extract(downloaded)
        return text[:6000] if text else "No text extracted."
    return "Unable to download the page."


def _get_weather_blocking(lat: float, lon: float) -> str:
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}&current_weather=true"
    )
    response = requests.get(url, timeout=15)
    response.raise_for_status()
    return str(response.json().get("current_weather", "Weather data is not available."))


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
    """Extracts clean reader-mode text from a web page, ignoring ads and menus."""
    try:
        return await asyncio.to_thread(_extract_webpage_text_blocking, url)
    except Exception as exc:
        return f"Text extraction failed: {exc}"


@tool
async def get_weather(lat: float, lon: float) -> str:
    """Gets the current weather for the specified coordinates."""
    try:
        return await asyncio.to_thread(_get_weather_blocking, lat, lon)
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
