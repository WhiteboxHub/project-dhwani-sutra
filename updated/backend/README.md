# Wisper STT Backend

This is the backend architecture supporting real-time, multi-session Speech-to-Text inference, LLM-based transcript cleaning, and bidirectional WebSocket streaming. It is built entirely on **FastAPI** to handle high-throughput async processing and real-time broadcasting.

## 🚀 Features

- **Multi-Session WebSocket Broadcasting**: An in-memory `ConnectionManager` routes messages using unique `session_id` channels, allowing simultaneous, independent streaming sessions to run continuously.
- **Pluggable STT Architecture**: Seamlessly scales between chunked uploading and true real-time parsing using dynamic Speech-to-Text providers:
  - **OpenAI Whisper** (Default): Processes rapid 1-3s `.webm` chunks via asynchronous threaded API calls.
  - **Deepgram**: Fast, real-time live-stream socket ingestion (ideal for continuous low-latency).
- **Background LLM Refining**: Transcriptions run parallel to a background `llm_cleaning` service which corrects grammatical domain-specific terminology (e.g. LangChain, RAG) on the fly without blocking the WebSocket pipeline.

## 🛠️ Setup & Installation

### 1. Prerequisites
Ensure you have Python 3.9+ installed and operational. 

### 2. Virtual Environment
It's highly recommended to isolate dependencies. To set up the virtual environment (`myenv`):
```bash
# Generate virtual environment
python -m venv myenv

# Activate (Windows)
./myenv/Scripts/activate

# Activate (macOS/Linux)
source myenv/bin/activate
```

### 3. Install Dependencies
Make sure you install the required packages:
```bash
pip install fastapi uvicorn websockets python-dotenv openai deepgram-sdk langchain pydantic
```

## ⚙️ Environment Variables
Create a root level `.env` file referencing your API keys and provider targets. Based on the provided template:

```ini
# Core Configuration
STT_PROVIDER=openai # Options: [openai, deepgram]

# API Keys
OPEN_AI_KEY=sk-...your-openai-key...
DEEPGRAM_API_KEY=your-deepgram-key...
```

## 🔌 Using the API (WebSocket Endpoints)

All endpoints utilize pure WebSockets `(ws://)` under `uvicorn`.

### 1. The Streamer Interface
**Endpoint**: `ws://<HOST>:<PORT>/ws/stt/{session_id}?provider=[openai|deepgram]`

The gateway primarily responsible for receiving continuous `.webm` audio queues.
* Broadcasts down `transcript_raw` payloads instantaneously inside the session.
* Non-blockingly fires the context-aware LLM generation mapping the segment ID.
* Emits `transcript_cleaned` payloads asynchronously back to the event loop.

### 2. The Listener Interface
**Endpoint**: `ws://<HOST>:<PORT>/ws/listen/{session_id}`

A headless connection that registers itself to the `ConnectionManager`. It receives identical JSON broadcasting outputs (raw and cleaned transcript objects) without pushing data payloads. 

## 🏃‍♂️ Running the Server

Start the application utilizing `uvicorn` live-reload pointing to `main.py` entrypoint:

```bash
uvicorn main:app --reload
```

Server spawns on `http://127.0.0.1:8000`. Keep this alive to establish client routing.
