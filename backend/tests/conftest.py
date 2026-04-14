"""Pytest configuration and fixtures."""

import asyncio
import os
from typing import AsyncIterator, Iterator

import pytest
from fastapi.testclient import TestClient

# Set test mode
os.environ["TEST_MODE"] = "true"
os.environ["PROVIDER"] = "mock"

from app.config import get_config, reload_config  # noqa: E402
from app.main import app  # noqa: E402
from app.providers.mock import MockSTTProvider  # noqa: E402
from app.websocket.session import SessionManager  # noqa: E402


@pytest.fixture(scope="session")
def event_loop() -> Iterator[asyncio.AbstractEventLoop]:
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def test_config():
    """Load test configuration."""
    reload_config()
    return get_config()


@pytest.fixture
def client() -> TestClient:
    """Create FastAPI test client."""
    return TestClient(app)


@pytest.fixture
async def mock_provider() -> AsyncIterator[MockSTTProvider]:
    """Create mock STT provider."""
    provider = MockSTTProvider(latency_ms=100, partial_delay_ms=50)
    await provider.connect()
    yield provider
    await provider.disconnect()


@pytest.fixture
async def session_manager() -> AsyncIterator[SessionManager]:
    """Create session manager for testing."""
    manager = SessionManager(
        max_sessions=10,
        max_age_seconds=3600,
        max_idle_seconds=600,
        cleanup_interval_seconds=10,
    )
    yield manager
    await manager.close_all()


@pytest.fixture
def sample_audio_chunk() -> bytes:
    """Generate sample audio chunk (PCM16, 16kHz, 250ms)."""
    import random

    # 250ms of PCM16 @ 16kHz = 16000 * 0.25 * 2 bytes
    chunk_size = int(16000 * 0.25 * 2)
    return bytes([random.randint(0, 255) for _ in range(chunk_size)])
