import os
import tempfile
import time
import logging
from contextlib import asynccontextmanager

import numpy as np
from fastapi import FastAPI, UploadFile, File
import uvicorn
import mlx_whisper

# --- 1. Setup Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

# Define the model repo (mlx-community/whisper-large-v3-mlx is the newest standard, 
# but keeping your requested name)
MODEL_REPO = "mlx-community/whisper-large-v3-mlx"

# --- 2. Startup Event (Model Pre-loading) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Server initializing. Pre-loading model '{MODEL_REPO}' into Apple Silicon unified memory...")
    start_time = time.time()
    
    # "Warm-up" run: Transcribing 1 second of silent audio forces MLX to 
    # download the model and load the computation graph into memory cache.
    dummy_audio = np.zeros(16000, dtype=np.float32)
    mlx_whisper.transcribe(dummy_audio, path_or_hf_repo=MODEL_REPO)
    
    logger.info(f"Model successfully loaded and cached in {time.time() - start_time:.2f} seconds.")
    logger.info("Server is ready to accept requests!")
    yield
    
    # Teardown logic (if any) goes here
    logger.info("Server shutting down.")

# Initialize FastAPI with the lifespan context
app = FastAPI(lifespan=lifespan)

@app.post("/viva")
async def viva(text: str, screenshot: str = None):
    logger.info(f"Received request for viva: {text}")

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
        output = mlx_whisper.transcribe(
            temp_audio_path,
            path_or_hf_repo=MODEL_REPO,
            verbose=True
        )
        
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
    uvicorn.run("speech_backend:app", host="127.0.0.1", port=8000, reload=True)
