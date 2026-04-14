# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Dhwani Sutra** is a production-grade, modular, real-time Speech-to-Text streaming platform. Users speak into a browser (sender), audio is streamed via WebSocket to a backend, transcribed in real-time using pluggable STT providers, and broadcast live to receiver web pages.

### Architecture Flow
```
Mic (Client A) → WebSocket → Backend → STT Provider → WebSocket broadcast → Receiver (Client B)
```

## Tech Stack

- **Backend**: Python with FastAPI, async/await, WebSockets
- **Frontend**: Vanilla JavaScript, Web Audio API, MediaRecorder
- **Transport**: WebSocket-based streaming, optional Redis PubSub for scaling
- **Containerization**: Docker and docker-compose

## Core Design Principles

### 1. Pluggable STT Provider Architecture
All STT providers implement a common interface:
```python
class STTProvider:
    async def connect()
    async def stream_audio(chunk)
    async def receive_transcript()
    async def close()
```

Providers are interchangeable via configuration. Supported providers:
- OpenAI Realtime API
- Deepgram
- AssemblyAI
- Google Speech-to-Text

### 2. Session Management
- Each audio stream is a session with a unique ID
- Sessions support multiple receiver clients (1:N broadcast)
- Session state stored in memory or Redis for distributed deployments
- Sessions have TTL and max duration limits

### 3. WebSocket Protocol
Message types:
- `audio_chunk`: Binary audio data from sender
- `transcript_partial`: Interim transcription results
- `transcript_final`: Final transcription with confidence
- `error`: Error messages with codes
- `status`: Connection and session state updates

### 4. Error Handling & Resilience
- WebSocket reconnection with exponential backoff
- Audio buffering during network interruptions
- Provider failover and circuit breaker patterns
- Graceful degradation when providers are unavailable

## Project Structure

```
backend/
  app/
    providers/           # STT provider implementations
      base.py           # Base STTProvider interface
      openai.py
      deepgram.py
      assemblyai.py
      google.py
      mock.py           # Test mode provider
    websocket/
      gateway.py        # WebSocket connection handler
      session.py        # Session lifecycle management
      broadcaster.py    # Multi-client broadcast logic
    audio/
      encoder.py        # Audio format conversion
      buffer.py         # Buffering and chunking
    utils/
      retry.py          # Retry and backoff logic
      logging.py        # Structured logging
    config.py           # Configuration management
    main.py             # FastAPI app entry point
  tests/
    unit/
    integration/
  Dockerfile
  requirements.txt
  pyproject.toml

frontend/
  sender/               # Audio capture and streaming client
    index.html
    app.js
    audio-capture.js
  receiver/             # Transcript display client
    index.html
    app.js
    transcript-display.js

cli/
  cli.py               # CLI tool for server management

docker-compose.yml
config.yaml            # Default configuration
.env.example
```

## Development Commands

### Initial Setup
```bash
# Backend setup
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt

# Install dev dependencies
pip install pytest pytest-asyncio httpx websockets
```

### Running the Application

```bash
# Start backend (development)
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Start backend in test mode (no external API calls)
uvicorn app.main:app --reload --env TEST_MODE=true

# Start with specific provider
PROVIDER=deepgram uvicorn app.main:app --reload

# Using Docker
docker-compose up --build

# Frontend (serve with any static server)
python -m http.server 8080 --directory frontend/sender
python -m http.server 8081 --directory frontend/receiver
```

### Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html

# Run specific test file
pytest tests/unit/test_providers.py

# Run integration tests only
pytest tests/integration/ -v

# Run with test mode provider
pytest -k "test_mode"
```

### Code Quality

```bash
# Type checking
mypy app/

# Linting
ruff check app/
black --check app/

# Format code
black app/
ruff check --fix app/
```

## Configuration

Configuration is managed via `config.yaml` and environment variables:

```yaml
provider: deepgram              # openai | deepgram | assemblyai | google | mock
sample_rate: 16000
chunk_duration_ms: 250
audio_format: opus              # opus | pcm | wav
session_max_duration: 14400     # 4 hours
session_idle_timeout: 3600      # 1 hour
max_concurrent_sessions: 100
log_level: info
redis_url: null                 # Enable for distributed deployments
```

Environment variables override config file:
- `PROVIDER`
- `DEEPGRAM_API_KEY`
- `OPENAI_API_KEY`
- `ASSEMBLYAI_API_KEY`
- `GOOGLE_APPLICATION_CREDENTIALS`
- `REDIS_URL`
- `TEST_MODE`

## Key Implementation Notes

### Audio Format Handling
- Default: Opus codec at 16kHz for bandwidth efficiency
- Backend resamples to provider requirements automatically
- Mono audio preferred; stereo converted to mono
- Audio encoder utility handles all format conversions

### Session Lifecycle
1. Client connects → backend creates session ID
2. Session registered in SessionManager
3. Multiple receivers can subscribe to same session
4. Session cleaned up on timeout or explicit close
5. Orphaned sessions cleaned via background task

### Provider Selection
Provider is dependency-injected based on config:
```python
provider = get_provider(config.provider)
await provider.connect()
```

Test mode uses MockProvider that returns deterministic transcripts without API calls.

### WebSocket Gateway Responsibilities
- Accept sender connections (audio ingress)
- Accept receiver connections (transcript egress)
- Route audio chunks to active STT provider
- Broadcast transcripts to all receivers in session
- Handle connection errors and reconnections

### Monitoring & Observability
- Structured JSON logs with correlation IDs per session
- Log levels: DEBUG (dev), INFO (prod), ERROR (alerts)
- Key metrics to track:
  - Active sessions count
  - Audio chunk latency (capture → backend)
  - STT provider latency (audio → transcript)
  - End-to-end latency (capture → receiver display)
  - Provider API errors
  - WebSocket disconnections

### Security Considerations
- Use WSS (TLS) in production
- Implement session token authentication
- Rate limit per IP and per session
- API keys via environment variables or secrets manager
- CORS configuration for allowed origins
- Input validation on all WebSocket messages

## Testing Strategy

### Test Mode
Enable with `TEST_MODE=true`. Uses MockProvider that:
- Returns predefined transcripts
- Simulates realistic latency
- No external API calls or costs
- Deterministic for CI/CD

### Unit Tests
- Provider interface compliance
- Audio encoding/decoding
- WebSocket message serialization
- Session management logic

### Integration Tests
- End-to-end flow with MockProvider
- Multiple concurrent sessions
- Receiver broadcast functionality
- Reconnection scenarios

### Load Testing
- Simulate multiple concurrent senders
- Measure latency under load
- Test session limits

## Scaling Considerations

### Single Instance
- In-memory session management
- Direct WebSocket connections
- Suitable for <100 concurrent sessions

### Distributed (Redis PubSub)
- Session state in Redis
- WebSocket connections load balanced
- Sticky sessions not required
- Horizontal scaling of backend pods

## Common Pitfall Avoidance

1. **Audio Format Mismatches**: Always validate provider expects the format you're sending
2. **WebSocket Backpressure**: Implement buffering if receiver can't keep up with audio rate
3. **Provider Rate Limits**: Use circuit breaker pattern and retry with backoff
4. **Session Leaks**: Ensure cleanup on both normal and error paths
5. **Browser Compatibility**: Test MediaRecorder codec support across browsers
6. **Latency Accumulation**: Monitor each stage; optimize audio chunk size vs latency tradeoff

## Browser Client Notes

### Sender
- Request microphone permission explicitly
- Use `AudioWorklet` for lowest latency (fallback to MediaRecorder)
- Send audio in 250ms chunks by default
- Show visual feedback for mic level and connection status
- Handle network errors with reconnection

### Receiver
- Display partial transcripts with visual differentiation from final
- Smooth text updates (no flicker)
- Auto-scroll transcript display
- Show connection status and latency indicators

## Adding a New STT Provider

1. Create new file in `app/providers/`
2. Inherit from `STTProvider` base class
3. Implement all async methods
4. Add provider-specific configuration
5. Register in provider factory (`config.py`)
6. Add integration test
7. Update documentation

## When Things Break

- Check logs for session correlation ID
- Verify API keys are set correctly
- Test with `TEST_MODE=true` to isolate provider issues
- Use browser DevTools Network tab for WebSocket debugging
- Monitor provider status pages
- Check Redis connection if using distributed mode
