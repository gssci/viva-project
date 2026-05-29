import asyncio
import logging
import shutil
from pathlib import Path
from typing import Any

from langchain_core.tools import tool
from yt_dlp import YoutubeDL, parse_options
from yt_dlp.utils import DownloadError, sanitize_filename

logger = logging.getLogger(__name__)

DEFAULT_YOUTUBE_DOWNLOAD_DIR = Path.home() / "Downloads"
DEFAULT_OUTPUT_TEMPLATE = "%(title).200B [%(id)s].%(ext)s"


def _require_ffmpeg() -> None:
    missing = [name for name in ("ffmpeg", "ffprobe") if not shutil.which(name)]
    if missing:
        raise RuntimeError(
            "Missing required executable(s): "
            f"{', '.join(missing)}. Install ffmpeg so yt-dlp can merge best "
            "video and audio streams into mp4."
        )


def _resolve_output_dir(output_dir: str | None) -> Path:
    directory = (
        Path(output_dir).expanduser() if output_dir else DEFAULT_YOUTUBE_DOWNLOAD_DIR
    )
    directory.mkdir(parents=True, exist_ok=True)
    if not directory.is_dir():
        raise ValueError(f"Output path is not a directory: {directory}")
    return directory.resolve()


def _output_template(filename: str | None) -> str:
    if not filename or not filename.strip():
        return DEFAULT_OUTPUT_TEMPLATE

    stem = Path(filename.strip()).name
    if stem.lower().endswith(".mp4"):
        stem = stem[:-4]
    stem = sanitize_filename(stem, restricted=False).strip(". ")
    if not stem:
        raise ValueError("Filename must contain at least one usable character.")
    return f"{stem}.%(ext)s"


def _base_ydl_options(output_dir: Path, filename: str | None) -> dict[str, Any]:
    return {
        "format": "bv*+ba/b",
        "outtmpl": str(output_dir / _output_template(filename)),
        "merge_output_format": "mp4",
        "remuxvideo": "mp4",
        "noplaylist": True,
        "continuedl": True,
        "retries": 10,
        "fragment_retries": 10,
        "extractor_retries": 3,
        "file_access_retries": 5,
        "socket_timeout": 30,
        "concurrent_fragment_downloads": 4,
        "windowsfilenames": True,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "ignoreerrors": False,
    }


def _cookies_from_browser(value: str) -> tuple[str, str | None, str | None, str | None]:
    parsed_options = parse_options(["--cookies-from-browser", value, "about:blank"])
    return parsed_options.ydl_opts["cookiesfrombrowser"]


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

    original_ext = info.get("ext")
    if original_ext:
        for path in list(candidates):
            candidates.append(path.with_suffix(".mp4"))
            candidates.append(path.with_suffix(f".{original_ext}"))

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


def _find_downloaded_mp4(
    info: dict[str, Any] | None,
    output_dir: Path,
    started_with: dict[Path, int],
) -> Path | None:
    for item in _flatten_download_info(info):
        for path in _candidate_paths(item, output_dir):
            if path.exists() and path.suffix.lower() == ".mp4":
                return path.resolve()

    new_or_changed = []
    for path in output_dir.glob("*.mp4"):
        try:
            stat = path.stat()
        except OSError:
            continue
        if started_with.get(path.resolve()) != stat.st_mtime_ns:
            new_or_changed.append((stat.st_mtime_ns, path))

    if new_or_changed:
        return max(new_or_changed, key=lambda item: item[0])[1].resolve()
    return None


def _download_youtube_video_blocking(
    url: str,
    output_dir: str | None = None,
    filename: str | None = None,
    cookies_from_browser: str | None = None,
    allow_reencode_if_needed: bool = True,
) -> str:
    cleaned_url = url.strip()
    if not cleaned_url:
        raise ValueError("A YouTube video URL is required.")

    _require_ffmpeg()
    directory = _resolve_output_dir(output_dir)
    started_with = {
        path.resolve(): path.stat().st_mtime_ns for path in directory.glob("*.mp4")
    }
    options = _base_ydl_options(directory, filename)
    if cookies_from_browser and cookies_from_browser.strip():
        options["cookiesfrombrowser"] = _cookies_from_browser(cookies_from_browser)

    logger.info("Downloading YouTube video with yt-dlp: %s", cleaned_url)
    try:
        with YoutubeDL(options) as ydl:
            info = ydl.extract_info(cleaned_url, download=True)
    except DownloadError:
        if not allow_reencode_if_needed:
            raise
        logger.info(
            "yt-dlp remux failed for %s; retrying with mp4 re-encode fallback",
            cleaned_url,
        )
        fallback_options = {**options, "recodevideo": "mp4"}
        with YoutubeDL(fallback_options) as ydl:
            info = ydl.extract_info(cleaned_url, download=True)

    mp4_path = _find_downloaded_mp4(info, directory, started_with)
    if not mp4_path:
        raise RuntimeError(
            f"Download completed, but no mp4 output file was found in {directory}."
        )

    size_mb = mp4_path.stat().st_size / (1024 * 1024)
    return f"Downloaded YouTube video to {mp4_path} ({size_mb:.1f} MB)."


@tool
async def download_youtube_video(
    url: str,
    output_dir: str | None = None,
    filename: str | None = None,
    cookies_from_browser: str | None = None,
    allow_reencode_if_needed: bool = True,
) -> str:
    """
    Downloads a YouTube video in the highest available quality and saves it as mp4.

    Uses yt-dlp with ffmpeg/ffprobe. The tool downloads the best available video
    and audio streams, merges them into an mp4, resumes partial downloads, and
    retries transient network failures.

    Args:
        url: The YouTube video URL to download.
        output_dir: Optional directory where the mp4 should be saved. Defaults to ~/Downloads.
        filename: Optional output filename or stem. The final extension is always mp4.
        cookies_from_browser: Optional browser name/profile for yt-dlp cookies, such as "safari", "chrome", or "firefox:default".
        allow_reencode_if_needed: If true, re-encode to mp4 only when lossless remuxing fails.
    """
    try:
        return await asyncio.to_thread(
            _download_youtube_video_blocking,
            url,
            output_dir,
            filename,
            cookies_from_browser,
            allow_reencode_if_needed,
        )
    except Exception as exc:
        return f"YouTube download failed: {exc}"


youtube_tools = [download_youtube_video]


__all__ = [
    "download_youtube_video",
    "youtube_tools",
]
