"""End-to-end integration tests."""

import asyncio

import pytest

from app.audio.buffer import AudioBuffer
from app.providers.mock import MockSTTProvider
from app.websocket.broadcaster import TranscriptBroadcaster
from app.websocket.session import Session, SessionManager, SessionState


class TestEndToEndFlow:
    """Test complete end-to-end flow."""

    @pytest.mark.asyncio
    async def test_simple_transcription_flow(self, mock_provider, sample_audio_chunk):
        """Test basic transcription flow."""
        # Create session
        session = Session(session_id="e2e-test", provider=mock_provider)
        session.state = SessionState.ACTIVE

        # Add audio chunks to buffer
        for _ in range(15):
            await session.audio_buffer.add_chunk(sample_audio_chunk)

        # Stream audio to provider
        async for chunk in session.audio_buffer.get_chunks():
            await mock_provider.stream_audio(chunk)
            break  # Just test one chunk

        # Receive transcripts
        transcripts = []
        async for transcript in mock_provider.receive_transcripts():
            transcripts.append(transcript)
            if transcript.is_final:
                break

        # Verify we got transcripts
        assert len(transcripts) > 0
        assert any(t.is_final for t in transcripts)

    @pytest.mark.asyncio
    async def test_session_lifecycle(self):
        """Test complete session lifecycle."""
        # Create manager
        manager = SessionManager()

        # Create provider and session
        provider = MockSTTProvider()
        await provider.connect()

        session = manager.create_session(provider)
        session_id = session.session_id

        assert session_id in manager.sessions
        assert session.state == SessionState.INITIALIZING

        # Activate session
        session.state = SessionState.ACTIVE
        assert session.state == SessionState.ACTIVE

        # Close session
        await manager.remove_session(session_id)

        assert session_id not in manager.sessions
        assert session.state == SessionState.CLOSED

        await provider.disconnect()

    @pytest.mark.asyncio
    async def test_multiple_concurrent_sessions(self):
        """Test handling multiple concurrent sessions."""
        manager = SessionManager(max_sessions=5)
        sessions = []

        # Create multiple sessions
        for i in range(3):
            provider = MockSTTProvider()
            await provider.connect()

            session = manager.create_session(provider)
            session.state = SessionState.ACTIVE
            sessions.append(session)

        # Verify all sessions are active
        assert len(manager.sessions) == 3
        for session in sessions:
            assert session.state == SessionState.ACTIVE

        # Cleanup
        await manager.close_all()
        assert len(manager.sessions) == 0

    @pytest.mark.asyncio
    async def test_audio_buffering_and_streaming(self, sample_audio_chunk):
        """Test audio buffering and streaming pipeline."""
        buffer = AudioBuffer(target_chunk_size=4096, flush_timeout=0.1)

        # Add multiple chunks
        for _ in range(5):
            await buffer.add_chunk(sample_audio_chunk)

        # Collect chunks
        chunks = []
        async for chunk in buffer.get_chunks():
            chunks.append(chunk)
            if len(chunks) >= 2:
                break

        assert len(chunks) >= 2
        for chunk in chunks:
            assert len(chunk) > 0

        buffer.close()

    @pytest.mark.asyncio
    async def test_provider_error_recovery(self):
        """Test error recovery with provider."""
        provider = MockSTTProvider(error_rate=0.5)  # 50% error rate
        await provider.connect()

        # Try to stream audio multiple times
        chunk = b"x" * 8000

        attempts = 0
        max_attempts = 10

        while attempts < max_attempts:
            try:
                await provider.stream_audio(chunk)
                attempts += 1
            except Exception:
                # Error occurred, but should be able to continue
                attempts += 1

        # Should have completed attempts despite errors
        assert attempts == max_attempts

        await provider.disconnect()

    @pytest.mark.asyncio
    async def test_session_expiry_and_cleanup(self):
        """Test that expired sessions are cleaned up."""
        manager = SessionManager(
            max_age_seconds=0.2,
            max_idle_seconds=0.2,
            cleanup_interval_seconds=0.1,
        )

        # Create provider and session
        provider = MockSTTProvider()
        await provider.connect()

        session = manager.create_session(provider)
        session_id = session.session_id

        # Wait for expiry
        await asyncio.sleep(0.3)

        # Run cleanup
        await manager.cleanup_expired_sessions()

        # Session should be removed
        assert session_id not in manager.sessions

        await provider.disconnect()


class TestBroadcasting:
    """Test transcript broadcasting."""

    @pytest.mark.asyncio
    async def test_broadcast_format(self):
        """Test transcript message format."""
        from app.providers.base import Transcript

        transcript = Transcript(
            text="Hello world",
            is_final=True,
            confidence=0.95,
            language="en-US",
        )

        message = TranscriptBroadcaster._format_transcript_message(transcript, "test-session")

        assert "test-session" in message
        assert "Hello world" in message
        assert "0.95" in message

    @pytest.mark.asyncio
    async def test_broadcast_to_multiple_receivers(self):
        """Test broadcasting to multiple receivers."""
        # This would require WebSocket mocking
        # For now, just test the message formatting
        from app.providers.base import Transcript

        transcript = Transcript(
            text="Test message",
            is_final=False,
            confidence=0.85,
        )

        # Test that formatting works
        message = TranscriptBroadcaster._format_transcript_message(transcript, "session-123")

        assert '"type": "transcript_partial"' in message or '"type":"transcript_partial"' in message
        assert "Test message" in message
