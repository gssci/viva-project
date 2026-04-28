from __future__ import annotations

import logging
import os
import re
import shutil
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import mlx.core as mx
from langdetect import DetectorFactory, detect, lang_detect_exception
from mlx_audio.audio_io import write as audio_write
from mlx_audio.tts.utils import load as load_tts_model

logger = logging.getLogger(__name__)
DetectorFactory.seed = 0

QwenLanguage = Literal[
    "Chinese",
    "English",
    "Japanese",
    "Korean",
    "German",
    "French",
    "Russian",
    "Portuguese",
    "Spanish",
    "Italian",
]

SUPPORTED_QWEN_TTS_LANGUAGES: tuple[QwenLanguage, ...] = (
    "Chinese",
    "English",
    "Japanese",
    "Korean",
    "German",
    "French",
    "Russian",
    "Portuguese",
    "Spanish",
    "Italian",
)

LANGDETECT_TO_QWEN_LANGUAGE: dict[str, QwenLanguage] = {
    "zh": "Chinese",
    "zh-cn": "Chinese",
    "zh-tw": "Chinese",
    "en": "English",
    "ja": "Japanese",
    "ko": "Korean",
    "de": "German",
    "fr": "French",
    "ru": "Russian",
    "pt": "Portuguese",
    "es": "Spanish",
    "it": "Italian",
}

DEFAULT_TTS_MODEL = "mlx-community/Qwen3-TTS-12Hz-0.6B-CustomVoice-6bit"
DEFAULT_OUTPUT_DIR = Path(tempfile.gettempdir()) / "viva_tts_audio"
DEFAULT_SPEAKER = os.getenv("VIVA_QWEN_TTS_SPEAKER", "Vivian")
DEFAULT_INSTRUCT = os.getenv("VIVA_QWEN_TTS_INSTRUCT", "Crisp, objective, and neutral delivery. Straightforward with no strong emotion.").strip() or None
DEFAULT_FALLBACK_LANGUAGE: QwenLanguage = "English"


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _qwen_language_from_name(language: str | None) -> QwenLanguage | None:
    if not language:
        return None

    normalized = language.strip().lower()
    for supported_language in SUPPORTED_QWEN_TTS_LANGUAGES:
        if supported_language.lower() == normalized:
            return supported_language
    return None


def _fallback_language() -> QwenLanguage:
    return (
        _qwen_language_from_name(os.getenv("VIVA_QWEN_TTS_FALLBACK_LANGUAGE"))
        or DEFAULT_FALLBACK_LANGUAGE
    )


@dataclass(frozen=True)
class TTSAudioResult:
    path: Path
    language: QwenLanguage
    voice: str
    sample_rate: int
    duration_seconds: float | None
    processing_time: float


def detect_tts_language(text: str) -> QwenLanguage:
    """
    Detect a reply language and return the Qwen3-TTS language parameter.
    """
    clean_text = text.strip()
    if not clean_text:
        return _fallback_language()

    if re.search(r"[\u3040-\u30ff]", clean_text):
        return "Japanese"
    if re.search(r"[\uac00-\ud7af]", clean_text):
        return "Korean"

    has_han_script = bool(re.search(r"[\u4e00-\u9fff]", clean_text))
    try:
        detected_language = detect(clean_text).lower()
    except lang_detect_exception.LangDetectException:
        return "Chinese" if has_han_script else _fallback_language()

    qwen_language = LANGDETECT_TO_QWEN_LANGUAGE.get(detected_language)
    if qwen_language:
        return qwen_language

    if has_han_script:
        return "Chinese"
    return _fallback_language()


def _chunk_text_for_tts(text: str, max_chars: int = 260) -> str:
    sentences = re.split(r"(?<=[.!?;:。！？；：])\s+", text.strip())
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
    if not words:
        return [
            sentence[index : index + max_chars]
            for index in range(0, len(sentence), max_chars)
        ]

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


def _speaker_env_key(language: QwenLanguage) -> str:
    return f"VIVA_QWEN_TTS_{language.upper()}_SPEAKER"


class VivaQwenTTSService:
    """
    Thread-safe lazy wrapper around MLX Qwen3-TTS generation.

    The backend generates audio files only; playback is owned by the Swift app.
    """

    def __init__(
        self,
        model_name: str | None = None,
        output_dir: str | Path | None = None,
        audio_format: str = "wav",
        max_age_seconds: int = 60 * 60,
    ) -> None:
        self.model_name = model_name or os.getenv("VIVA_QWEN_TTS_MODEL", DEFAULT_TTS_MODEL)
        self.output_dir = Path(
            output_dir or os.getenv("VIVA_TTS_OUTPUT_DIR", str(DEFAULT_OUTPUT_DIR))
        )
        self.audio_format = audio_format
        self.max_age_seconds = max_age_seconds
        self.temperature = _env_float("VIVA_QWEN_TTS_TEMPERATURE", 0.9)
        self.top_k = _env_int("VIVA_QWEN_TTS_TOP_K", 50)
        self.top_p = _env_float("VIVA_QWEN_TTS_TOP_P", 1.0)
        self.repetition_penalty = _env_float("VIVA_QWEN_TTS_REPETITION_PENALTY", 1.05)
        self.max_tokens = _env_int("VIVA_QWEN_TTS_MAX_TOKENS", 4096)
        self.instruct = DEFAULT_INSTRUCT
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
                logger.debug("Unable to remove old Qwen TTS file: %s", audio_path)

    def synthesize_to_file(
        self,
        text: str,
        output_path: str | Path | None = None,
    ) -> TTSAudioResult:
        clean_text = text.strip()
        if not clean_text:
            raise ValueError("Cannot synthesize empty text.")

        language = detect_tts_language(clean_text)
        tts_text = _chunk_text_for_tts(clean_text)
        audio_path = self._audio_path(output_path)

        start_time = time.time()
        with self._lock:
            model = self._load_model_locked()
            language = self._language_for_model_locked(model, language)
            speaker = self._speaker_for_language_locked(model, language)

            results = list(
                model.generate_custom_voice(
                    text=tts_text,
                    speaker=speaker,
                    language=language,
                    instruct=self.instruct,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                    top_k=self.top_k,
                    top_p=self.top_p,
                    repetition_penalty=self.repetition_penalty,
                    verbose=False,
                    stream=False,
                )
            )

            audio_chunks = [
                result.audio for result in results if result.audio is not None
            ]
            if not audio_chunks:
                raise RuntimeError("Qwen3-TTS did not generate audio.")

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
            "Qwen TTS audio generated. language=%s speaker=%s duration=%s "
            "processing_time=%.2fs path=%s",
            language,
            speaker,
            f"{duration_seconds:.2f}s" if duration_seconds is not None else "unknown",
            processing_time,
            audio_path,
        )

        return TTSAudioResult(
            path=audio_path,
            language=language,
            voice=speaker,
            sample_rate=sample_rate,
            duration_seconds=duration_seconds,
            processing_time=round(processing_time, 2),
        )

    def _audio_path(self, output_path: str | Path | None) -> Path:
        if output_path is None:
            return self.output_dir / f"{uuid.uuid4().hex}.{self.audio_format}"

        audio_path = Path(output_path)
        audio_path.parent.mkdir(parents=True, exist_ok=True)
        return audio_path

    def _speaker_for_language_locked(self, model, language: QwenLanguage) -> str:
        speaker = os.getenv(_speaker_env_key(language), DEFAULT_SPEAKER)
        supported_speakers = (
            model.get_supported_speakers()
            if hasattr(model, "get_supported_speakers")
            else []
        )
        if not supported_speakers:
            return speaker

        speaker_by_lower = {supported.lower(): supported for supported in supported_speakers}
        supported_speaker = speaker_by_lower.get(speaker.lower())
        if supported_speaker:
            return supported_speaker

        fallback_speaker = supported_speakers[0]
        logger.warning(
            "Qwen speaker '%s' is not supported by %s. Falling back to '%s'.",
            speaker,
            self.model_name,
            fallback_speaker,
        )
        return fallback_speaker

    def _language_for_model_locked(self, model, language: QwenLanguage) -> QwenLanguage:
        supported_languages = (
            model.get_supported_languages()
            if hasattr(model, "get_supported_languages")
            else []
        )
        if not supported_languages:
            return language

        supported_language_names = {supported.lower() for supported in supported_languages}
        if language.lower() in supported_language_names:
            return language

        fallback_language = _fallback_language()
        if fallback_language.lower() in supported_language_names:
            logger.warning(
                "Qwen language '%s' is not supported by %s. Falling back to '%s'.",
                language,
                self.model_name,
                fallback_language,
            )
            return fallback_language

        logger.warning(
            "Qwen language '%s' is not supported by %s. Using detected language anyway.",
            language,
            self.model_name,
        )
        return language

    def _load_model_locked(self):
        if self._model is None:
            logger.info("Loading Qwen TTS model '%s'...", self.model_name)
            self._model = load_tts_model(self.model_name)
            logger.info("Qwen TTS model loaded.")
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


VivaTTSService = VivaQwenTTSService


def synthesize_speech_to_file(
    text: str,
    output_dir: str | Path | None = None,
    output_path: str | Path | None = None,
) -> TTSAudioResult:
    return VivaQwenTTSService(output_dir=output_dir).synthesize_to_file(
        text,
        output_path=output_path,
    )


def read_this(text: str) -> Path:
    """
    Backward-compatible helper: generate audio and return the WAV path.
    """
    return synthesize_speech_to_file(text).path


def generate_expressive_speech() -> None:
    output_filename = Path("expressive_output.wav")
    result = synthesize_speech_to_file(
        "This is incredible! The new model running on Apple Silicon is blazing fast "
        "and sounds so realistic.",
        output_dir=Path.cwd(),
        output_path=output_filename,
    )

    if result.path != output_filename and result.path.exists():
        shutil.copyfile(result.path, output_filename)

    print(
        "Success! Audio saved to "
        f"{output_filename} with language={result.language} voice={result.voice}"
    )


if __name__ == "__main__":
    generate_expressive_speech()
