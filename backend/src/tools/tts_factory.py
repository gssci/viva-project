from __future__ import annotations

import os
from pathlib import Path

from tools.tts_common import DEFAULT_OUTPUT_DIR
from tools.tts_tools import VivaTTSService as VivaKokoroTTSService
from tools.voxtral_tts_tools import VivaVoxtralTTSService

TTS_ENGINE_ENV = "VIVA_TTS_ENGINE"


def create_tts_service(output_dir: str | Path | None = None):
    engine = os.getenv(TTS_ENGINE_ENV, "kokoro").strip().lower()

    if engine in {"kokoro", "kokoro-82m"}:
        return VivaKokoroTTSService(output_dir=output_dir)
    if engine in {"voxtral", "voxtral-4b", "voxtral_tts"}:
        return VivaVoxtralTTSService(output_dir=output_dir)

    supported_engines = "kokoro, voxtral"
    raise ValueError(
        f"Unsupported {TTS_ENGINE_ENV} value '{engine}'. "
        f"Supported values: {supported_engines}."
    )


__all__ = ["DEFAULT_OUTPUT_DIR", "create_tts_service"]
