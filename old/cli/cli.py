#!/usr/bin/env python3
"""
Dhwani Sutra CLI - Command-line interface for server management
"""

import asyncio
import sys
from pathlib import Path

import click
import uvicorn

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.config import get_config, reload_config  # noqa: E402


@click.group()
@click.version_option(version="0.1.0", prog_name="dhwani-sutra")
def cli() -> None:
    """Dhwani Sutra - Real-time Speech-to-Text streaming platform."""
    pass


@cli.command()
@click.option("--host", default="0.0.0.0", help="Host to bind to")
@click.option("--port", default=8000, help="Port to bind to")
@click.option("--reload", is_flag=True, help="Enable auto-reload")
@click.option("--test-mode", is_flag=True, help="Run in test mode (mock provider)")
@click.option("--provider", type=str, help="STT provider to use")
def start(host: str, port: int, reload: bool, test_mode: bool, provider: str | None) -> None:
    """Start the Dhwani Sutra server."""
    import os

    # Set environment variables
    if test_mode:
        os.environ["TEST_MODE"] = "true"
    if provider:
        os.environ["PROVIDER"] = provider

    config = reload_config()

    click.echo("🎙️  Dhwani Sutra - Real-time Speech-to-Text")
    click.echo(f"Provider: {config.provider}")
    click.echo(f"Test Mode: {config.test_mode}")
    click.echo(f"Server: http://{host}:{port}")
    click.echo()

    try:
        uvicorn.run(
            "app.main:app",
            host=host,
            port=port,
            reload=reload,
            log_config=None,
        )
    except KeyboardInterrupt:
        click.echo("\n\nShutting down...")


@cli.command()
def info() -> None:
    """Show configuration and system information."""
    config = get_config()

    click.echo("📋 Configuration")
    click.echo("=" * 50)
    click.echo(f"Provider: {config.provider}")
    click.echo(f"Test Mode: {config.test_mode}")
    click.echo()

    click.echo("🎵 Audio Settings")
    click.echo(f"  Sample Rate: {config.audio.sample_rate} Hz")
    click.echo(f"  Format: {config.audio.format}")
    click.echo(f"  Chunk Duration: {config.audio.chunk_duration_ms} ms")
    click.echo(f"  Channels: {config.audio.channels}")
    click.echo()

    click.echo("🔗 Session Settings")
    click.echo(f"  Max Concurrent: {config.session.max_concurrent}")
    click.echo(f"  Max Duration: {config.session.max_duration_seconds}s")
    click.echo(f"  Idle Timeout: {config.session.idle_timeout_seconds}s")
    click.echo()

    click.echo("🔒 Security")
    click.echo(f"  Auth Required: {config.security.require_auth}")
    click.echo(f"  Allowed Origins: {len(config.security.allowed_origins)}")
    click.echo()

    # Check API keys
    click.echo("🔑 API Keys")
    providers_status = {
        "OpenAI": bool(config.openai_api_key),
        "Deepgram": bool(config.deepgram_api_key),
        "AssemblyAI": bool(config.assemblyai_api_key),
        "Google": bool(config.google_application_credentials),
    }

    for provider_name, configured in providers_status.items():
        status = "✓" if configured else "✗"
        click.echo(f"  {status} {provider_name}")


@cli.command()
@click.option("--provider", default="mock", help="Provider to test")
async def test_provider(provider: str) -> None:
    """Test STT provider connection."""
    import os

    from app.providers.factory import ProviderFactory

    os.environ["PROVIDER"] = provider
    config = reload_config()

    click.echo(f"Testing {provider} provider...")

    try:
        # Create provider
        stt_provider = ProviderFactory.create_provider(provider, config)

        # Test connection
        click.echo("Connecting...")
        await stt_provider.connect()
        click.echo("✓ Connected successfully")

        # Disconnect
        await stt_provider.disconnect()
        click.echo("✓ Disconnected successfully")

        click.echo(f"\n✓ {provider} provider test passed")

    except Exception as e:
        click.echo(f"\n✗ Test failed: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option("--duration", default=10, help="Simulation duration (seconds)")
@click.option("--session-id", help="Session ID (optional)")
def simulate_sender(duration: int, session_id: str | None) -> None:
    """Simulate an audio sender for testing."""
    import json
    import random
    import time

    import websocket

    url = "ws://localhost:8000/ws/sender"
    click.echo(f"Connecting to {url}...")

    ws = websocket.WebSocket()
    ws.connect(url)

    # Send init message
    init_msg = {"type": "init"}
    if session_id:
        init_msg["session_id"] = session_id

    ws.send(json.dumps(init_msg))

    # Receive session info
    response = json.loads(ws.recv())
    click.echo(f"Session created: {response.get('session_id')}")

    # Send fake audio chunks
    click.echo(f"Sending audio for {duration} seconds...")
    start_time = time.time()

    while time.time() - start_time < duration:
        # Generate fake audio chunk (250ms @ 16kHz)
        chunk_size = 16000 * 2 // 4  # 250ms of PCM16
        fake_audio = bytes([random.randint(0, 255) for _ in range(chunk_size)])

        ws.send_binary(fake_audio)
        time.sleep(0.25)

        if int(time.time() - start_time) % 5 == 0:
            click.echo(f"  {int(time.time() - start_time)}s elapsed...")

    # End session
    ws.send(json.dumps({"type": "end"}))
    ws.close()

    click.echo("✓ Simulation complete")


@cli.command()
@click.argument("session-id")
@click.option("--duration", default=30, help="Receive duration (seconds)")
def simulate_receiver(session_id: str, duration: int) -> None:
    """Simulate a transcript receiver for testing."""
    import json
    import time

    import websocket

    url = f"ws://localhost:8000/ws/receiver/{session_id}"
    click.echo(f"Connecting to {url}...")

    ws = websocket.WebSocket()
    ws.connect(url)

    # Receive connection confirmation
    response = json.loads(ws.recv())
    click.echo(f"Connected: {response.get('type')}")

    click.echo(f"Receiving transcripts for {duration} seconds...")
    click.echo("Press Ctrl+C to stop\n")

    start_time = time.time()

    try:
        ws.settimeout(1.0)
        while time.time() - start_time < duration:
            try:
                message = ws.recv()
                data = json.loads(message)

                if data.get("type") in ["transcript_partial", "transcript_final"]:
                    is_final = data.get("is_final", False)
                    text = data.get("text", "")
                    confidence = data.get("confidence")

                    status = "[FINAL]" if is_final else "[PARTIAL]"
                    conf_str = f" ({confidence:.0%})" if confidence else ""

                    click.echo(f"{status}{conf_str} {text}")

            except websocket.WebSocketTimeoutException:
                continue

    except KeyboardInterrupt:
        click.echo("\n\nStopped by user")

    ws.close()
    click.echo("✓ Receiver closed")


@cli.command()
@click.option("--format", type=click.Choice(["json", "text"]), default="text")
def check_health(format: str) -> None:
    """Check server health status."""
    import requests

    url = "http://localhost:8000/health"

    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()

        if format == "json":
            click.echo(response.text)
        else:
            data = response.json()
            click.echo("Health Check Results")
            click.echo("=" * 50)
            click.echo(f"Status: {data.get('status')}")
            click.echo(f"Provider: {data.get('provider')}")
            click.echo(f"Test Mode: {data.get('test_mode')}")

    except requests.RequestException as e:
        click.echo(f"✗ Health check failed: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    # Handle async commands
    if len(sys.argv) > 1 and sys.argv[1] == "test-provider":
        # Remove the command from argv to avoid click processing it
        provider_arg = None
        if "--provider" in sys.argv:
            idx = sys.argv.index("--provider")
            provider_arg = sys.argv[idx + 1]

        async def run_test() -> None:
            await test_provider(provider_arg or "mock")

        asyncio.run(run_test())
    else:
        cli()
