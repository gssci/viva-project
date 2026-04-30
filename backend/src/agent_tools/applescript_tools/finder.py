import datetime as dt
import zipfile
from pathlib import Path
from typing import Optional

from langchain_core.tools import tool

from .core import escape_applescript_string, run_applescript


def _selected_finder_paths() -> list[str]:
    script = """
    tell application "Finder"
        set selectedItems to selection
        if (count of selectedItems) = 0 then return ""
        set output to ""
        repeat with selectedItem in selectedItems
            set output to output & POSIX path of (selectedItem as alias) & "\\n"
        end repeat
        return output
    end tell
    """
    result = run_applescript(script)
    if result.startswith("Script execution error") or not result:
        return []
    return [line.strip() for line in result.splitlines() if line.strip()]


@tool
def list_finder_selection_paths() -> str:
    """
    Lists POSIX paths for all files and folders currently selected in Finder.
    Call this tool when the user asks about selected Finder items.
    """
    paths = _selected_finder_paths()
    if not paths:
        return "No items selected in Finder."
    return "\n".join(f"- {path}" for path in paths)


@tool
def list_finder_folder_contents(folder_path: str, max_results: int = 50) -> str:
    """
    Lists files and folders in a Finder folder with basic metadata.
    Call this tool when the user asks what is inside a folder.

    Args:
        folder_path: POSIX path to the folder.
        max_results: Maximum items to return, from 1 to 100.
    """
    if not folder_path.strip():
        return "Folder path cannot be empty."
    max_results = max(1, min(100, max_results))
    safe_path = escape_applescript_string(folder_path)
    script = f'''
    set folderAlias to POSIX file "{safe_path}" as alias
    tell application "Finder"
        try
            set folderItems to items of folderAlias
        on error
            return "Folder not found or is not a folder."
        end try
        set output to ""
        set itemCount to 0
        repeat with folderItem in folderItems
            set itemCount to itemCount + 1
            set output to output & "- " & name of folderItem & " | " & kind of folderItem & " | " & (modification date of folderItem as string) & "\\n"
            if itemCount is greater than or equal to {max_results} then return output
        end repeat
        if output is "" then return "Folder is empty."
        return output
    end tell
    '''
    return run_applescript(script)


@tool
def reveal_path_in_finder(path: str) -> str:
    """
    Reveals a file or folder in Finder.
    Call this tool when the user asks to show a path in Finder.

    Args:
        path: POSIX path to reveal.
    """
    if not path.strip():
        return "Path cannot be empty."
    safe_path = escape_applescript_string(path)
    script = f'''
    set targetItem to POSIX file "{safe_path}" as alias
    tell application "Finder"
        reveal targetItem
        activate
    end tell
    '''
    result = run_applescript(script)
    if result.startswith("Script execution error"):
        return "Could not reveal that path in Finder."
    return "Path revealed in Finder."


@tool
def open_path_in_finder(path: str) -> str:
    """
    Opens a file or folder using Finder.
    Call this tool when the user asks to open a path.

    Args:
        path: POSIX path to open.
    """
    if not path.strip():
        return "Path cannot be empty."
    safe_path = escape_applescript_string(path)
    script = f'''
    set targetItem to POSIX file "{safe_path}" as alias
    tell application "Finder"
        open targetItem
        activate
    end tell
    '''
    result = run_applescript(script)
    if result.startswith("Script execution error"):
        return "Could not open that path."
    return "Path opened."


@tool
def create_finder_folder(parent_path: str, folder_name: str) -> str:
    """
    Creates a folder inside a parent folder.
    Call this tool when the user asks to create a folder in Finder.

    Args:
        parent_path: POSIX path to the parent folder.
        folder_name: Name of the folder to create.
    """
    if not parent_path.strip() or not folder_name.strip() or "/" in folder_name:
        return "A parent path and simple folder name are required."
    safe_parent = escape_applescript_string(parent_path)
    safe_name = escape_applescript_string(folder_name)
    script = f'''
    set parentAlias to POSIX file "{safe_parent}" as alias
    tell application "Finder"
        make new folder at parentAlias with properties {{name:"{safe_name}"}}
        return "Folder created."
    end tell
    '''
    return run_applescript(script)


@tool
def duplicate_finder_selection() -> str:
    """
    Duplicates the selected Finder items in their current folder.
    Call this tool when the user asks to duplicate selected files or folders.
    """
    script = """
    tell application "Finder"
        set selectedItems to selection
        if (count of selectedItems) = 0 then return "No items selected in Finder."
        duplicate selectedItems
        return "Selected Finder items duplicated."
    end tell
    """
    return run_applescript(script)


@tool
def copy_finder_selection_to_folder(destination_folder_path: str) -> str:
    """
    Copies selected Finder items to a destination folder.
    Call this tool when the user asks to copy selected files or folders somewhere.

    Args:
        destination_folder_path: POSIX path to the destination folder.
    """
    if not destination_folder_path.strip():
        return "Destination folder path cannot be empty."
    safe_destination = escape_applescript_string(destination_folder_path)
    script = f'''
    set destinationAlias to POSIX file "{safe_destination}" as alias
    tell application "Finder"
        set selectedItems to selection
        if (count of selectedItems) = 0 then return "No items selected in Finder."
        duplicate selectedItems to destinationAlias
        return "Selected Finder items copied."
    end tell
    '''
    return run_applescript(script)


@tool
def compress_finder_selection(output_zip_path: Optional[str] = None) -> str:
    """
    Compresses selected Finder items into a zip archive. Does not delete or move originals.
    Call this tool when the user asks to zip or compress selected files or folders.

    Args:
        output_zip_path: (Optional) POSIX output path for the zip file. Defaults to Desktop with a timestamp.
    """
    paths = _selected_finder_paths()
    if not paths:
        return "No items selected in Finder."

    if output_zip_path:
        output_path = Path(output_zip_path).expanduser()
    else:
        timestamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        output_path = Path.home() / "Desktop" / f"finder-selection-{timestamp}.zip"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(
            output_path, "w", compression=zipfile.ZIP_DEFLATED
        ) as archive:
            used_names: set[str] = set()
            for index, selected_path in enumerate(paths, start=1):
                source = Path(selected_path)
                if not source.exists():
                    continue
                root_name = source.name
                if root_name in used_names:
                    root_name = f"{index}-{root_name}"
                used_names.add(root_name)

                if source.is_dir():
                    for child in source.rglob("*"):
                        if child.is_file():
                            archive.write(
                                child, Path(root_name) / child.relative_to(source)
                            )
                else:
                    archive.write(source, root_name)
    except OSError as exc:
        return f"Compression failed: {exc}"

    return f"Created zip archive at {output_path}."


finder_tools = [
    list_finder_selection_paths,
    list_finder_folder_contents,
    reveal_path_in_finder,
    open_path_in_finder,
    create_finder_folder,
    duplicate_finder_selection,
    copy_finder_selection_to_folder,
    compress_finder_selection,
]
