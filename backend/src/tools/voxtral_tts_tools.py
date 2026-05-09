from __future__ import annotations

import logging
import os
import re
import shutil
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import mlx.core as mx
from mlx_audio.tts.utils import load as load_tts_model

from tools.language_tools import detect_language, normalize_text_for_tts
from tools.tts_common import (
    DEFAULT_OUTPUT_DIR,
    DEFAULT_SAMPLE_RATE,
    TTSAudioChunk,
    TTSAudioResult,
    TTSMetadata,
    audio_to_pcm_f32_bytes,
    chunk_text_for_tts,
    concatenate_audio,
    duration_seconds,
    generated_audio_chunks,
    write_audio_file,
)

logger = logging.getLogger(__name__)

DEFAULT_TTS_MODEL = "mlx-community/Voxtral-4B-TTS-2603-mlx-4bit"
DEFAULT_FALLBACK_LANGUAGE = "en"
DEFAULT_VOICE_GENDER = "female"
SUPPORTED_VOXTRAL_LANGUAGES = {"en", "fr", "es", "de", "it", "pt", "nl", "ar", "hi"}
VOXTRAL_LANGUAGE_HINT_PATTERNS = (
    ("ar", re.compile(r"[\u0600-\u06ff]")),
    ("hi", re.compile(r"[\u0900-\u097f]")),
    (
        "it",
        re.compile(
            r"\b(ciao|grazie|prego|sono|questo|questa|italiano|italiana|buongiorno|buonasera|perche|perché)\b|[àèéìòù]",
            re.IGNORECASE,
        ),
    ),
    (
        "en",
        re.compile(
            r"\b(hello|hi|thanks|please|the|this|that|from|with|your|you|i'm|i am)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "fr",
        re.compile(
            r"\b(bonjour|merci|français|francaise|avec|vous)\b|[âçêëîïûüÿ]",
            re.IGNORECASE,
        ),
    ),
    (
        "es",
        re.compile(
            r"\b(hola|gracias|español|buenos|buenas|usted)\b|[¿¡ñ]",
            re.IGNORECASE,
        ),
    ),
    (
        "de",
        re.compile(
            r"\b(danke|bitte|deutsch|guten|ich)\b|[äöüß]",
            re.IGNORECASE,
        ),
    ),
    (
        "pt",
        re.compile(
            r"\b(olá|ola|obrigado|obrigada|português|portuguesa)\b|[ãõ]",
            re.IGNORECASE,
        ),
    ),
    (
        "nl",
        re.compile(r"\b(nederlands|alsjeblieft|bedankt)\b", re.IGNORECASE),
    ),
)

VOXTRAL_VOICE_BY_LANGUAGE_AND_GENDER = {
    "en": {"male": "casual_male", "female": "casual_female"},
    "fr": {"male": "fr_male", "female": "fr_female"},
    "es": {"male": "es_male", "female": "es_female"},
    "de": {"male": "de_male", "female": "de_female"},
    "it": {"male": "it_male", "female": "it_female"},
    "pt": {"male": "pt_male", "female": "pt_female"},
    "nl": {"male": "nl_male", "female": "nl_female"},
    "ar": {"male": "ar_male", "female": "ar_male"},
    "hi": {"male": "hi_male", "female": "hi_female"},
    "other": {"male": "neutral_male", "female": "neutral_female"},
}


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


def _normalize_voice_gender(voice_gender: str | None) -> str:
    normalized = (
        voice_gender or os.getenv("VIVA_TTS_VOICE_GENDER") or DEFAULT_VOICE_GENDER
    ).strip().lower()
    if normalized not in {"male", "female"}:
        logger.warning(
            "Unsupported Voxtral voice gender '%s'. Falling back to '%s'.",
            voice_gender,
            DEFAULT_VOICE_GENDER,
        )
        return DEFAULT_VOICE_GENDER
    return normalized


def _voice_for_language(language: str, voice_gender: str) -> str:
    voices_by_gender = VOXTRAL_VOICE_BY_LANGUAGE_AND_GENDER.get(
        language,
        VOXTRAL_VOICE_BY_LANGUAGE_AND_GENDER["other"],
    )
    return voices_by_gender.get(
        voice_gender,
        VOXTRAL_VOICE_BY_LANGUAGE_AND_GENDER["other"][voice_gender],
    )


def _detect_voxtral_language(text: str) -> str:
    for language, pattern in VOXTRAL_LANGUAGE_HINT_PATTERNS:
        if pattern.search(text):
            return language

    language = detect_language(text, fallback=DEFAULT_FALLBACK_LANGUAGE).lower()
    if language in SUPPORTED_VOXTRAL_LANGUAGES:
        return language

    if re.search(r"[A-Za-z]", text) and not re.search(
        r"[\u0600-\u06ff\u0900-\u097f]",
        text,
    ):
        return DEFAULT_FALLBACK_LANGUAGE

    return "other"


@dataclass(frozen=True)
class VoxtralTTSRequest:
    text: str
    language: str
    voice: str
    voice_gender: str


class VivaVoxtralTTSService:
    """
    Thread-safe lazy wrapper around MLX-Audio Voxtral 4B TTS generation.

    The public helpers intentionally match tts_tools.py so either service can be
    selected by the backend without changing callers.
    """

    engine_name = "voxtral"
    sample_rate = DEFAULT_SAMPLE_RATE

    def __init__(
        self,
        model_name: str | None = None,
        output_dir: str | Path | None = None,
        audio_format: str = "wav",
        max_age_seconds: int = 60 * 60,
    ) -> None:
        self.model_name = model_name or os.getenv(
            "VIVA_VOXTRAL_TTS_MODEL", DEFAULT_TTS_MODEL
        )
        self.output_dir = Path(
            output_dir or os.getenv("VIVA_TTS_OUTPUT_DIR", str(DEFAULT_OUTPUT_DIR))
        )
        self.audio_format = audio_format
        self.max_age_seconds = max_age_seconds
        self.temperature = _env_float("VIVA_VOXTRAL_TTS_TEMPERATURE", 0.8)
        self.top_k = _env_int("VIVA_VOXTRAL_TTS_TOP_K", 50)
        self.top_p = _env_float("VIVA_VOXTRAL_TTS_TOP_P", 0.95)
        self.max_tokens = _env_int("VIVA_VOXTRAL_TTS_MAX_TOKENS", 4096)
        self.streaming_interval = _env_float(
            "VIVA_VOXTRAL_TTS_STREAMING_INTERVAL", 0.8
        )
        self._model = None
        self._lock = threading.Lock()

        self.output_dir.mkdir(parents=True, exist_ok=True)

    @property
    def output_directory(self) -> Path:
        return self.output_dir

    def describe(self, text: str, voice_gender: str | None = None) -> TTSMetadata:
        request = self._prepare_request(text, voice_gender)
        return TTSMetadata(
            engine=self.engine_name,
            language=request.language,
            voice=request.voice,
            sample_rate=self.sample_rate,
        )

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
                logger.debug("Unable to remove old Voxtral TTS file: %s", audio_path)

    def synthesize_to_file(
        self,
        text: str,
        output_path: str | Path | None = None,
        voice_gender: str | None = None,
    ) -> TTSAudioResult:
        request = self._prepare_request(text, voice_gender)
        audio_path = self._audio_path(output_path)

        start_time = time.time()
        with self._lock:
            model = self._load_model_locked()
            results = list(self._generate(model, request, stream=False))
            audio_chunks = generated_audio_chunks(results)
            sample_rate = results[0].sample_rate
            audio = concatenate_audio(audio_chunks)
            write_audio_file(audio_path, audio, sample_rate, self.audio_format)
            mx.clear_cache()

        if not audio_path.exists() or audio_path.stat().st_size == 0:
            raise RuntimeError(f"TTS audio file was not created: {audio_path}")

        audio_duration = duration_seconds(results)
        processing_time = time.time() - start_time
        self.cleanup_old_files()

        logger.info(
            "Voxtral TTS audio generated. language=%s voice=%s duration=%s "
            "processing_time=%.2fs path=%s",
            request.language,
            request.voice,
            f"{audio_duration:.2f}s" if audio_duration is not None else "unknown",
            processing_time,
            audio_path,
        )

        return TTSAudioResult(
            path=audio_path,
            language=request.language,
            voice=request.voice,
            sample_rate=sample_rate,
            duration_seconds=audio_duration,
            processing_time=round(processing_time, 2),
        )

    def stream_pcm(
        self,
        text: str,
        voice_gender: str | None = None,
    ) -> Iterator[TTSAudioChunk]:
        request = self._prepare_request(text, voice_gender)
        start_time = time.time()
        generated = False

        with self._lock:
            model = self._load_model_locked()
            for result in self._generate(model, request, stream=True):
                if result.audio is None or result.audio.shape[0] == 0:
                    continue
                generated = True
                yield TTSAudioChunk(
                    data=audio_to_pcm_f32_bytes(result.audio),
                    sample_rate=result.sample_rate,
                    segment_index=result.segment_idx,
                    is_final=getattr(result, "is_final_chunk", False),
                )
                mx.clear_cache()

        if not generated:
            raise RuntimeError("Voxtral did not generate audio.")

        logger.info(
            "Voxtral TTS stream completed. language=%s voice=%s processing_time=%.2fs",
            request.language,
            request.voice,
            time.time() - start_time,
        )

    def _prepare_request(
        self,
        text: str,
        voice_gender: str | None = None,
    ) -> VoxtralTTSRequest:
        clean_text = text.strip()
        if not clean_text:
            raise ValueError("Cannot synthesize empty text.")

        language = _detect_voxtral_language(clean_text)
        normalized_text = normalize_text_for_tts(clean_text, language)
        if not normalized_text:
            raise ValueError("Cannot synthesize text after TTS normalization.")

        clean_voice_gender = _normalize_voice_gender(voice_gender)
        voice = _voice_for_language(language, clean_voice_gender)

        return VoxtralTTSRequest(
            text=chunk_text_for_tts(
                normalized_text,
                max_chars=360,
                sentence_pattern=r"(?<=[.!?;:。！？；：])\s+",
            ),
            language=language,
            voice=voice,
            voice_gender=clean_voice_gender,
        )

    def _generate(self, model, request: VoxtralTTSRequest, stream: bool):
        return model.generate(
            text=request.text,
            voice=request.voice,
            temperature=self.temperature,
            top_k=self.top_k,
            top_p=self.top_p,
            max_tokens=self.max_tokens,
            verbose=False,
            stream=stream,
            streaming_interval=self.streaming_interval,
        )

    def _audio_path(self, output_path: str | Path | None) -> Path:
        if output_path is None:
            return self.output_dir / f"{uuid.uuid4().hex}.{self.audio_format}"

        audio_path = Path(output_path)
        audio_path.parent.mkdir(parents=True, exist_ok=True)
        return audio_path

    def _load_model_locked(self):
        if self._model is None:
            logger.info("Loading Voxtral TTS model '%s'...", self.model_name)
            self._model = load_tts_model(self.model_name)
            logger.info("Voxtral TTS model loaded.")
        return self._model


VivaTTSService = VivaVoxtralTTSService


def synthesize_speech_to_file(
    text: str,
    output_dir: str | Path | None = None,
    output_path: str | Path | None = None,
    voice_gender: str | None = None,
) -> TTSAudioResult:
    return VivaVoxtralTTSService(output_dir=output_dir).synthesize_to_file(
        text,
        output_path=output_path,
        voice_gender=voice_gender,
    )


def read_this(text: str) -> Path:
    """
    Backward-compatible helper: generate audio and return the WAV path.
    """
    return synthesize_speech_to_file(text).path


def generate_expressive_speech() -> None:
    output_filename = Path("voxtral_output.wav")
    result = synthesize_speech_to_file(
        "This is Voxtral 4B running locally with MLX Audio acceleration.",
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
