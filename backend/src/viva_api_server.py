import asyncio
import logging
import os
import tempfile
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import mlx_whisper
import numpy as np
import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.staticfiles import StaticFiles

from langchain_agent import VivaAgentService
from tools.tts_tools import DEFAULT_OUTPUT_DIR, VivaTTSService

# --- 1. Setup Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

MODEL_REPO = "mlx-community/whisper-large-v3-mlx"
TTS_OUTPUT_DIR = Path(os.getenv("VIVA_TTS_OUTPUT_DIR", str(DEFAULT_OUTPUT_DIR)))
TTS_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _warm_up_whisper_model() -> None:
    dummy_audio = np.zeros(16000, dtype=np.float32)
    mlx_whisper.transcribe(dummy_audio, path_or_hf_repo=MODEL_REPO)


def _transcribe_audio_file(temp_audio_path: str) -> dict:
    return mlx_whisper.transcribe(
        temp_audio_path,
        path_or_hf_repo=MODEL_REPO,
        verbose=True,
    )


# --- 2. Startup Event (Model Pre-loading) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        f"Server initializing. Pre-loading model '{MODEL_REPO}' into Apple Silicon unified memory..."
    )
    start_time = time.time()

    # Warm up Whisper off the event loop and initialize the LangChain agent once.
    await asyncio.to_thread(_warm_up_whisper_model)
    app.state.viva_service = VivaAgentService()
    await app.state.viva_service.initialize()
    app.state.tts_service = VivaTTSService(output_dir=TTS_OUTPUT_DIR)
    app.state.active_viva_tasks = {}
    app.state.active_viva_task_lock = asyncio.Lock()

    if os.getenv("VIVA_TTS_WARMUP", "0") == "1":
        logger.info("Pre-loading TTS model into memory...")
        await asyncio.to_thread(app.state.tts_service.warm_up)

    logger.info(
        f"Model successfully loaded and cached in {time.time() - start_time:.2f} seconds."
    )
    logger.info("Server is ready to accept requests!")
    yield

    logger.info("Server shutting down.")


# Initialize FastAPI with the lifespan context
app = FastAPI(lifespan=lifespan)
app.mount(
    "/generated-audio",
    StaticFiles(directory=str(TTS_OUTPUT_DIR)),
    name="generated-audio",
)


async def _clear_active_viva_task(
    request: Request,
    request_id: str,
    task: asyncio.Task | None,
) -> None:
    async with request.app.state.active_viva_task_lock:
        if request.app.state.active_viva_tasks.get(request_id) is task:
            del request.app.state.active_viva_tasks[request_id]


@app.post("/viva")
async def viva(
    request: Request,
    text: str = Form(...),
    request_id: str | None = Form(default=None),
    screenshot: UploadFile | None = File(default=None),
):
    clean_text = text.strip()
    if not clean_text:
        raise HTTPException(status_code=400, detail="The 'text' field is required.")

    viva_request_id = (request_id or str(uuid.uuid4())).strip()
    if not viva_request_id:
        raise HTTPException(
            status_code=400, detail="The 'request_id' field cannot be empty."
        )

    current_task = asyncio.current_task()
    async with request.app.state.active_viva_task_lock:
        if viva_request_id in request.app.state.active_viva_tasks:
            raise HTTPException(
                status_code=409, detail="A Viva request with this id is already active."
            )
        request.app.state.active_viva_tasks[viva_request_id] = current_task

    screenshot_bytes: bytes | None = None
    if screenshot is not None:
        screenshot_bytes = await screenshot.read()

    logger.info(
        "Received Viva request. request_id=%s text_length=%s screenshot=%s",
        viva_request_id,
        len(clean_text),
        bool(screenshot_bytes),
    )

    start_time = time.time()
    try:
        response_text = await request.app.state.viva_service.run(
            text=clean_text,
            screenshot_bytes=screenshot_bytes,
            screenshot_content_type=screenshot.content_type if screenshot else None,
            screenshot_filename=screenshot.filename if screenshot else None,
        )
        if current_task is not None and current_task.cancelling():
            raise asyncio.CancelledError
    except asyncio.CancelledError as exc:
        await _clear_active_viva_task(request, viva_request_id, current_task)
        logger.info("Viva request cancelled. request_id=%s", viva_request_id)
        raise HTTPException(status_code=499, detail="Viva request cancelled.") from exc
    except Exception as exc:
        await _clear_active_viva_task(request, viva_request_id, current_task)
        logger.exception("Viva request failed: %s", exc)
        raise HTTPException(
            status_code=500, detail="Viva backend request failed."
        ) from exc

    process_duration = time.time() - start_time
    logger.info("Viva response text generated in %.2f seconds.", process_duration)

    audio_payload: dict[str, object] = {
        "audio_url": None,
        "audio_content_type": None,
        "tts_language": None,
        "tts_voice": None,
        "tts_processing_time": None,
        "tts_error": None,
    }

    try:
        tts_result = await asyncio.to_thread(
            request.app.state.tts_service.synthesize_to_file,
            response_text,
        )
        if current_task is not None and current_task.cancelling():
            raise asyncio.CancelledError
        audio_payload.update(
            {
                "audio_url": (
                    str(request.base_url).rstrip("/")
                    + f"/generated-audio/{tts_result.path.name}"
                ),
                "audio_content_type": "audio/wav",
                "tts_language": tts_result.language,
                "tts_voice": tts_result.voice,
                "tts_processing_time": tts_result.processing_time,
            }
        )
    except asyncio.CancelledError as exc:
        logger.info("Viva request cancelled during TTS. request_id=%s", viva_request_id)
        raise HTTPException(status_code=499, detail="Viva request cancelled.") from exc
    except Exception as exc:
        logger.exception("TTS generation failed: %s", exc)
        audio_payload["tts_error"] = "TTS generation failed."
    finally:
        await _clear_active_viva_task(request, viva_request_id, current_task)

    total_duration = time.time() - start_time
    logger.info("Viva request completed in %.2f seconds.", total_duration)
    return {
        "text": response_text,
        "processing_time": round(process_duration, 2),
        "used_screenshot": bool(screenshot_bytes),
        **audio_payload,
    }


@app.post("/viva/cancel/{request_id}")
async def cancel_viva(request: Request, request_id: str):
    async with request.app.state.active_viva_task_lock:
        task = request.app.state.active_viva_tasks.get(request_id)

    if task is None or task.done():
        return {
            "request_id": request_id,
            "cancelled": False,
            "detail": "No active Viva request found for this id.",
        }

    task.cancel()
    logger.info("Viva cancellation requested. request_id=%s", request_id)
    return {
        "request_id": request_id,
        "cancelled": True,
    }


@app.post("/transcribe")
async def transcribe(file: UploadFile = File(...)):
    logger.info(f"Received new audio file: {file.filename}")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_audio:
        temp_audio.write(await file.read())
        temp_audio_path = temp_audio.name

    try:
        logger.info("Starting Whisper inference...")
        start_time = time.time()

        # --- 3. Verbose Inference & Language Detection ---
        # verbose=True forces whisper to log chunk processing
        # Language is automatically detected by Whisper if not specified
        output = await asyncio.to_thread(_transcribe_audio_file, temp_audio_path)

        process_duration = time.time() - start_time

        # Extract metadata
        text = output.get("text", "").strip()
        language = output.get("language", "unknown")

        # Log the performance and metadata
        logger.info(f"Inference completed in {process_duration:.2f} seconds.")
        logger.info(f"Auto-detected Language: {language}")
        logger.info(f"Transcribed Text: {text}")

        # We also return the language and processing time to the frontend API payload
        # just in case you want to display it in SwiftUI later!
        return {
            "text": text,
            "language": language,
            "processing_time": round(process_duration, 2),
        }
    finally:
        if os.path.exists(temp_audio_path):
            os.remove(temp_audio_path)


if __name__ == "__main__":
    # Standard Uvicorn startup
    uvicorn.run("viva_api_server:app", host="127.0.0.1", port=8000, reload=True)
