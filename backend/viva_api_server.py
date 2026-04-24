import asyncio
import logging
import os
import tempfile
import time
from contextlib import asynccontextmanager

import mlx_whisper
import numpy as np
import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile

from langchain_agent import PuroLangService

# --- 1. Setup Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

MODEL_REPO = "mlx-community/whisper-large-v3-mlx"

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
    logger.info(f"Server initializing. Pre-loading model '{MODEL_REPO}' into Apple Silicon unified memory...")
    start_time = time.time()

    # Warm up Whisper off the event loop and initialize the LangChain agent once.
    await asyncio.to_thread(_warm_up_whisper_model)
    app.state.viva_service = PuroLangService()
    await app.state.viva_service.initialize()

    logger.info(f"Model successfully loaded and cached in {time.time() - start_time:.2f} seconds.")
    logger.info("Server is ready to accept requests!")
    yield

    logger.info("Server shutting down.")

# Initialize FastAPI with the lifespan context
app = FastAPI(lifespan=lifespan)

@app.post("/viva")
async def viva(
    request: Request,
    text: str = Form(...),
    screenshot: UploadFile | None = File(default=None),
):
    clean_text = text.strip()
    if not clean_text:
        raise HTTPException(status_code=400, detail="The 'text' field is required.")

    screenshot_bytes: bytes | None = None
    if screenshot is not None:
        screenshot_bytes = await screenshot.read()

    logger.info(
        "Received Viva request. text_length=%s screenshot=%s",
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
    except Exception as exc:
        logger.exception("Viva request failed: %s", exc)
        raise HTTPException(status_code=500, detail="Viva backend request failed.") from exc

    process_duration = time.time() - start_time
    logger.info("Viva response generated in %.2f seconds.", process_duration)
    return {
        "text": response_text,
        "processing_time": round(process_duration, 2),
        "used_screenshot": bool(screenshot_bytes),
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
            "processing_time": round(process_duration, 2)
        }
    finally:
        if os.path.exists(temp_audio_path):
            os.remove(temp_audio_path)

if __name__ == "__main__":
    # Standard Uvicorn startup
    uvicorn.run("viva_api_server:app", host="127.0.0.1", port=8000, reload=True)
