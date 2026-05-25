import asyncio
import base64
import logging
import os
from typing import Any

from langchain.agents import create_agent, AgentState
from langchain.messages import AIMessage, HumanMessage
from langchain.messages import RemoveMessage, SystemMessage
from langgraph.graph.message import REMOVE_ALL_MESSAGES
from langchain_openai import ChatOpenAI
from agent_tools import all_agent_tools
from langgraph.checkpoint.memory import InMemorySaver
from langchain.agents.middleware import before_model
from langgraph.runtime import Runtime
from langchain_core.messages import BaseMessage
from langchain_core.runnables import RunnableConfig

logger = logging.getLogger(__name__)

LLM_MODEL = os.getenv(
    "VIVA_LLM_MODEL", os.getenv("VIVA_OMLX_MODEL", "gemma-4-E4B-it-Q4_K_M.gguf")
)
LLM_BASE_URL = os.getenv(
    "VIVA_LLM_BASE_URL", os.getenv("VIVA_OMLX_BASE_URL", "http://127.0.0.1:8000/v1")
)
LLM_API_KEY = os.getenv(
    "VIVA_LLM_API_KEY", os.getenv("VIVA_OMLX_API_KEY", "not-needed")
)
DEFAULT_IMAGE_MIME_TYPE = "image/jpeg"
DEFAULT_AUDIO_MIME_TYPE = "audio/wav"
MAX_HISTORY_MESSAGES = 3

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


def _normalize_audio_mime_type(content_type: str | None) -> str:
    if not content_type:
        return DEFAULT_AUDIO_MIME_TYPE

    mime_type = content_type.split(";", 1)[0].strip().lower()
    if mime_type.startswith("audio/"):
        return mime_type

    logger.warning(
        "Received native audio with non-audio content type '%s'; using '%s'.",
        content_type,
        DEFAULT_AUDIO_MIME_TYPE,
    )
    return DEFAULT_AUDIO_MIME_TYPE


def _build_user_message(
    text: str,
    screenshot_bytes: bytes | None = None,
    screenshot_content_type: str | None = None,
    screenshot_filename: str | None = None,
    audio_bytes: bytes | None = None,
    audio_content_type: str | None = None,
    audio_filename: str | None = None,
) -> HumanMessage:
    prompt = text.strip()
    if not screenshot_bytes and not audio_bytes:
        return HumanMessage(content=prompt)

    content_blocks: list[dict[str, Any]] = [{"type": "text", "text": prompt}]

    if audio_bytes:
        audio_block: dict[str, Any] = {
            "type": "audio",
            "base64": base64.b64encode(audio_bytes).decode("ascii"),
            "mime_type": _normalize_audio_mime_type(audio_content_type),
        }
        if audio_filename:
            audio_block["extras"] = {"filename": audio_filename}
        content_blocks.append(audio_block)

    if screenshot_bytes:
        image_mime_type = _normalize_image_mime_type(screenshot_content_type)
        image_base64 = base64.b64encode(screenshot_bytes).decode("ascii")
        content_blocks.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{image_mime_type};base64,{image_base64}",
                },
            }
        )

    return HumanMessage(content=content_blocks)


def _text_from_content_block(block: Any) -> str:
    if isinstance(block, str):
        return block.strip()

    if isinstance(block, dict):
        if block.get("type") in {"text", "text-plain"} and block.get("text"):
            return str(block["text"]).strip()
        return ""

    block_type = getattr(block, "type", None)
    text = getattr(block, "text", None)
    if block_type in {"text", "text-plain"} and text:
        return str(text).strip()

    return ""


def _format_message_content(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()

    if isinstance(content, dict):
        return _text_from_content_block(content)

    if isinstance(content, list):
        text_chunks: list[str] = []
        for item in content:
            text = _text_from_content_block(item)
            if text:
                text_chunks.append(text)
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


def _latest_human_message_index(messages: list[BaseMessage]) -> int | None:
    for index in range(len(messages) - 1, -1, -1):
        if isinstance(messages[index], HumanMessage):
            return index
    return None


def _clean_history_message(message: BaseMessage) -> BaseMessage | None:
    text = _format_message_content(message.content)
    if not text:
        return None

    if isinstance(message, SystemMessage):
        return SystemMessage(content=text)

    if isinstance(message, HumanMessage):
        return HumanMessage(content=text)

    if isinstance(message, AIMessage) and not message.tool_calls:
        return AIMessage(content=text)

    return None


def _write_prompt_to_file(messages: list[BaseMessage]) -> None:
    try:
        from datetime import datetime

        root_dir = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        logs_dir = os.path.join(root_dir, ".logs")
        os.makedirs(logs_dir, exist_ok=True)
        log_file_path = os.path.join(logs_dir, "agent_prompts.txt")

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_lines = []
        log_lines.append("=" * 60)
        log_lines.append(f"Timestamp: {now_str}")
        log_lines.append("=== PROMPT SENT TO MODEL ===")

        for msg in messages:
            role = type(msg).__name__
            content = msg.content

            if isinstance(content, str):
                log_lines.append(f"[{role}]: {content.strip()}")
            elif isinstance(content, list):
                log_lines.append(f"[{role}]:")
                for block in content:
                    if isinstance(block, dict):
                        block_type = block.get("type")
                        if block_type == "text":
                            log_lines.append(
                                f"  - Text: {block.get('text', '').strip()}"
                            )
                        elif block_type == "image_url":
                            url = block.get("image_url", {}).get("url", "")
                            if url.startswith("data:image"):
                                truncated_url = (
                                    url[:60] + "... [truncated base64 image data]"
                                )
                                log_lines.append(f"  - Image URL: {truncated_url}")
                            else:
                                log_lines.append(f"  - Image URL: {url}")
                        elif block_type == "audio":
                            mime = block.get("mime_type", "unknown")
                            log_lines.append(
                                f"  - Audio: [base64 audio data, mime={mime} (truncated)]"
                            )
                        else:
                            log_lines.append(
                                f"  - {block_type or 'Unknown'}: {str(block)}"
                            )
                    else:
                        log_lines.append(f"  - {str(block)}")
            else:
                log_lines.append(f"[{role}]: {str(content)}")

        log_lines.append("=" * 60 + "\n\n")

        with open(log_file_path, "a", encoding="utf-8") as f:
            f.write("\n".join(log_lines))

    except Exception as e:
        logger.error("Failed to write agent prompt to file: %s", e)


@before_model
def trim_messages(state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
    """Keep compact text-only conversation history before each model call."""
    messages = state["messages"]

    current_turn_start = _latest_human_message_index(messages)
    if current_turn_start is None:
        history_messages = messages
        current_turn_messages: list[BaseMessage] = []
    else:
        history_messages = messages[:current_turn_start]
        current_turn_messages = messages[current_turn_start:]

    system_messages: list[BaseMessage] = []
    conversation_messages: list[BaseMessage] = []

    for message in history_messages:
        clean_message = _clean_history_message(message)
        if clean_message is None:
            continue
        if isinstance(clean_message, SystemMessage):
            system_messages.append(clean_message)
        else:
            conversation_messages.append(clean_message)

    compact_history = conversation_messages[-MAX_HISTORY_MESSAGES:]
    new_messages = [*system_messages, *compact_history, *current_turn_messages]

    # Write the compiled prompt to the log file before calling the model
    _write_prompt_to_file(new_messages)

    if new_messages == messages:
        return None

    logger.info(
        "Trimmed conversation history from %d to %d messages.",
        len(messages),
        len(new_messages),
    )
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
                model=LLM_MODEL,
                base_url=LLM_BASE_URL,
                api_key=LLM_API_KEY,
            )
            self._agent = create_agent(
                model=llm,
                tools=all_agent_tools,
                system_prompt=SYSTEM_PROMPT,
                middleware=[trim_messages],
                checkpointer=InMemorySaver(),
            )
            logger.info(
                "Viva agent initialized with LLM model '%s' via llama-server.",
                LLM_MODEL,
            )

    async def run(
        self,
        text: str,
        screenshot_bytes: bytes | None = None,
        screenshot_content_type: str | None = None,
        screenshot_filename: str | None = None,
        audio_bytes: bytes | None = None,
        audio_content_type: str | None = None,
        audio_filename: str | None = None,
    ) -> str:
        await self.initialize()

        user_message = _build_user_message(
            text=text,
            screenshot_bytes=screenshot_bytes,
            screenshot_content_type=screenshot_content_type,
            screenshot_filename=screenshot_filename,
            audio_bytes=audio_bytes,
            audio_content_type=audio_content_type,
            audio_filename=audio_filename,
        )

        config: RunnableConfig = {"configurable": {"thread_id": "1"}}

        async with self._invocation_lock:
            response = await self._agent.ainvoke(
                {"messages": [user_message]},
                config=config,
            )
        response_text = _extract_response_text(response)
        logger.info(response_text)
        if not response_text:
            raise RuntimeError("The agent did not return text.")
        return response_text


async def run_viva_agent(
    text: str,
    screenshot_bytes: bytes | None = None,
    screenshot_content_type: str | None = None,
    screenshot_filename: str | None = None,
    audio_bytes: bytes | None = None,
    audio_content_type: str | None = None,
    audio_filename: str | None = None,
    service: VivaAgentService | None = None,
) -> str:
    viva_service = service or VivaAgentService()
    return await viva_service.run(
        text=text,
        screenshot_bytes=screenshot_bytes,
        screenshot_content_type=screenshot_content_type,
        screenshot_filename=screenshot_filename,
        audio_bytes=audio_bytes,
        audio_content_type=audio_content_type,
        audio_filename=audio_filename,
    )


async def _demo() -> None:
    service = VivaAgentService()
    response = await service.run("What day is it today?")
    print(response)


if __name__ == "__main__":
    asyncio.run(_demo())
