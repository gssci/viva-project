import asyncio
import logging
import shutil
from pathlib import Path
from typing import Any

from langchain_core.tools import tool
from yt_dlp import YoutubeDL, parse_options
from yt_dlp.utils import sanitize_filename

logger = logging.getLogger(__name__)

DEFAULT_SOUNDCLOUD_DOWNLOAD_DIR = Path.home() / "Downloads"
DEFAULT_OUTPUT_TEMPLATE = "%(title).200B [%(id)s].%(ext)s"


def _require_ffmpeg() -> None:
    missing = [name for name in ("ffmpeg", "ffprobe") if not shutil.which(name)]
    if missing:
        raise RuntimeError(
            "Missing required executable(s): "
            f"{', '.join(missing)}. Install ffmpeg so yt-dlp can convert "
            "SoundCloud audio to mp3."
        )


def _resolve_output_dir(output_dir: str | None) -> Path:
    directory = (
        Path(output_dir).expanduser()
        if output_dir
        else DEFAULT_SOUNDCLOUD_DOWNLOAD_DIR
    )
    directory.mkdir(parents=True, exist_ok=True)
    if not directory.is_dir():
        raise ValueError(f"Output path is not a directory: {directory}")
    return directory.resolve()


def _output_template(filename: str | None) -> str:
    if not filename or not filename.strip():
        return DEFAULT_OUTPUT_TEMPLATE

    stem = Path(filename.strip()).name
    if stem.lower().endswith(".mp3"):
        stem = stem[:-4]
    stem = sanitize_filename(stem, restricted=False).strip(". ")
    if not stem:
        raise ValueError("Filename must contain at least one usable character.")
    return f"{stem}.%(ext)s"


def _cookies_from_browser(value: str) -> tuple[str, str | None, str | None, str | None]:
    parsed_options = parse_options(["--cookies-from-browser", value, "about:blank"])
    return parsed_options.ydl_opts["cookiesfrombrowser"]


def _base_ydl_options(output_dir: Path, filename: str | None) -> dict[str, Any]:
    return {
        "format": "bestaudio/best",
        "outtmpl": str(output_dir / _output_template(filename)),
        "noplaylist": True,
        "continuedl": True,
        "retries": 10,
        "fragment_retries": 10,
        "extractor_retries": 3,
        "file_access_retries": 5,
        "socket_timeout": 30,
        "windowsfilenames": True,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "ignoreerrors": False,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "0",
            }
        ],
    }


def _flatten_download_info(info: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not info:
        return []
    entries = info.get("entries")
    if isinstance(entries, list):
        return [entry for entry in entries if isinstance(entry, dict)]
    return [info]


def _candidate_paths(info: dict[str, Any], output_dir: Path) -> list[Path]:
    candidates: list[Path] = []

    for download in info.get("requested_downloads") or []:
        if isinstance(download, dict) and download.get("filepath"):
            candidates.append(Path(download["filepath"]))

    for key in ("filepath", "_filename"):
        if info.get(key):
            candidates.append(Path(info[key]))

    for path in list(candidates):
        candidates.append(path.with_suffix(".mp3"))

    seen: set[Path] = set()
    unique_candidates: list[Path] = []
    for path in candidates:
        resolved = path.expanduser()
        if not resolved.is_absolute():
            resolved = output_dir / resolved
        if resolved not in seen:
            seen.add(resolved)
            unique_candidates.append(resolved)
    return unique_candidates


def _find_downloaded_mp3(
    info: dict[str, Any] | None,
    output_dir: Path,
    started_with: dict[Path, int],
) -> Path | None:
    for item in _flatten_download_info(info):
        for path in _candidate_paths(item, output_dir):
            if path.exists() and path.suffix.lower() == ".mp3":
                return path.resolve()

    new_or_changed = []
    for path in output_dir.glob("*.mp3"):
        try:
            stat = path.stat()
        except OSError:
            continue
        if started_with.get(path.resolve()) != stat.st_mtime_ns:
            new_or_changed.append((stat.st_mtime_ns, path))

    if new_or_changed:
        return max(new_or_changed, key=lambda item: item[0])[1].resolve()
    return None


def _download_soundcloud_audio_blocking(
    url: str,
    output_dir: str | None = None,
    filename: str | None = None,
    cookies_from_browser: str | None = None,
) -> str:
    cleaned_url = url.strip()
    if not cleaned_url:
        raise ValueError("A SoundCloud track URL is required.")

    _require_ffmpeg()
    directory = _resolve_output_dir(output_dir)
    started_with = {
        path.resolve(): path.stat().st_mtime_ns for path in directory.glob("*.mp3")
    }
    options = _base_ydl_options(directory, filename)
    if cookies_from_browser and cookies_from_browser.strip():
        options["cookiesfrombrowser"] = _cookies_from_browser(cookies_from_browser)

    logger.info("Downloading SoundCloud audio with yt-dlp: %s", cleaned_url)
    with YoutubeDL(options) as ydl:
        info = ydl.extract_info(cleaned_url, download=True)

    mp3_path = _find_downloaded_mp3(info, directory, started_with)
    if not mp3_path:
        raise RuntimeError(
            f"Download completed, but no mp3 output file was found in {directory}."
        )

    size_mb = mp3_path.stat().st_size / (1024 * 1024)
    return f"Downloaded SoundCloud audio to {mp3_path} ({size_mb:.1f} MB)."


@tool
async def download_soundcloud_audio(
    url: str,
    output_dir: str | None = None,
    filename: str | None = None,
    cookies_from_browser: str | None = None,
) -> str:
    """
    Downloads a SoundCloud track and saves it as an mp3 file.

    Uses yt-dlp with ffmpeg/ffprobe. The tool downloads the best available
    audio stream, converts it to mp3, resumes partial downloads, and retries
    transient network failures.

    Args:
        url: The SoundCloud track URL to download.
        output_dir: Optional directory where the mp3 should be saved. Defaults to ~/Downloads.
        filename: Optional output filename or stem. The final extension is always mp3.
        cookies_from_browser: Optional browser name/profile for yt-dlp cookies, such as "safari", "chrome", or "firefox:default".
    """
    try:
        return await asyncio.to_thread(
            _download_soundcloud_audio_blocking,
            url,
            output_dir,
            filename,
            cookies_from_browser,
        )
    except Exception as exc:
        return f"SoundCloud download failed: {exc}"


soundcloud_tools = [download_soundcloud_audio]
