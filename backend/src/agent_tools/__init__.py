from .applescript_tools import all_mac_tools
from .general_tools import (
    extract_webpage_text,
    general_tools,
    get_current_datetime,
    get_weather,
    python_repl_tool,
    web_search,
)
from .pdf_tools import (
    convert_pdf_to_markdown,
    extract_pdf_images,
    extract_pdf_text,
    get_pdf_metadata,
    pdf_tools,
    render_pdf_pages_to_images,
    search_pdf_text,
    split_pdf_pages,
    summarize_pdf,
)
from .youtube_tools import (
    download_youtube_video,
    youtube_tools,
)


all_agent_tools = [
    *general_tools,
    *pdf_tools,
    *youtube_tools,
    *all_mac_tools,
]


__all__ = [
    "all_agent_tools",
    "all_mac_tools",
    "extract_webpage_text",
    "general_tools",
    "get_current_datetime",
    "get_weather",
    "get_pdf_metadata",
    "convert_pdf_to_markdown",
    "extract_pdf_images",
    "extract_pdf_text",
    "pdf_tools",
    "python_repl_tool",
    "render_pdf_pages_to_images",
    "search_pdf_text",
    "split_pdf_pages",
    "summarize_pdf",
    "download_youtube_video",
    "youtube_tools",
    "web_search",
]
