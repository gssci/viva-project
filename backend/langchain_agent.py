import asyncio
import datetime
import logging
import os
from typing import Any

import geocoder
import requests
import trafilatura
from ddgs import DDGS
from langchain.agents import create_agent
from langchain.tools import tool
from langchain_openai import ChatOpenAI
from agent_tools.applescript_tools import all_mac_tools
from langchain_experimental.utilities import PythonREPL
from langgraph.checkpoint.memory import InMemorySaver  

python_repl = PythonREPL()

logger = logging.getLogger(__name__)

OLLAMA_MODEL = os.getenv("VIVA_OLLAMA_MODEL", "gemma4:26b")
OLLAMA_BASE_URL = os.getenv("VIVA_OLLAMA_BASE_URL", "http://localhost:11434/v1/")
OLLAMA_API_KEY = os.getenv("VIVA_OLLAMA_API_KEY", "ollama")

SYSTEM_PROMPT = (
    "You are Viva, a useful, concise and action-oriented assistant. "
    "Use tools when they are actually needed. "
    "Reply with short, plain-text responses without any formatting. "
    "Your replies must sound natural like spoken language. "
    "Reply in the same language used by the user. "
    "Use the Python tool to perform math computations. "
)


def _format_message_content(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        text_chunks: list[str] = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "text" and item.get("text"):
                    text_chunks.append(str(item["text"]))
            elif hasattr(item, "text") and getattr(item, "text"):
                text_chunks.append(str(item.text))
            elif item:
                text_chunks.append(str(item))
        return "\n".join(chunk.strip() for chunk in text_chunks if chunk).strip()

    return str(content).strip()


def _extract_response_text(response: dict[str, Any]) -> str:
    messages = response.get("messages") or []
    for message in reversed(messages):
        content = getattr(message, "content", message)
        text = _format_message_content(content)
        if text:
            return text
    return ""


def _get_gps_location_blocking() -> str:
    g = geocoder.ip()
    if g.ok:
        return f"Latitude: {g.lat}, Longitude: {g.lng}, City: {g.city}"
    return "Unable to determine GPS location."


def _web_search_blocking(query: str, max_results: int) -> str:
    logger.info(f"Using DDG to search for {query}, max_results={max_results}")
    results = DDGS().text(query, max_results=max_results)
    return str(list(results))


def _extract_webpage_text_blocking(url: str) -> str:
    logger.info(f"Using Trafilatura to fetch {url}")
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

# You can create the tool to pass to an agent
@tool
def python_repl_tool(code: str) -> str:
    """A Python shell.

    Use this to execute python commands.

    Input should be a valid python command.

    If you want to see the output of a value, you should print it out with `print(...)`.
    """
    return python_repl.run(code)

TOOLS = [
    get_current_datetime,
    web_search,
    extract_webpage_text,
    get_weather,
]

TOOLS.extend(all_mac_tools)

class VivaAgentService:
    def __init__(self) -> None:
        self._agent = None
        self._initialization_lock = asyncio.Lock()
        self._invocation_lock = asyncio.Lock()

    async def initialize(self) -> None:
        if self._agent is not None:
            return

        async with self._initialization_lock:
            if self._agent is not None:
                return

            llm = ChatOpenAI(
                model=OLLAMA_MODEL,
                base_url=OLLAMA_BASE_URL,
                api_key=OLLAMA_API_KEY,
            )
            self._agent = create_agent(
                model=llm,
                tools=TOOLS,
                system_prompt=SYSTEM_PROMPT,
                checkpointer=InMemorySaver()
            )
            logger.info("Viva agent initialized with model '%s'.", OLLAMA_MODEL)

    async def run(
        self,
        text: str,
        screenshot_bytes: bytes | None = None,
        screenshot_content_type: str | None = None,
        screenshot_filename: str | None = None,
    ) -> str:
        await self.initialize()

        prompt = text.strip()
        if screenshot_bytes:
            prompt += (
                "\n\n[System note: the frontend attached a screenshot "
                f"('{screenshot_filename or 'upload'}', content type "
                f"{screenshot_content_type or 'application/octet-stream'}). "
                "The backend currently forwards only text to the model, so answer based "
                "on the user's text request.]"
            )

        async with self._invocation_lock:
            response = await self._agent.ainvoke(
                {"messages": [{"role": "user", "content": prompt}]},
                config={"thread_id":0}
            )

        response_text = _extract_response_text(response)
        if not response_text:
            raise RuntimeError("The agent did not return text.")
        return response_text


async def run_viva_agent(
    text: str,
    screenshot_bytes: bytes | None = None,
    screenshot_content_type: str | None = None,
    screenshot_filename: str | None = None,
    service: VivaAgentService | None = None,
) -> str:
    viva_service = service or VivaAgentService()
    return await viva_service.run(
        text=text,
        screenshot_bytes=screenshot_bytes,
        screenshot_content_type=screenshot_content_type,
        screenshot_filename=screenshot_filename,
    )


async def _demo() -> None:
    service = VivaAgentService()
    response = await service.run("What day is it today?")
    print(response)


if __name__ == "__main__":
    asyncio.run(_demo())
