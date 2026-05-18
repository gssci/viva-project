import subprocess
from pathlib import Path
from langchain_core.tools import tool
from .finder import _selected_finder_paths

@tool
def convert_media_file(target_format: str) -> str:
    """
    Converts the currently selected media file in Finder to a specified format using ffmpeg.
    The output file will have the same name and path as the input, but with the new extension.
    
    Args:
        target_format: The desired file extension.
    """
    paths = _selected_finder_paths()
    if not paths:
        return "No items selected in Finder."
    
    if len(paths) > 1:
        return "Please select only one file for conversion."

    input_path = Path(paths[0])
    if not input_path.is_file():
        return f"The selected item '{input_path.name}' is not a file."

    # Create output path with the new extension
    output_path = input_path.with_suffix(f".{target_format.strip('.')}")

    # Construct ffmpeg command
    # We use -y to overwrite if file exists, but in a real assistant 
    # we might want to check first. Given the prompt, we'll just run it.
    command = ["ffmpeg", "-i", str(input_path), "-y", str(output_path)]

    try:
        # Run ffmpeg as a separate process
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        return f"Successfully converted '{input_path.name}' to '{output_path.name}'."
    except subprocess.CalledProcessError as e:
        return f"Error during conversion: {e.stderr.strip()}"
    except Exception as e:
        return f"An unexpected error occurred: {str(e)}"

media_converter_tools = [
    convert_media_file,
]
