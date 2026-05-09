import asyncio
import logging
import os
import tempfile
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import mlx_whisper
import numpy as np
import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from langchain_agent import VivaAgentService
from tools.tts_common import PCM_STREAM_CONTENT_TYPE
from tools.tts_factory import DEFAULT_OUTPUT_DIR, create_tts_service

# --- 1. Setup Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

MODEL_REPO = "mlx-community/whisper-large-v3-mlx"
NATIVE_AUDIO_PROMPT = "Respond to the user request."
TTS_OUTPUT_DIR = Path(os.getenv("VIVA_TTS_OUTPUT_DIR", str(DEFAULT_OUTPUT_DIR)))
TTS_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
TTS_STREAM_MAX_AGE_SECONDS = 5 * 60
DEFAULT_TTS_VOICE_GENDER = os.getenv("VIVA_TTS_VOICE_GENDER", "female")
SUPPORTED_TTS_VOICE_GENDERS = {"male", "female"}
_END_OF_STREAM = object()


@dataclass(frozen=True)
class PendingTTSStream:
    text: str
    voice_gender: str | None
    created_at: float


def _warm_up_whisper_model() -> None:
    dummy_audio = np.zeros(16000, dtype=np.float32)
    mlx_whisper.transcribe(dummy_audio, path_or_hf_repo=MODEL_REPO)


def _transcribe_audio_file(temp_audio_path: str) -> dict:
    return mlx_whisper.transcribe(
        temp_audio_path,
        path_or_hf_repo=MODEL_REPO,
        verbose=True,
    )


def _normalize_tts_voice_gender(voice_gender: str | None) -> str:
    normalized = (voice_gender or DEFAULT_TTS_VOICE_GENDER).strip().lower()
    if normalized not in SUPPORTED_TTS_VOICE_GENDERS:
        supported = ", ".join(sorted(SUPPORTED_TTS_VOICE_GENDERS))
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported TTS voice gender '{voice_gender}'. Use one of: {supported}.",
        )
    return normalized


def _next_tts_chunk(chunk_iterator: Iterator):
    try:
        return next(chunk_iterator)
    except StopIteration:
        return _END_OF_STREAM


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
    app.state.tts_service = create_tts_service(output_dir=TTS_OUTPUT_DIR)
    app.state.tts_executor = ThreadPoolExecutor(
        max_workers=1,
        thread_name_prefix="viva-tts",
    )
    app.state.active_viva_tasks = {}
    app.state.active_viva_task_lock = asyncio.Lock()
    app.state.pending_tts_streams = {}
    app.state.pending_tts_stream_lock = asyncio.Lock()

    if os.getenv("VIVA_TTS_WARMUP", "1") == "1":
        logger.info("Pre-loading TTS model into memory...")
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(app.state.tts_executor, app.state.tts_service.warm_up)

    logger.info(
        f"Model successfully loaded and cached in {time.time() - start_time:.2f} seconds."
    )
    logger.info("Server is ready to accept requests!")
    yield

    logger.info("Server shutting down.")
    app.state.tts_executor.shutdown(wait=False, cancel_futures=True)


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


def _absolute_url(request: Request, path: str) -> str:
    return str(request.base_url).rstrip("/") + path


async def _store_tts_stream(
    request: Request,
    request_id: str,
    text: str,
    voice_gender: str | None,
) -> None:
    now = time.time()
    async with request.app.state.pending_tts_stream_lock:
        stale_request_ids = [
            stream_request_id
            for stream_request_id, pending in request.app.state.pending_tts_streams.items()
            if now - pending.created_at > TTS_STREAM_MAX_AGE_SECONDS
        ]
        for stream_request_id in stale_request_ids:
            del request.app.state.pending_tts_streams[stream_request_id]

        request.app.state.pending_tts_streams[request_id] = PendingTTSStream(
            text=text,
            voice_gender=voice_gender,
            created_at=now,
        )


async def _pop_tts_stream(request: Request, request_id: str) -> PendingTTSStream | None:
    async with request.app.state.pending_tts_stream_lock:
        pending = request.app.state.pending_tts_streams.pop(request_id, None)

    if pending is None:
        return None
    if time.time() - pending.created_at > TTS_STREAM_MAX_AGE_SECONDS:
        return None
    return pending


async def _run_viva_request(
    request: Request,
    text: str,
    request_id: str | None,
    tts_enabled: bool,
    tts_voice_gender: str | None,
    screenshot: UploadFile | None = None,
    audio: UploadFile | None = None,
) -> dict[str, object]:
    clean_text = text.strip()
    if not clean_text:
        raise HTTPException(status_code=400, detail="The 'text' field is required.")

    viva_request_id = (request_id or str(uuid.uuid4())).strip()
    if not viva_request_id:
        raise HTTPException(
            status_code=400, detail="The 'request_id' field cannot be empty."
        )
    clean_tts_voice_gender = _normalize_tts_voice_gender(tts_voice_gender)

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

    audio_bytes: bytes | None = None
    if audio is not None:
        audio_bytes = await audio.read()
        if not audio_bytes:
            await _clear_active_viva_task(request, viva_request_id, current_task)
            raise HTTPException(status_code=400, detail="The audio file is empty.")

    logger.info(
        "Received Viva request. request_id=%s text_length=%s screenshot=%s native_audio=%s",
        viva_request_id,
        len(clean_text),
        bool(screenshot_bytes),
        bool(audio_bytes),
    )

    start_time = time.time()
    try:
        response_text = await request.app.state.viva_service.run(
            text=clean_text,
            screenshot_bytes=screenshot_bytes,
            screenshot_content_type=screenshot.content_type if screenshot else None,
            screenshot_filename=screenshot.filename if screenshot else None,
            audio_bytes=audio_bytes,
            audio_content_type=audio.content_type if audio else None,
            audio_filename=audio.filename if audio else None,
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
        if tts_enabled:
            tts_metadata = await asyncio.to_thread(
                request.app.state.tts_service.describe,
                response_text,
                clean_tts_voice_gender,
            )
            if current_task is not None and current_task.cancelling():
                raise asyncio.CancelledError

            await _store_tts_stream(
                request,
                viva_request_id,
                response_text,
                clean_tts_voice_gender,
            )
            audio_payload.update(
                {
                    "audio_url": _absolute_url(
                        request,
                        f"/viva/tts-stream/{viva_request_id}",
                    ),
                    "audio_content_type": PCM_STREAM_CONTENT_TYPE,
                    "tts_language": tts_metadata.language,
                    "tts_voice": tts_metadata.voice,
                }
            )
        else:
            logger.info("TTS generation skipped. request_id=%s", viva_request_id)
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


@app.post("/viva")
async def viva(
    request: Request,
    text: str = Form(...),
    request_id: str | None = Form(default=None),
    tts_enabled: bool = Form(default=True),
    tts_voice_gender: str | None = Form(default=DEFAULT_TTS_VOICE_GENDER),
    screenshot: UploadFile | None = File(default=None),
):
    return await _run_viva_request(
        request=request,
        text=text,
        request_id=request_id,
        tts_enabled=tts_enabled,
        tts_voice_gender=tts_voice_gender,
        screenshot=screenshot,
    )


@app.post("/viva/native-audio")
async def viva_native_audio(
    request: Request,
    file: UploadFile = File(...),
    text: str = Form(default=NATIVE_AUDIO_PROMPT),
    request_id: str | None = Form(default=None),
    tts_enabled: bool = Form(default=True),
    tts_voice_gender: str | None = Form(default=DEFAULT_TTS_VOICE_GENDER),
    screenshot: UploadFile | None = File(default=None),
):
    return await _run_viva_request(
        request=request,
        text=text,
        request_id=request_id,
        tts_enabled=tts_enabled,
        tts_voice_gender=tts_voice_gender,
        screenshot=screenshot,
        audio=file,
    )


@app.get("/viva/tts-stream/{request_id}")
async def viva_tts_stream(request: Request, request_id: str):
    pending = await _pop_tts_stream(request, request_id)
    if pending is None:
        raise HTTPException(status_code=404, detail="No pending TTS stream found.")

    tts_service = request.app.state.tts_service

    async def audio_iterator():
        chunk_iterator = tts_service.stream_pcm(
            pending.text,
            pending.voice_gender,
        )
        loop = asyncio.get_running_loop()
        try:
            while True:
                chunk = await loop.run_in_executor(
                    request.app.state.tts_executor,
                    _next_tts_chunk,
                    chunk_iterator,
                )
                if chunk is _END_OF_STREAM:
                    break
                if chunk.data:
                    yield chunk.data
        except asyncio.CancelledError:
            logger.info("TTS stream closed by client. request_id=%s", request_id)
            raise
        except Exception as exc:
            logger.exception("TTS stream failed. request_id=%s error=%s", request_id, exc)
        finally:
            await loop.run_in_executor(
                request.app.state.tts_executor,
                chunk_iterator.close,
            )

    headers = {
        "Cache-Control": "no-store",
        "X-Audio-Sample-Rate": str(tts_service.sample_rate),
        "X-Audio-Channels": "1",
        "X-Audio-Sample-Format": "f32le",
    }
    return StreamingResponse(
        audio_iterator(),
        media_type=PCM_STREAM_CONTENT_TYPE,
        headers=headers,
    )


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
