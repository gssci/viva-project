import asyncio
import base64
import logging
import os
from typing import Any

from langchain.agents import create_agent, AgentState
from langchain.messages import HumanMessage
from langchain.messages import RemoveMessage
from langgraph.graph.message import REMOVE_ALL_MESSAGES
from langchain_openai import ChatOpenAI
from agent_tools import all_agent_tools
from langgraph.checkpoint.memory import InMemorySaver
from langchain.agents.middleware import before_model
from langgraph.runtime import Runtime
from langchain_core.runnables import RunnableConfig

logger = logging.getLogger(__name__)

OLLAMA_MODEL = os.getenv("VIVA_OLLAMA_MODEL", "gemma4:26b")
OLLAMA_BASE_URL = os.getenv("VIVA_OLLAMA_BASE_URL", "http://localhost:11434/v1/")
OLLAMA_API_KEY = os.getenv("VIVA_OLLAMA_API_KEY", "ollama")
DEFAULT_IMAGE_MIME_TYPE = "image/jpeg"

SYSTEM_PROMPT = (
    "You are Viva, a useful, concise and action-oriented assistant. "
    "Use tools when they are actually needed. "
    "Reply with short, plain-text responses without any formatting. "
    "Your replies must sound natural like spoken language. "
    "Reply in the same language used by the user. "
    "Use the Python tool to perform math computations. "
)


def _normalize_image_mime_type(content_type: str | None) -> str:
    if not content_type:
        return DEFAULT_IMAGE_MIME_TYPE

    mime_type = content_type.split(";", 1)[0].strip().lower()
    if mime_type.startswith("image/"):
        return mime_type

    logger.warning(
        "Received screenshot with non-image content type '%s'; using '%s'.",
        content_type,
        DEFAULT_IMAGE_MIME_TYPE,
    )
    return DEFAULT_IMAGE_MIME_TYPE


def _build_user_message(
    text: str,
    screenshot_bytes: bytes | None = None,
    screenshot_content_type: str | None = None,
    screenshot_filename: str | None = None,
) -> HumanMessage:
    prompt = text.strip()
    if not screenshot_bytes:
        return HumanMessage(content=prompt)

    image_block: dict[str, Any] = {
        "type": "image",
        "base64": base64.b64encode(screenshot_bytes).decode("ascii"),
        "mime_type": _normalize_image_mime_type(screenshot_content_type),
    }
    if screenshot_filename:
        image_block["extras"] = {"filename": screenshot_filename}

    return HumanMessage(
        content_blocks=[
            {"type": "text", "text": prompt},
            image_block,
        ]
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


@before_model
def trim_messages(state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
    """Keep only the last few messages to fit context window."""
    messages = state["messages"]

    if len(messages) <= 3:
        return None  # No changes needed

    first_msg = messages[0]
    recent_messages = messages[-3:] if len(messages) % 2 == 0 else messages[-4:]
    new_messages = [first_msg] + recent_messages

    return {"messages": [RemoveMessage(id=REMOVE_ALL_MESSAGES), *new_messages]}


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
                tools=all_agent_tools,
                system_prompt=SYSTEM_PROMPT,
                middleware=[trim_messages],
                checkpointer=InMemorySaver(),
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

        user_message = _build_user_message(
            text=text,
            screenshot_bytes=screenshot_bytes,
            screenshot_content_type=screenshot_content_type,
            screenshot_filename=screenshot_filename,
        )

        config: RunnableConfig = {"configurable": {"thread_id": "1"}}

        async with self._invocation_lock:
            response = await self._agent.ainvoke(
                {"messages": [user_message]},
                config=config,
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
