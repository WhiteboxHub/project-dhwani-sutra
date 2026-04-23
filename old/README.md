# Dhwani Sutra

**Production-grade, modular, end-to-end real-time Speech-to-Text streaming platform**

A scalable STT system where users speak into a browser, audio is streamed to a backend, transcribed in real-time using pluggable providers, and broadcast live to receiver web pages.

## Features

✨ **Modular Provider Architecture** - Pluggable STT providers (OpenAI, Deepgram, AssemblyAI, Google)  
🚀 **Real-time Streaming** - WebSocket-based low-latency audio streaming  
📡 **Multi-receiver Broadcasting** - One sender, multiple receivers per session  
🧪 **Test Mode** - Mock provider for development without API costs  
🐳 **Docker Ready** - Complete containerization with docker-compose  
🔧 **Production-Grade** - Error handling, reconnection, circuit breakers, structured logging  
📊 **Observability** - Health checks, metrics hooks, correlation IDs  
🎯 **Type-Safe** - Full type hints and async architecture

## Architecture

```
┌─────────────┐       WebSocket        ┌──────────────┐
│  Sender     │ ──────────────────────→│   Backend    │
│  (Browser)  │     Audio Chunks       │   (FastAPI)  │
└─────────────┘                        └──────────────┘
                                              │
                                              ↓
                                       ┌──────────────┐
                                       │ STT Provider │
                                       │  (Pluggable) │
                                       └──────────────┘
                                              │
                                              ↓
┌─────────────┐       WebSocket        ┌──────────────┐
│  Receiver   │ ←──────────────────────│  Broadcast   │
│  (Browser)  │     Transcripts        │   (N:1)      │
└─────────────┘                        └──────────────┘
```

## Quick Start

### 1. Clone and Setup

```bash
git clone <repo-url>
cd project-dhwani-sutra

# Backend setup
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure

Copy `.env.example` to `.env` and configure your settings:

```bash
cp .env.example .env
```

Edit `.env`:
```env
PROVIDER=mock  # or openai, deepgram, assemblyai, google
DEEPGRAM_API_KEY=your_key_here
# Add other provider keys as needed
```

### 3. Run with Docker (Recommended)

```bash
docker-compose up --build
```

This starts:
- Backend API: http://localhost:8000
- Sender UI: http://localhost:8080
- Receiver UI: http://localhost:8081

### 4. Run Locally

```bash
# Terminal 1: Backend
cd backend
uvicorn app.main:app --reload

# Terminal 2: Sender frontend
cd frontend/sender
python -m http.server 8080

# Terminal 3: Receiver frontend
cd frontend/receiver
python -m http.server 8081
```

### 5. Use the Application

1. Open sender: http://localhost:8080
2. Click "Start Recording" and allow microphone access
3. Copy the session ID shown
4. Open receiver: http://localhost:8081
5. Paste session ID and see live transcripts!

## CLI Tool

```bash
# Start server
python cli/cli.py start

# Start in test mode
python cli/cli.py start --test-mode

# Show configuration
python cli/cli.py info

# Test provider connection
python cli/cli.py test-provider --provider deepgram

# Simulate sender
python cli/cli.py simulate-sender --duration 10

# Simulate receiver
python cli/cli.py simulate-receiver <session-id>

# Check health
python cli/cli.py check-health
```

## Configuration

Configuration is managed via `config.yaml` and environment variables:

```yaml
# Provider selection
provider: mock  # openai | deepgram | assemblyai | google | mock

# Audio settings
audio:
  sample_rate: 16000
  chunk_duration_ms: 250
  format: opus
  channels: 1

# Session management
session:
  max_duration_seconds: 14400  # 4 hours
  idle_timeout_seconds: 3600   # 1 hour
  max_concurrent: 100
```

Environment variables override config file settings.

## STT Providers

### Mock Provider (Default)
No API key required. Perfect for development and testing.

```bash
PROVIDER=mock
```

### Deepgram
```bash
PROVIDER=deepgram
DEEPGRAM_API_KEY=your_key
```

### OpenAI Realtime API
```bash
PROVIDER=openai
OPENAI_API_KEY=your_key
```

### AssemblyAI
```bash
PROVIDER=assemblyai
ASSEMBLYAI_API_KEY=your_key
```

### Google Cloud Speech
```bash
PROVIDER=google
GOOGLE_APPLICATION_CREDENTIALS=/path/to/credentials.json
```

## Testing

```bash
cd backend

# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html

# Run specific test file
pytest tests/unit/test_providers.py -v

# Run integration tests only
pytest tests/integration/
```

## Development

### Code Quality

```bash
# Type checking
mypy app/

# Linting
ruff check app/

# Format code
black app/
ruff check --fix app/
```

### Project Structure

```
backend/
  app/
    providers/         # STT provider implementations
    websocket/         # WebSocket gateway and sessions
    audio/             # Audio processing utilities
    utils/             # Logging, retry, etc.
  tests/
    unit/              # Unit tests
    integration/       # Integration tests

frontend/
  sender/              # Audio capture client
  receiver/            # Transcript display client

cli/                   # Command-line tool
config.yaml            # Configuration
docker-compose.yml     # Docker setup
```

## API Documentation

Once running, visit:
- **API Docs**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/health
- **Readiness**: http://localhost:8000/ready

## WebSocket Protocol

### Sender (`/ws/sender`)

**Client → Server:**
```json
{"type": "init"}
```

**Server → Client:**
```json
{
  "type": "session_created",
  "session_id": "uuid",
  "provider": "deepgram"
}
```

**Client → Server:** Binary audio chunks (PCM16/Opus)

### Receiver (`/ws/receiver/{session_id}`)

**Server → Client (Partial):**
```json
{
  "type": "transcript_partial",
  "session_id": "uuid",
  "text": "Hello",
  "is_final": false,
  "confidence": 0.85
}
```

**Server → Client (Final):**
```json
{
  "type": "transcript_final",
  "session_id": "uuid",
  "text": "Hello world",
  "is_final": true,
  "confidence": 0.95
}
```

## Scaling

### Single Instance (Default)
- In-memory session management
- Suitable for <100 concurrent sessions

### Distributed (Redis)
```bash
# Start with Redis
docker-compose --profile with-redis up

# Configure
REDIS_URL=redis://localhost:6379/0
```

## Production Checklist

- [ ] Set strong API keys in environment variables
- [ ] Configure allowed origins in `config.yaml`
- [ ] Enable authentication if needed
- [ ] Set up monitoring and alerting
- [ ] Configure log aggregation
- [ ] Set up SSL/TLS (use WSS for WebSockets)
- [ ] Configure rate limiting
- [ ] Set up Redis for distributed deployments
- [ ] Configure backup STT provider for failover

## Troubleshooting

**Audio not capturing:**
- Ensure microphone permissions are granted
- Check browser compatibility (Chrome/Edge recommended)
- Verify HTTPS for production (microphone requires secure context)

**Connection errors:**
- Check firewall settings
- Verify WebSocket support
- Check CORS configuration in `config.yaml`

**Provider errors:**
- Verify API keys are correct
- Check provider status pages
- Try test mode: `PROVIDER=mock`
- Check logs: `docker-compose logs backend`

**No transcripts:**
- Verify audio is being sent (check network tab)
- Check session ID matches between sender and receiver
- Review backend logs for errors

## Performance

**Latency breakdown:**
- Audio capture → backend: 10-50ms
- Backend → STT provider: 50-200ms
- Provider processing: 100-500ms (varies by provider)
- Broadcast to receivers: 10-50ms
- **Total end-to-end: 170-800ms**

**Optimization tips:**
- Reduce chunk duration (trade latency for accuracy)
- Use opus encoding for bandwidth
- Enable Redis for distributed caching
- Use provider-specific optimizations

## Security

- API keys via environment variables only
- Rate limiting enabled by default
- CORS restrictions configured
- Session timeout and cleanup
- Input validation on all WebSocket messages
- No audio persistence by default

## License

MIT

## Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open Pull Request

## Support

- 📖 Documentation: See `CLAUDE.md` for developer guide
- 🐛 Issues: GitHub Issues
- 💬 Discussions: GitHub Discussions

## Acknowledgments

Built with:
- FastAPI - Modern async web framework
- Deepgram/OpenAI/AssemblyAI/Google - STT providers
- structlog - Structured logging
- pytest - Testing framework

---

**Dhwani Sutra** - धवनि सूत्र - "Thread of Sound"
