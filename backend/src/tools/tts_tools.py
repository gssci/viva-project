from __future__ import annotations

import logging
import os
import re
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

import mlx.core as mx
from mlx_audio.audio_io import write as audio_write
from mlx_audio.tts.utils import load as load_tts_model
from trafilatura.settings import Extractor

from tools.language_tools import detect_language

logger = logging.getLogger(__name__)

DEFAULT_TTS_MODEL = "prince-canuma/Kokoro-82M"
DEFAULT_OUTPUT_DIR = Path(tempfile.gettempdir()) / "viva_tts_audio"

KOKORO_VOICE_BY_LANGUAGE = {
    "en": os.getenv("VIVA_TTS_EN_VOICE", "af_heart"),
    "it": os.getenv("VIVA_TTS_IT_VOICE", "im_nicola"),
    "other": os.getenv("VIVA_TTS_FALLBACK_VOICE", "af_heart"),
}

KOKORO_LANG_CODE_BY_LANGUAGE = {
    "en": "a",
    "it": "i",
    "other": "a",
}

KOKORO_SPEED_BY_LANGUAGE = {
    "en": float(os.getenv("VIVA_TTS_EN_SPEED", "1.0")),
    "it": float(os.getenv("VIVA_TTS_IT_SPEED", "1.25")),
    "other": float(os.getenv("VIVA_TTS_FALLBACK_SPEED", "1.0")),
}


@dataclass(frozen=True)
class TTSAudioResult:
    path: Path
    language: str
    voice: str
    sample_rate: int
    duration_seconds: float | None
    processing_time: float


def _chunk_text_for_tts(text: str, max_chars: int = 220) -> str:
    sentences = re.split(r"(?<=[.!?;:])\s+", text.strip())
    chunks: list[str] = []
    current = ""

    for sentence in sentences:
        if not sentence:
            continue

        if len(sentence) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_split_long_sentence(sentence, max_chars))
            continue

        candidate = f"{current} {sentence}".strip()
        if current and len(candidate) > max_chars:
            chunks.append(current)
            current = sentence
        else:
            current = candidate

    if current:
        chunks.append(current)

    return "\n".join(chunks) if chunks else text


def _split_long_sentence(sentence: str, max_chars: int) -> list[str]:
    words = sentence.split()
    chunks: list[str] = []
    current = ""

    for word in words:
        candidate = f"{current} {word}".strip()
        if current and len(candidate) > max_chars:
            chunks.append(current)
            current = word
        else:
            current = candidate

    if current:
        chunks.append(current)
    return chunks


options = Extractor(
    output_format="txt",
    with_metadata=False,
    comments=False,
    formatting=False,
    images=False,
    links=False,
    tables=False,
    precision=True,
)


class VivaTTSService:
    """
    Thread-safe lazy wrapper around mlx-audio Kokoro generation.

    The backend generates audio files only; playback is owned by the Swift app.
    """

    def __init__(
        self,
        model_name: str | None = None,
        output_dir: str | Path | None = None,
        audio_format: str = "wav",
        max_age_seconds: int = 60 * 60,
    ) -> None:
        self.model_name = model_name or os.getenv("VIVA_TTS_MODEL", DEFAULT_TTS_MODEL)
        self.output_dir = Path(
            output_dir or os.getenv("VIVA_TTS_OUTPUT_DIR", str(DEFAULT_OUTPUT_DIR))
        )
        self.audio_format = audio_format
        self.max_age_seconds = max_age_seconds
        self._model = None
        self._lock = threading.Lock()

        self.output_dir.mkdir(parents=True, exist_ok=True)

    @property
    def output_directory(self) -> Path:
        return self.output_dir

    def warm_up(self) -> None:
        with self._lock:
            self._load_model_locked()

    def cleanup_old_files(self) -> None:
        now = time.time()
        for audio_path in self.output_dir.glob(f"*.{self.audio_format}"):
            try:
                if now - audio_path.stat().st_mtime > self.max_age_seconds:
                    audio_path.unlink()
            except OSError:
                logger.debug("Unable to remove old TTS file: %s", audio_path)

    def synthesize_to_file(self, text: str) -> TTSAudioResult:
        clean_text = text.strip()
        if not clean_text:
            raise ValueError("Cannot synthesize empty text.")

        language = detect_language(clean_text)
        voice = KOKORO_VOICE_BY_LANGUAGE.get(
            language, KOKORO_VOICE_BY_LANGUAGE["other"]
        )
        lang_code = KOKORO_LANG_CODE_BY_LANGUAGE.get(
            language, KOKORO_LANG_CODE_BY_LANGUAGE["other"]
        )
        speed = KOKORO_SPEED_BY_LANGUAGE.get(
            language, KOKORO_SPEED_BY_LANGUAGE["other"]
        )
        tts_text = _chunk_text_for_tts(clean_text)
        file_name = f"{uuid.uuid4().hex}.{self.audio_format}"
        audio_path = self.output_dir / file_name

        start_time = time.time()
        with self._lock:
            model = self._load_model_locked()
            results = list(
                model.generate(
                    text=tts_text,
                    voice=voice,
                    speed=speed,
                    lang_code=lang_code,
                )
            )

            audio_chunks = [
                result.audio for result in results if result.audio is not None
            ]
            if not audio_chunks:
                raise RuntimeError("Kokoro did not generate audio.")

            sample_rate = results[0].sample_rate
            audio = (
                mx.concatenate(audio_chunks, axis=0)
                if len(audio_chunks) > 1
                else audio_chunks[0]
            )
            audio_write(str(audio_path), audio, sample_rate, format=self.audio_format)
            mx.clear_cache()

        if not audio_path.exists() or audio_path.stat().st_size == 0:
            raise RuntimeError(f"TTS audio file was not created: {audio_path}")

        duration_seconds = self._duration_seconds(results)
        processing_time = time.time() - start_time
        self.cleanup_old_files()

        logger.info(
            "TTS audio generated. language=%s voice=%s duration=%s processing_time=%.2fs path=%s",
            language,
            voice,
            f"{duration_seconds:.2f}s" if duration_seconds is not None else "unknown",
            processing_time,
            audio_path,
        )

        return TTSAudioResult(
            path=audio_path,
            language=language,
            voice=voice,
            sample_rate=sample_rate,
            duration_seconds=duration_seconds,
            processing_time=round(processing_time, 2),
        )

    def _load_model_locked(self):
        if self._model is None:
            logger.info("Loading TTS model '%s'...", self.model_name)
            self._model = load_tts_model(self.model_name)
            logger.info("TTS model loaded.")
        return self._model

    @staticmethod
    def _duration_seconds(results) -> float | None:
        total_samples = 0
        sample_rate = None
        for result in results:
            if result.audio is None:
                continue
            sample_rate = result.sample_rate
            total_samples += int(result.audio.shape[0])

        if not sample_rate:
            return None
        return total_samples / sample_rate


def synthesize_speech_to_file(
    text: str, output_dir: str | Path | None = None
) -> TTSAudioResult:
    return VivaTTSService(output_dir=output_dir).synthesize_to_file(text)


def read_this(text: str) -> Path:
    """
    Backward-compatible helper: generate audio and return the WAV path.
    """
    return synthesize_speech_to_file(text).path


if __name__ == "__main__":
    result = synthesize_speech_to_file("Hello, I am Viva. This is an audio test.")
    print(result.path)
