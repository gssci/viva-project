from .applescript_tools import all_mac_tools
from .general_tools import (
    extract_webpage_text,
    general_tools,
    get_current_datetime,
    get_weather,
    python_repl_tool,
    web_search,
)


all_agent_tools = [
    *general_tools,
    *all_mac_tools,
]


__all__ = [
    "all_agent_tools",
    "all_mac_tools",
    "extract_webpage_text",
    "general_tools",
    "get_current_datetime",
    "get_weather",
    "python_repl_tool",
    "web_search",
]
