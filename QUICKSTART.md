# Quick Start Guide

Get Dhwani Sutra running in 5 minutes!

## Option 1: Docker (Recommended)

```bash
# 1. Start everything with docker-compose
docker-compose up --build

# That's it! Services will be available at:
# - Backend API: http://localhost:8000
# - Sender UI: http://localhost:8080
# - Receiver UI: http://localhost:8081
```

## Option 2: Local Development

```bash
# 1. Install backend dependencies
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 2. Start backend (in terminal 1)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 3. Start sender frontend (in terminal 2)
cd ../frontend/sender
python -m http.server 8080

# 4. Start receiver frontend (in terminal 3)
cd ../frontend/receiver
python -m http.server 8081
```

## First Test

1. **Open Sender**: Navigate to http://localhost:8080
2. **Allow Microphone**: Click "Start Recording" and grant microphone permission
3. **Get Session ID**: Copy the session ID displayed after connection
4. **Open Receiver**: Navigate to http://localhost:8081
5. **Connect**: Paste the session ID and hit Enter
6. **Speak**: Talk into your microphone and see real-time transcripts!

## Using Real STT Providers

### Deepgram (Recommended for Production)

```bash
# 1. Get API key from https://deepgram.com
# 2. Set environment variable
export PROVIDER=deepgram
export DEEPGRAM_API_KEY=your_key_here

# 3. Restart backend
uvicorn app.main:app --reload
```

### OpenAI Realtime API

```bash
export PROVIDER=openai
export OPENAI_API_KEY=your_key_here
```

### AssemblyAI

```bash
export PROVIDER=assemblyai
export ASSEMBLYAI_API_KEY=your_key_here
```

### Google Cloud Speech

```bash
export PROVIDER=google
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/credentials.json
```

## Testing with CLI

```bash
# Test provider connection
python cli/cli.py test-provider --provider mock

# Simulate audio sender (for testing without microphone)
python cli/cli.py simulate-sender --duration 10

# Check system health
python cli/cli.py check-health

# View configuration
python cli/cli.py info
```

## Common Issues

### "Connection failed"
- Ensure backend is running on port 8000
- Check firewall settings
- Verify WebSocket support in browser

### "No audio level"
- Grant microphone permissions
- Check if microphone is working in other apps
- Try a different browser (Chrome/Edge recommended)

### "No transcripts appearing"
- Verify session ID matches between sender and receiver
- Check backend logs for errors
- Ensure audio is being captured (watch audio level bar)

## Next Steps

- 📖 Read the full [README.md](README.md) for detailed documentation
- 🔧 Configure providers in [config.yaml](config.yaml)
- 🧪 Run tests: `cd backend && pytest`
- 🚀 Deploy to production (see README.md)

## Architecture at a Glance

```
Sender (Browser) → WebSocket → Backend → STT Provider
                                           ↓
Receiver (Browser) ← WebSocket ← Broadcast ← Transcripts
```

The mock provider is perfect for development - it simulates realistic STT behavior without API calls or costs!
