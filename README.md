# Viva — Your Private, On-Device AI Assistant for macOS

**Viva** is a macOS menubar AI assistant that leverages open-source AI models to provide a completely private, local Siri alternative. Everything runs on your MacBook Pro — no cloud services, no data leaves your machine.

Speak naturally, and Viva listens, understands, and acts. It can answer questions, search the web, control your Mac, send messages, manage reminders, and much more — all powered by locally-running open-source models on Apple Silicon.

---

## 🔒 Privacy

Viva is designed with privacy as a first-class principle:

- **All AI inference runs locally** — Whisper, your chosen LLM via Ollama, and Qwen TTS all execute on your Mac's Apple Silicon chip.
- **No cloud AI APIs** — no OpenAI, Google, or Anthropic endpoints are called.
- **Web search and weather** use DuckDuckGo and Open-Meteo (a free, privacy-respecting weather API that doesn't require authentication or tracking).
- **Audio recordings** are temporary and deleted immediately after transcription.

---

## ✨ Features

- **🎙️ Voice-First Interaction** — Tap the mic, speak naturally, and get spoken responses. Speech-to-text and text-to-speech run entirely on-device.
- **🔒 100% Private** — All inference happens locally via Ollama and MLX. No data is sent to any external AI provider.
- **🧠 Local LLM Agent** — Powered by a LangChain agent connected to your local Ollama instance. Default model is `gemma4:26b`, but any Ollama-compatible model works.
- **🖥️ macOS Integration** — Control your Mac through AppleScript: adjust volume, toggle dark mode, send iMessages, create Notes and Reminders, read clipboard, control Music, empty Trash, and more.
- **🌐 Web Awareness** — Search the web, extract clean text from webpages, and get real-time weather data.
- **📸 Screen Context** — Optionally share a screenshot with your request for visual context.
- **🗣️ Multilingual TTS** — Text-to-speech in 10 languages (English, Chinese, Japanese, Korean, German, French, Russian, Portuguese, Spanish, Italian) using Qwen TTS on MLX.
- **🎤 Whisper Transcription** — MLX-powered Whisper Large V3 for fast, accurate on-device speech recognition with automatic language detection.

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────┐
│                  macOS App (SwiftUI)             │
│  ┌──────────┐  ┌──────────┐  ┌───────────────┐  │
│  │ Menubar   │  │ Floating  │  │  Audio        │  │
│  │ Icon      │→ │ Panel UI  │  │  Recorder     │  │
│  └──────────┘  └────┬─────┘  └───────────────┘  │
│                     │ HTTP                       │
└─────────────────────┼───────────────────────────┘
                      ▼
┌─────────────────────────────────────────────────┐
│           Backend (FastAPI on localhost:8000)    │
│  ┌────────────┐  ┌────────────┐  ┌───────────┐  │
│  │ MLX Whisper│  │ LangChain  │  │ Qwen TTS  │  │
│  │ (STT)      │  │ Agent +    │  │ (MLX)     │  │
│  │            │  │ Ollama LLM │  │           │  │
│  └────────────┘  └────────────┘  └───────────┘  │
│                        │                         │
│              ┌─────────┴─────────┐               │
│              │   Tool Belt       │               │
│              │ • Web Search      │               │
│              │ • Weather API     │               │
│              │ • Page Extraction │               │
│              │ • AppleScript     │               │
│              │   (macOS control) │               │
│              └───────────────────┘               │
└─────────────────────────────────────────────────┘
```

### Components

| Component | Technology | Purpose |
|---|---|---|
| **macOS App** | SwiftUI + SwiftData | Menubar icon, floating input panel, audio recording, response playback |
| **Backend Server** | FastAPI + Uvicorn | REST API coordinating STT, agent, and TTS |
| **Speech-to-Text** | MLX Whisper (Large V3) | On-device audio transcription via Apple Silicon Neural Engine |
| **AI Agent** | LangChain + Ollama | Conversational agent with tool-calling capabilities |
| **Text-to-Speech** | Qwen TTS (MLX Audio) | On-device voice synthesis in 10 languages |
| **macOS Tools** | AppleScript (`osascript`) | Volume, dark mode, iMessage, Notes, Reminders, clipboard, Safari, Finder, Music, Trash |

---

## 📋 Requirements

- **macOS** with Apple Silicon (M1/M2/M3/M4) — required for MLX acceleration
- **Xcode 15+** — to build and run the macOS app
- **Python 3.13+** — for the backend server
- **[Ollama](https://ollama.ai/)** — local LLM inference server
- **~26 GB free disk space** — for the default `gemma4:26b` model and Whisper Large V3

---

## 🚀 Setup

### 1. Install Ollama

Download and install Ollama from [ollama.ai](https://ollama.ai/), then pull the default model:

```bash
ollama pull gemma4:26b
```

Ollama will start automatically and listen on `http://localhost:11434`.

### 2. Set Up the Backend

```bash
# Navigate to the backend directory
cd backend

# Create a virtual environment and install dependencies
python -m venv .venv
source .venv/bin/activate
pip install -r pyproject.toml
```

Or use [`uv`](https://github.com/astral-sh/uv) for faster installs:

```bash
cd backend
uv sync
```

### 3. Start the Backend Server

```bash
cd backend
source .venv/bin/activate
python viva_api_server.py
```

The server starts on `http://127.0.0.1:8000`. On first launch, it will download and cache the Whisper model (~3 GB) and warm up inference — this may take a minute or two.

### 4. Build and Run the macOS App

Open the Xcode project:

```bash
open macos-app/Viva.xcodeproj
```

Select your Mac as the destination and press **⌘R** to build and run. The Viva icon will appear in your menubar.

---

## ⚙️ Configuration

All configuration is done via environment variables. Set them in your shell or a `.env` file in the `backend/` directory:

| Variable | Default | Description |
|---|---|---|
| `VIVA_OLLAMA_MODEL` | `gemma4:26b` | Ollama model to use for the agent |
| `VIVA_OLLAMA_BASE_URL` | `http://localhost:11434/v1/` | Ollama API endpoint |
| `VIVA_OLLAMA_API_KEY` | `ollama` | API key for Ollama (usually not needed) |
| `VIVA_TTS_OUTPUT_DIR` | `/tmp/viva-tts` | Directory for generated TTS audio files |
| `VIVA_TTS_WARMUP` | `0` | Set to `1` to pre-load the TTS model at startup |

Example with a custom model:

```bash
VIVA_OLLAMA_MODEL=llama3.3:70b python viva_api_server.py
```

---

## 🎯 How to Use

1. **Click the Viva icon** in the menubar to open the floating input panel.
2. **Tap the microphone** (🎙️) button and speak your request.
3. Viva transcribes your speech, sends it to the AI agent, and plays back the spoken response.
4. **Right-click** the menubar icon for Settings or to Quit.
5. Optionally enable **"Share Screen"** to include a screenshot with your request.

### Example Commands

- *"What's the weather like in Rome?"*
- *"Set a reminder to call Mom at 5 PM"*
- *"Turn on dark mode"*
- *"Search for the latest Python release"*
- *"What's on my clipboard?"*
- *"Send a message to John saying see you tomorrow"*
- *"List my reminders"*

---

## 📁 Project Structure

```
viva-project/
├── macos-app/
│   └── Viva.xcodeproj/           # Xcode project for the macOS menubar app
│       └── Viva/
│           ├── VivaApp.swift      # App entry point, menubar setup, panel management
│           ├── ContentView.swift  # Floating panel UI, audio recording, API calls
│           ├── ScreenShotManager.swift  # Screenshot capture utility
│           └── Item.swift         # SwiftData model
├── backend/
│   ├── viva_api_server.py         # FastAPI server (STT, agent, TTS endpoints)
│   ├── langchain_agent.py         # LangChain agent with tool definitions
│   ├── pyproject.toml             # Python dependencies
│   ├── tools/
│   │   ├── qwen_tts_tools.py      # Qwen TTS synthesis on MLX
│   │   └── tts_tools.py           # Legacy TTS utilities
│   ├── agent_tools/
│   │   └── applescript_tools.py   # macOS control tools (volume, messages, etc.)
│   └── chains/
│       └── applescript_generator.py  # AppleScript generation chain
└── README.md
```

---

## 🔧 Development

### Backend

```bash
cd backend
source .venv/bin/activate
python viva_api_server.py
```

The server auto-reloads on file changes (via Uvicorn's `reload=True`).

### macOS App

Build and run directly from Xcode. The app communicates with the backend via HTTP on `localhost:8000`.

### API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/transcribe` | Upload audio file → returns transcribed text |
| `POST` | `/viva` | Send text (+ optional screenshot) → returns AI response + TTS audio |
| `POST` | `/viva/cancel/{id}` | Cancel an in-progress Viva request |


---

## 🤝 Contributing

Contributions are welcome! Here are some areas where help is needed:

- More AppleScript tools for deeper macOS integration
- Vision support for screenshot understanding
- Persistent conversation history
- Settings panel for model and voice preferences
- Support for additional TTS voices and languages

Please open an issue or pull request on GitHub.

---

## 📄 License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
