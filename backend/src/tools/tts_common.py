from __future__ import annotations

import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import mlx.core as mx
import numpy as np
from mlx_audio.audio_io import write as audio_write

DEFAULT_OUTPUT_DIR = Path(tempfile.gettempdir()) / "viva_tts_audio"
PCM_STREAM_CONTENT_TYPE = "application/vnd.viva.pcm-f32"
DEFAULT_SAMPLE_RATE = 24_000


@dataclass(frozen=True)
class TTSAudioResult:
    path: Path
    language: str
    voice: str
    sample_rate: int
    duration_seconds: float | None
    processing_time: float


@dataclass(frozen=True)
class TTSAudioChunk:
    data: bytes
    sample_rate: int
    segment_index: int
    is_final: bool = False


@dataclass(frozen=True)
class TTSMetadata:
    engine: str
    language: str
    voice: str
    sample_rate: int


def chunk_text_for_tts(
    text: str,
    max_chars: int,
    sentence_pattern: str = r"(?<=[.!?;:])\s+",
) -> str:
    sentences = re.split(sentence_pattern, text.strip())
    chunks: list[str] = []
    current = ""

    for sentence in sentences:
        if not sentence:
            continue

        if len(sentence) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(split_long_sentence(sentence, max_chars))
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


def split_long_sentence(sentence: str, max_chars: int) -> list[str]:
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


def generated_audio_chunks(results: Iterable) -> list:
    return [result.audio for result in results if result.audio is not None]


def concatenate_audio(audio_chunks: list):
    if not audio_chunks:
        raise RuntimeError("TTS did not generate audio.")
    return (
        mx.concatenate(audio_chunks, axis=0)
        if len(audio_chunks) > 1
        else audio_chunks[0]
    )


def write_audio_file(path: Path, audio, sample_rate: int, audio_format: str) -> None:
    audio_write(str(path), audio, sample_rate, format=audio_format)


def duration_seconds(results: Iterable) -> float | None:
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


def audio_to_pcm_f32_bytes(audio) -> bytes:
    pcm = np.array(audio, dtype=np.float32).reshape(-1)
    pcm = np.ascontiguousarray(pcm, dtype="<f4")
    return pcm.tobytes()
