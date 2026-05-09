from __future__ import annotations

import logging
import os
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

DEFAULT_TTS_MODEL = "prince-canuma/Kokoro-82M"

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
class KokoroTTSRequest:
    text: str
    language: str
    voice: str
    lang_code: str
    speed: float


class VivaTTSService:
    """
    Thread-safe lazy wrapper around mlx-audio Kokoro generation.

    The service can write complete audio files for script compatibility or yield
    raw float PCM chunks for low-latency playback in the macOS app.
    """

    engine_name = "kokoro"
    sample_rate = DEFAULT_SAMPLE_RATE

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

    def describe(self, text: str, voice_gender: str | None = None) -> TTSMetadata:
        request = self._prepare_request(text)
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
                logger.debug("Unable to remove old TTS file: %s", audio_path)

    def synthesize_to_file(
        self,
        text: str,
        output_path: str | Path | None = None,
        voice_gender: str | None = None,
    ) -> TTSAudioResult:
        request = self._prepare_request(text)
        audio_path = self._audio_path(output_path)

        start_time = time.time()
        with self._lock:
            model = self._load_model_locked()
            results = list(self._generate(model, request))
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
            "Kokoro TTS audio generated. language=%s voice=%s duration=%s "
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
        request = self._prepare_request(text)
        start_time = time.time()
        generated = False

        with self._lock:
            model = self._load_model_locked()
            for result in self._generate(model, request):
                if result.audio is None:
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
            raise RuntimeError("Kokoro did not generate audio.")

        logger.info(
            "Kokoro TTS stream completed. language=%s voice=%s processing_time=%.2fs",
            request.language,
            request.voice,
            time.time() - start_time,
        )

    def _prepare_request(self, text: str) -> KokoroTTSRequest:
        clean_text = text.strip()
        if not clean_text:
            raise ValueError("Cannot synthesize empty text.")

        language = detect_language(clean_text)
        normalized_text = normalize_text_for_tts(clean_text, language)
        if not normalized_text:
            raise ValueError("Cannot synthesize text after TTS normalization.")

        voice = KOKORO_VOICE_BY_LANGUAGE.get(
            language, KOKORO_VOICE_BY_LANGUAGE["other"]
        )
        lang_code = KOKORO_LANG_CODE_BY_LANGUAGE.get(
            language, KOKORO_LANG_CODE_BY_LANGUAGE["other"]
        )
        speed = KOKORO_SPEED_BY_LANGUAGE.get(
            language, KOKORO_SPEED_BY_LANGUAGE["other"]
        )

        return KokoroTTSRequest(
            text=chunk_text_for_tts(normalized_text, max_chars=220),
            language=language,
            voice=voice,
            lang_code=lang_code,
            speed=speed,
        )

    def _generate(self, model, request: KokoroTTSRequest):
        return model.generate(
            text=request.text,
            voice=request.voice,
            speed=request.speed,
            lang_code=request.lang_code,
        )

    def _audio_path(self, output_path: str | Path | None) -> Path:
        if output_path is None:
            return self.output_dir / f"{uuid.uuid4().hex}.{self.audio_format}"

        audio_path = Path(output_path)
        audio_path.parent.mkdir(parents=True, exist_ok=True)
        return audio_path

    def _load_model_locked(self):
        if self._model is None:
            logger.info("Loading Kokoro TTS model '%s'...", self.model_name)
            self._model = load_tts_model(self.model_name)
            logger.info("Kokoro TTS model loaded.")
        return self._model


def synthesize_speech_to_file(
    text: str,
    output_dir: str | Path | None = None,
    output_path: str | Path | None = None,
    voice_gender: str | None = None,
) -> TTSAudioResult:
    return VivaTTSService(output_dir=output_dir).synthesize_to_file(
        text,
        output_path=output_path,
        voice_gender=voice_gender,
    )


def read_this(text: str) -> Path:
    """
    Backward-compatible helper: generate audio and return the WAV path.
    """
    return synthesize_speech_to_file(text).path


if __name__ == "__main__":
    result = synthesize_speech_to_file("Hello, I am Viva. This is an audio test.")
    print(result.path)
