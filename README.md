# Viva — Your Private, On-Device AI Assistant for macOS

**Viva** is a macOS menubar AI assistant that leverages open-source AI models to provide a completely private, local Siri alternative. Everything runs on your MacBook Pro — no cloud services, no data leaves your machine.

Speak naturally, and Viva listens, understands, and acts. It can answer questions, search the web, control your Mac, send messages, manage reminders and calendar events, and much more — all powered by locally-running open-source models on Apple Silicon.

---

## What Can It Do?

| Use Viva to... | Example request |
|---|---|
| Answer questions and keep conversational context | "What is a concise summary of this topic?" |
| Search the web | "Search for the latest Python release." |
| Extract readable text from a web page | "Read this article and summarize it." |
| Get current weather from a location or coordinates | "What's the weather in Rome?" |
| Check the current date and time | "What day is it today?" |
| Change system volume | "Set the Mac volume to 35 percent." |
| Mute or unmute audio | "Mute my Mac." |
| Toggle dark or light mode | "Turn on dark mode." |
| Check battery and charging status | "How much battery do I have left?" |
| Check Wi-Fi/network status | "What Wi-Fi network am I on?" |
| Identify the frontmost app | "What app am I using right now?" |
| Get a Mac system summary | "Tell me about this Mac." |
| Lock the screen | "Lock my Mac." |
| Start the screensaver | "Start the screensaver." |
| Open System Settings panes | "Open Bluetooth settings." |
| Show a macOS notification | "Notify me that the export is done." |
| Speak text with the system voice | "Say this out loud: meeting starts in five minutes." |
| Send an iMessage/SMS through Messages | "Text John saying I'll be there in 10 minutes." |
| Create an Apple Note | "Create a note with these meeting takeaways." |
| List reminder lists | "What reminder lists do I have?" |
| Create reminders with notes, due dates, lists, and priority | "Remind me to submit the report tomorrow at 9 AM with high priority." |
| List pending reminders | "What reminders do I still need to do?" |
| Complete reminders | "Mark the grocery reminder as done." |
| Delete reminders | "Delete the reminder about renewing the trial." |
| Update reminders | "Move the dentist reminder to Friday at 3 PM." |
| Show a reminder in Reminders | "Open my passport renewal reminder." |
| List calendars | "What calendars do I have?" |
| Create Calendar events with location, notes, URL, attendees, and alarms | "Add this event to my calendar with a 15-minute alert." |
| List Calendar events | "What's on my calendar this week?" |
| Update Calendar events | "Move my team sync to 4 PM." |
| Delete Calendar events | "Cancel the lunch event tomorrow." |
| Show a Calendar event | "Open my next dentist appointment." |
| Check Calendar conflicts | "Am I free tomorrow from 2 to 3?" |
| Find free Calendar slots | "Find a free 30-minute slot tomorrow afternoon." |
| Search Contacts | "Find Maria's contact details." |
| Get a contact's emails and phone numbers | "What email addresses do I have for Luca?" |
| List unread, recent, or searched Mail summaries | "Show me unread emails from Maria." |
| Create Mail drafts | "Draft an email to Sara about the project update." |
| Send Mail messages | "Send an email to Alex with the subject Budget and this summary." |
| List selected Finder items | "What files did I select in Finder?" |
| List folder contents | "What's inside my Downloads folder?" |
| Reveal files or folders in Finder | "Show this file in Finder." |
| Open files or folders | "Open the selected folder." |
| Create Finder folders | "Create a folder called Invoices in Documents." |
| Duplicate selected Finder items | "Duplicate the files I selected." |
| Copy selected Finder items to a folder | "Copy the selected files to my Desktop." |
| Compress selected Finder items | "Zip the files I selected in Finder." |
| Read clipboard text | "What's on my clipboard?" |
| Set clipboard text | "Copy this answer to my clipboard." |
| Read the active Safari tab URL/title | "What page am I looking at in Safari?" |
| Get the selected Finder item path | "Use the file I selected in Finder." |
| Control Apple Music playback | "Skip this song." |
| Play Apple Music recommendations and playlists | "Play music recommended for me." |
| Search and play Apple Music tracks | "Play Heroes by David Bowie." |
| Create and update Apple Music playlists | "Create a rock playlist with my highest-rated songs." |
| Empty the Trash | "Empty the trash." |

---

## 🔒 Privacy

Viva is designed with privacy as a first-class principle:

- **All AI inference runs locally** — Whisper, your chosen LLM via Ollama, and Qwen TTS all execute on your Mac's Apple Silicon chip.
- **No cloud AI APIs** — no OpenAI, Google, or Anthropic endpoints are called.
- **Web search and weather** use LangChain's DuckDuckGo integration and Open-Meteo (a free, privacy-respecting weather API that doesn't require authentication or tracking).
- **Audio recordings** are temporary and deleted immediately after transcription.

---

## ✨ Features

- **🎙️ Voice-First Interaction** — Tap the mic, speak naturally, and get spoken responses. Speech-to-text and text-to-speech run entirely on-device.
- **🔒 100% Private** — All inference happens locally via Ollama and MLX. No data is sent to any external AI provider.
- **🧠 Local LLM Agent** — Powered by a LangChain agent connected to your local Ollama instance, with in-process message history for follow-up requests. Default model is `gemma4:26b`, but any Ollama-compatible model works.
- **🖥️ macOS Integration** — Control your Mac through modular AppleScript tools: inspect system state, open settings panes, show notifications, speak feedback, send iMessages/email, create Notes, manage Reminders and Calendar events, look up Contacts, organize Finder selections, control Music playback and playlists, empty Trash, and more.
- **🌐 Web Awareness** — Search the web, extract clean text from webpages, and get real-time weather data.
- **📸 Screen Context** — Optionally share a screenshot with your request for visual context.
- **🗣️ Multilingual TTS** — Text-to-speech in 10 languages (English, Chinese, Japanese, Korean, German, French, Russian, Portuguese, Spanish, Italian) using Qwen3 TTS on MLX.
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
| **AI Agent** | LangChain + Ollama | Conversational agent with tool-calling capabilities and in-process message history |
| **Text-to-Speech** | Qwen TTS (MLX Audio) | On-device voice synthesis in 10 languages |
| **macOS Tools** | AppleScript (`osascript`) | System state, settings, notifications, speech, iMessage, Mail, Contacts, Notes, Reminders, Calendar, clipboard, Safari, Finder, Music, Trash |

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
pip install -e .
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
| `VIVA_QWEN_TTS_MODEL` | `mlx-community/Qwen3-TTS-12Hz-0.6B-CustomVoice-6bit` | MLX Qwen TTS model used for speech synthesis |
| `VIVA_QWEN_TTS_SPEAKER` | `Vivian` | Default Qwen TTS speaker voice |
| `VIVA_QWEN_TTS_INSTRUCT` | neutral delivery prompt | Voice style instruction passed to Qwen TTS |
| `VIVA_TTS_OUTPUT_DIR` | system temp `viva_tts_audio` directory | Directory for generated TTS audio files |
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
- *"Add lunch with Sara to my calendar tomorrow at 1 PM"*
- *"What's on my calendar this week?"*
- *"Find a free slot for a 30-minute meeting tomorrow afternoon"*
- *"Show me unread emails from Maria"*
- *"Zip the files I selected in Finder"*
- *"Notify me when this is done"*
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
│   ├── langchain_agent.py         # LangChain agent service and multimodal message handling
│   ├── pyproject.toml             # Python dependencies
│   ├── tools/
│   │   ├── qwen_tts_tools.py      # Qwen TTS synthesis on MLX
│   │   └── tts_tools.py           # Legacy TTS utilities
│   ├── agent_tools/
│   │   ├── general_tools.py       # Date/time, web, weather, and Python tools
│   │   └── applescript_tools/     # Modular macOS AppleScript tools
│   │       ├── __init__.py        # Collects all AppleScript tools for the LangChain agent
│   │       ├── core.py            # Shared AppleScript/date helpers
│   │       ├── system.py          # Volume, mute, dark mode
│   │       ├── system_state.py    # Battery, Wi-Fi, settings, lock screen
│   │       ├── feedback.py        # macOS notifications and spoken feedback
│   │       ├── productivity.py    # Messages and Notes
│   │       ├── reminders.py       # Reminders management
│   │       ├── calendar.py        # Calendar event management
│   │       ├── mail_contacts.py   # Mail and Contacts automation
│   │       ├── finder.py          # Safe Finder organization utilities
│   │       ├── context.py         # Clipboard, Safari, Finder context
│   │       └── media_files.py     # Music and Trash
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
| `POST` | `/viva` | Send text (+ optional screenshot and request ID) → returns AI response + TTS audio |
| `POST` | `/viva/cancel/{id}` | Cancel an in-progress Viva request by request ID |


---

## 🤝 Contributing

Contributions are welcome! Here are some areas where help is needed:

- More AppleScript tool domains for deeper macOS integration
- Vision support for screenshot understanding
- Persistent cross-session conversation history
- Settings panel for model and voice preferences
- Support for additional TTS voices and languages

Please open an issue or pull request on GitHub.

---

## 📄 License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
