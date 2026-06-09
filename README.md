# Viva — Private On-Device AI Assistant for macOS

A macOS menubar AI assistant that runs entirely on-device. No cloud APIs, no data leaves your Mac.

## Overview

Viva provides a voice-first, private alternative to Siri on Apple Silicon Macs. Powered by local models via MLX and an LM Studio OpenAI-compatible server, it handles voice input, natural language understanding, and spoken responses — all with zero external dependencies.

**Key capabilities:**
- Voice transcription via MLX Whisper Large v3 (auto language detection)
- LLM agent via LM Studio with in-process conversation history
- Streaming text-to-speech (Kokoro or Voxtral 4B via MLX Audio)
- 50+ macOS automation tools: system controls, Calendar, Reminders, Messages, Mail, Finder, Music, Safari, clipboard, and more
- Web search (DuckDuckGo), weather (Open-Meteo), and webpage extraction
- Optional screenshot context for visual queries
- Dual-mode: text input or native audio (send raw audio directly to multimodal LLM)

## Architecture

```
┌─────────────────────────────────────┐
│         macOS App (SwiftUI)         │
│  Menubar icon  │  Floating panel   │
│  Audio recorder│  Screenshot       │
│  TTS player    │  API client       │
└────────┬────────────────────────────┘
         │  HTTP  (localhost:8001)
         ▼
┌─────────────────────────────────────┐
│         Backend (FastAPI)           │
│  Whisper STT  │ LM Studio LLM Agent│
│  Kokoro/Vox TTS│  50+ macOS tools  │
└─────────────────────────────────────┘
```

## Tech Stack

| Layer | Technology |
|---|---|
| **UI** | SwiftUI, SwiftData, AVFoundation, AppKit |
| **Backend** | FastAPI + Uvicorn |
| **LLM** | LM Studio OpenAI-compatible API via LangChain / LangGraph |
| **STT** | MLX Whisper Large v3 |
| **TTS** | Kokoro 82M / Voxtral 4B via MLX Audio + misaki |
| **Tools** | AppleScript (AppKit), DuckDuckGo, Open-Meteo, Trafilatura |

## Quick Start

### 1. Backend

```bash
cd backend
uv sync
uv run ruff format src
uv run ruff check --fix src
uv run python src/viva_api_server.py
# Server starts on http://127.0.0.1:8001
```

Make sure LM Studio is launched at boot and serving `google/gemma-4-26b-a4b-qat` from its OpenAI-compatible API at `http://127.0.0.1:1234/v1`. Then launch the backend:

```bash
cd backend
make backend
```

**Prerequisites:**
- Python ≥3.13
- LM Studio running in the background with the model `google/gemma-4-26b-a4b-qat` loaded. For screenshot queries, use a vision-language model.
- Apple Silicon Mac (MLX requires arm64)

### 2. macOS App

Open `macos-app/Viva.xcodeproj` in Xcode and build/run. The app starts the backend with `make backend` from the `backend/` directory and communicates with it on `localhost:8001` by default.

## Project Structure

```
viva-project/
├── macos-app/
│   └── Viva/                  # SwiftUI app (Xcode project)
│       ├── VivaApp.swift      # App entry point
│       ├── ContentView.swift  # Floating panel UI + mic/screenshot
│       ├── FloatingPanel.swift# NSPanel overlay
│       ├── ContentViewModel.swift  # Orchestrates record → API → TTS
│       ├── AppDelegate.swift        # Menubar icon setup
│       ├── ScreenShotManager.swift # Display capture
│       ├── Services/              # API client, audio recorder/player
│       └── Models/                # Data types
├── backend/
│   └── src/
│       ├── viva_api_server.py     # FastAPI server (STT, agent, TTS endpoints)
│       ├── langchain_agent.py     # LangGraph agent + conversation management
│       ├── agent_tools/           # macOS automation tools (50+)
│       │   ├── applescript_tools/ # System, calendar, mail, music, Finder...
│       │   ├── general_tools.py   # Web search, weather, datetime, Python REPL
│       │   └── chains/            # AppleScript generation chains
│       └── tools/                 # TTS (Kokoro + Voxtral)
└── Makefile
```

## API Reference

| Endpoint | Method | Description |
|---|---|---|
| `/transcribe` | POST | Upload audio → returns transcribed text |
| `/viva` | POST | Send text (+ screenshot) → returns AI response + TTS audio |
| `/viva/native-audio` | POST | Send raw audio file → multimodal LLM + TTS |
| `/viva/tts-stream/{id}` | GET | Stream PCM audio for TTS playback |
| `/viva/cancel/{id}` | POST | Cancel an in-progress request |

## Configuration

Environment variables for customization:

| Variable | Default | Description |
|---|---|---|
| `VIVA_LLM_MODEL` | `google/gemma-4-26b-a4b-qat` | LM Studio model |
| `VIVA_LLM_BASE_URL` | `http://127.0.0.1:1234/v1` | LM Studio OpenAI-compatible endpoint |
| `VIVA_LLM_API_KEY` | `lm-studio` | LM Studio API key placeholder |
| `VIVA_BACKEND_HOST` | `127.0.0.1` | Backend host |
| `VIVA_BACKEND_PORT` | `8001` | Backend port |
| `VIVA_TTS_ENGINE` | `kokoro` | TTS engine (`kokoro` or `voxtral`) |
| `VIVA_TTS_VOICE_GENDER` | `female` | Voice gender for TTS |

## License

MIT — see [LICENSE](LICENSE)
