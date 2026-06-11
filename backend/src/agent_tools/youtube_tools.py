import asyncio
import logging
import os
import shutil
import subprocess
import tempfile
import unicodedata
from pathlib import Path
from typing import Any

from langchain_core.tools import tool
from yt_dlp import YoutubeDL, parse_options
from yt_dlp.utils import DownloadError, sanitize_filename

logger = logging.getLogger(__name__)

DEFAULT_YOUTUBE_DOWNLOAD_DIR = Path.home() / "Downloads"
DEFAULT_OUTPUT_TEMPLATE = "%(title).200B_%(id)s.%(ext)s"
MEDIA_SUFFIXES = {".aac", ".flac", ".m4a", ".mkv", ".mp3", ".mp4", ".opus", ".wav", ".webm"}


def _require_ffmpeg() -> None:
    missing = [name for name in ("ffmpeg", "ffprobe") if not shutil.which(name)]
    if missing:
        raise RuntimeError(
            "Missing required executable(s): "
            f"{', '.join(missing)}. Install ffmpeg so YouTube downloads can "
            "be converted to the requested media format."
        )


def _resolve_output_dir(output_dir: str | None) -> Path:
    directory = (
        Path(output_dir).expanduser() if output_dir else DEFAULT_YOUTUBE_DOWNLOAD_DIR
    )
    directory.mkdir(parents=True, exist_ok=True)
    if not directory.is_dir():
        raise ValueError(f"Output path is not a directory: {directory}")
    return directory.resolve()


def _sanitize_stem(value: str) -> str:
    ascii_value = (
        unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    )
    stem = sanitize_filename(ascii_value, restricted=True).strip(". ")
    if not stem:
        raise ValueError("Filename must contain at least one usable ASCII character.")
    return stem


def _output_template(filename: str | None, extension: str) -> str:
    if not filename or not filename.strip():
        return DEFAULT_OUTPUT_TEMPLATE

    stem = Path(filename.strip()).name
    suffix = Path(stem).suffix.lower()
    if suffix == f".{extension}" or suffix in MEDIA_SUFFIXES:
        stem = stem[: -len(suffix)]
    stem = _sanitize_stem(stem)
    return f"{stem}.%(ext)s"


def _unique_path(path: Path) -> Path:
    candidate = path
    counter = 1
    while candidate.exists():
        candidate = path.with_name(f"{path.stem}_{counter}{path.suffix}")
        counter += 1
    return candidate


def _sanitize_download_path(path: Path, extension: str) -> Path:
    sanitized_stem = _sanitize_stem(path.stem)
    sanitized_path = path.with_name(f"{sanitized_stem}.{extension}")
    if sanitized_path.name == path.name:
        return path.resolve()

    if sanitized_path.exists():
        sanitized_path = _unique_path(sanitized_path)
    path.rename(sanitized_path)
    return sanitized_path.resolve()


def _base_ydl_options(
    output_dir: Path,
    filename: str | None,
    output_extension: str,
) -> dict[str, Any]:
    return {
        "outtmpl": str(output_dir / _output_template(filename, output_extension)),
        "noplaylist": True,
        "continuedl": True,
        "retries": 10,
        "fragment_retries": 10,
        "extractor_retries": 3,
        "file_access_retries": 5,
        "socket_timeout": 30,
        "concurrent_fragment_downloads": 4,
        "windowsfilenames": True,
        "restrictfilenames": True,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "ignoreerrors": False,
    }


def _video_ydl_options(output_dir: Path, filename: str | None) -> dict[str, Any]:
    return {
        **_base_ydl_options(output_dir, filename, "mp4"),
        "format": "bv*+ba/b",
        "merge_output_format": "mp4",
        "remuxvideo": "mp4",
    }


def _audio_ydl_options(output_dir: Path, filename: str | None) -> dict[str, Any]:
    return {
        **_base_ydl_options(output_dir, filename, "mp3"),
        "format": "bestaudio/best",
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "0",
            }
        ],
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


def _find_downloaded_mp3(
    info: dict[str, Any] | None,
    output_dir: Path,
    started_with: dict[Path, int],
) -> Path | None:
    for item in _flatten_download_info(info):
        for path in _candidate_paths(item, output_dir):
            mp3_path = path.with_suffix(".mp3")
            if mp3_path.exists():
                return mp3_path.resolve()
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


def _overwrite_with_h264_mp4(mp4_path: Path) -> None:
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{mp4_path.stem}.h264.",
        suffix=".mp4",
        dir=mp4_path.parent,
    )
    os.close(fd)
    temp_path = Path(temp_name)
    try:
        command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(mp4_path),
            "-map",
            "0:v:0",
            "-map",
            "0:a?",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            str(temp_path),
        ]
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            details = (completed.stderr or completed.stdout).strip()
            raise RuntimeError(f"ffmpeg h.264 conversion failed: {details}")
        os.replace(temp_path, mp4_path)
    finally:
        temp_path.unlink(missing_ok=True)


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
    options = _video_ydl_options(directory, filename)
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

    mp4_path = _sanitize_download_path(mp4_path, "mp4")
    logger.info("Converting YouTube video to h.264 mp4 with ffmpeg: %s", mp4_path)
    _overwrite_with_h264_mp4(mp4_path)

    size_mb = mp4_path.stat().st_size / (1024 * 1024)
    return f"Downloaded YouTube video to {mp4_path} ({size_mb:.1f} MB, h.264 mp4)."


def _download_youtube_audio_blocking(
    url: str,
    output_dir: str | None = None,
    filename: str | None = None,
    cookies_from_browser: str | None = None,
) -> str:
    cleaned_url = url.strip()
    if not cleaned_url:
        raise ValueError("A YouTube video URL is required.")

    _require_ffmpeg()
    directory = _resolve_output_dir(output_dir)
    started_with = {
        path.resolve(): path.stat().st_mtime_ns for path in directory.glob("*.mp3")
    }
    options = _audio_ydl_options(directory, filename)
    if cookies_from_browser and cookies_from_browser.strip():
        options["cookiesfrombrowser"] = _cookies_from_browser(cookies_from_browser)

    logger.info("Downloading YouTube audio with yt-dlp: %s", cleaned_url)
    with YoutubeDL(options) as ydl:
        info = ydl.extract_info(cleaned_url, download=True)

    mp3_path = _find_downloaded_mp3(info, directory, started_with)
    if not mp3_path:
        raise RuntimeError(
            f"Download completed, but no mp3 output file was found in {directory}."
        )

    mp3_path = _sanitize_download_path(mp3_path, "mp3")
    size_mb = mp3_path.stat().st_size / (1024 * 1024)
    return f"Downloaded YouTube audio to {mp3_path} ({size_mb:.1f} MB, high-quality mp3)."


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
        allow_reencode_if_needed: If true, lets yt-dlp retry with mp4 re-encoding when remuxing fails. The final file is always converted to h.264 mp4.
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


@tool
async def download_youtube_audio_mp3(
    url: str,
    output_dir: str | None = None,
    filename: str | None = None,
    cookies_from_browser: str | None = None,
) -> str:
    """
    Downloads only the audio from a YouTube video and saves it as a high-quality mp3.

    Uses yt-dlp with ffmpeg/ffprobe. The tool downloads the best available audio
    stream, converts it to a high-quality mp3, resumes partial downloads, and
    retries transient network failures.

    Args:
        url: The YouTube video URL to download audio from.
        output_dir: Optional directory where the mp3 should be saved. Defaults to ~/Downloads.
        filename: Optional output filename or stem. The final extension is always mp3.
        cookies_from_browser: Optional browser name/profile for yt-dlp cookies, such as "safari", "chrome", or "firefox:default".
    """
    try:
        return await asyncio.to_thread(
            _download_youtube_audio_blocking,
            url,
            output_dir,
            filename,
            cookies_from_browser,
        )
    except Exception as exc:
        return f"YouTube audio download failed: {exc}"


youtube_tools = [download_youtube_video, download_youtube_audio_mp3]


__all__ = [
    "download_youtube_audio_mp3",
    "download_youtube_video",
    "youtube_tools",
]
