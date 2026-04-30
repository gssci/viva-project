from langchain_core.tools import tool

from .core import run_applescript


@tool
def get_clipboard_content() -> str:
    """
    Reads the current text content from the Mac Clipboard.
    Call this tool when the user asks you to read, summarize, translate, or interact with the text they just copied.
    """
    script = "the clipboard as text"
    result = run_applescript(script)
    if "Error" in result:
        return "No text found in the clipboard."
    return result


@tool
def set_clipboard_content(text: str) -> str:
    """
    Overwrites the Mac clipboard with the provided text.
    Call this tool when the user asks you to copy your response or generate text directly to their clipboard.

    Args:
        text: The text to copy to the clipboard.
    """
    safe_text = text.replace('"', '\\"').replace("\n", "\\n")
    script = f'set the clipboard to "{safe_text}"'
    run_applescript(script)
    return "Text successfully copied to the clipboard."


@tool
def get_active_safari_url() -> str:
    """
    Gets the URL and title of the currently active, frontmost tab in Safari.
    Call this tool when the user asks questions about "this article", "the page I'm reading", or asks you to scrape their current context.
    """
    script = """
    tell application "Safari"
        if it is running then
            set currentTab to current tab of front window
            set tabURL to URL of currentTab
            set tabName to name of currentTab
            return tabName & "\\n" & tabURL
        else
            return "Safari is not currently running."
        end if
    end tell
    """
    return run_applescript(script)


@tool
def get_finder_selection_path() -> str:
    """
    Returns the POSIX path of the file or folder currently selected in Finder.
    Call this tool when the user asks you to read, modify, or do something with "the selected file" or "this file in Finder".
    """
    script = """
    tell application "Finder"
        set selectedItems to selection
        if (count of selectedItems) = 0 then
            return "No items selected in Finder."
        end if
        set theItem to item 1 of selectedItems
        return POSIX path of (theItem as alias)
    end tell
    """
    return run_applescript(script)


context_tools = [
    get_clipboard_content,
    set_clipboard_content,
    get_active_safari_url,
    get_finder_selection_path,
]
