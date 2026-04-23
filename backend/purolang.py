import asyncio
import datetime
import logging
import os
from typing import Any

import geocoder
import requests
import trafilatura
from duckduckgo_search import DDGS
from langchain.agents import create_agent
from langchain.tools import tool
from langchain_openai import ChatOpenAI
from common_task_tools import all_mac_tools

logger = logging.getLogger(__name__)

OLLAMA_MODEL = os.getenv("VIVA_OLLAMA_MODEL", "gemma4:26b")
OLLAMA_BASE_URL = os.getenv("VIVA_OLLAMA_BASE_URL", "http://localhost:11434/v1/")
OLLAMA_API_KEY = os.getenv("VIVA_OLLAMA_API_KEY", "ollama")

SYSTEM_PROMPT = (
    "Sei Viva, un assistente utile, conciso e orientato all'azione. "
    "Usa i tool quando servono davvero. "
    "Se ti viene chiesto il meteo e non hai gia le coordinate, ottienile prima tramite GPS."
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
    g = geocoder.ip("me")
    if g.ok:
        return f"Latitudine: {g.lat}, Longitudine: {g.lng}, Citta: {g.city}"
    return "Impossibile determinare la posizione GPS."


def _web_search_blocking(query: str, max_results: int) -> str:
    results = DDGS().text(query, max_results=max_results)
    return str(list(results))


def _extract_webpage_text_blocking(url: str) -> str:
    downloaded = trafilatura.fetch_url(url)
    if downloaded:
        text = trafilatura.extract(downloaded)
        return text[:6000] if text else "Nessun testo estratto."
    return "Impossibile scaricare la pagina."


def _get_weather_blocking(lat: float, lon: float) -> str:
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}&current_weather=true"
    )
    response = requests.get(url, timeout=15)
    response.raise_for_status()
    return str(response.json().get("current_weather", "Dati meteo non disponibili."))


@tool
async def get_current_datetime() -> str:
    """Restituisce la data e l'ora attuali di sistema."""
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@tool
async def get_gps_location() -> str:
    """Ottiene la posizione GPS approssimativa basata sull'indirizzo IP locale."""
    try:
        return await asyncio.to_thread(_get_gps_location_blocking)
    except Exception as exc:
        return f"Errore nel recupero della posizione GPS: {exc}"


@tool
async def web_search(query: str, max_results: int = 5) -> str:
    """Effettua una ricerca sul web e restituisce i risultati principali."""
    try:
        return await asyncio.to_thread(_web_search_blocking, query, max_results)
    except Exception as exc:
        return f"Errore durante la ricerca web: {exc}"


@tool
async def extract_webpage_text(url: str) -> str:
    """Estrae il testo pulito da una pagina web in modalita lettura, ignorando ads e menu."""
    try:
        return await asyncio.to_thread(_extract_webpage_text_blocking, url)
    except Exception as exc:
        return f"Errore nell'estrazione: {exc}"


@tool
async def get_weather(lat: float, lon: float) -> str:
    """Ottiene il meteo attuale per le coordinate specificate."""
    try:
        return await asyncio.to_thread(_get_weather_blocking, lat, lon)
    except Exception as exc:
        return f"Errore nel recupero del meteo: {exc}"


TOOLS = [
    get_current_datetime,
    get_gps_location,
    web_search,
    extract_webpage_text,
    get_weather,
]

TOOLS.extend(all_mac_tools)

class PuroLangService:
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
            )
            logger.info("PuroLang agent initialized with model '%s'.", OLLAMA_MODEL)

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
                "\n\n[Nota di sistema: il frontend ha allegato uno screenshot "
                f"('{screenshot_filename or 'upload'}', tipo "
                f"{screenshot_content_type or 'application/octet-stream'}). "
                "Il backend inoltra al modello solo il testo, quindi rispondi basandoti "
                "sulla richiesta testuale dell'utente.]"
            )

        async with self._invocation_lock:
            response = await self._agent.ainvoke(
                {"messages": [{"role": "user", "content": prompt}]}
            )

        response_text = _extract_response_text(response)
        if not response_text:
            raise RuntimeError("L'agente non ha restituito testo.")
        return response_text


async def run_viva_agent(
    text: str,
    screenshot_bytes: bytes | None = None,
    screenshot_content_type: str | None = None,
    screenshot_filename: str | None = None,
    service: PuroLangService | None = None,
) -> str:
    viva_service = service or PuroLangService()
    return await viva_service.run(
        text=text,
        screenshot_bytes=screenshot_bytes,
        screenshot_content_type=screenshot_content_type,
        screenshot_filename=screenshot_filename,
    )


async def _demo() -> None:
    service = PuroLangService()
    response = await service.run("Che giorno e oggi?")
    print(response)


if __name__ == "__main__":
    asyncio.run(_demo())
