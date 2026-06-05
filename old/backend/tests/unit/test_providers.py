"""Unit tests for STT providers."""

import pytest

from app.providers.base import STTProvider, Transcript
from app.providers.factory import ProviderFactory
from app.providers.mock import MockSTTProvider


class TestMockProvider:
    """Test mock STT provider."""

    @pytest.mark.asyncio
    async def test_connection(self):
        """Test provider connection and disconnection."""
        provider = MockSTTProvider()

        assert not provider.is_connected()

        await provider.connect()
        assert provider.is_connected()

        await provider.disconnect()
        assert not provider.is_connected()

    @pytest.mark.asyncio
    async def test_context_manager(self):
        """Test provider as async context manager."""
        async with MockSTTProvider() as provider:
            assert provider.is_connected()

        assert not provider.is_connected()

    @pytest.mark.asyncio
    async def test_stream_audio(self, mock_provider, sample_audio_chunk):
        """Test audio streaming."""
        await mock_provider.stream_audio(sample_audio_chunk)
        assert len(mock_provider.audio_buffer) == 1

    @pytest.mark.asyncio
    async def test_stream_audio_not_connected(self, sample_audio_chunk):
        """Test that streaming fails when not connected."""
        provider = MockSTTProvider()

        with pytest.raises(RuntimeError, match="not connected"):
            await provider.stream_audio(sample_audio_chunk)

    @pytest.mark.asyncio
    async def test_receive_transcripts(self, mock_provider, sample_audio_chunk):
        """Test receiving transcripts."""
        # Send some audio chunks
        for _ in range(10):
            await mock_provider.stream_audio(sample_audio_chunk)

        # Receive transcripts
        received = []
        async for transcript in mock_provider.receive_transcripts():
            received.append(transcript)
            if transcript.is_final:
                break

        # Should have received at least partial and final
        assert len(received) > 0
        assert any(t.is_final for t in received)
        assert any(not t.is_final for t in received)

    @pytest.mark.asyncio
    async def test_transcript_format(self, mock_provider, sample_audio_chunk):
        """Test transcript object format."""
        for _ in range(10):
            await mock_provider.stream_audio(sample_audio_chunk)

        async for transcript in mock_provider.receive_transcripts():
            assert isinstance(transcript, Transcript)
            assert isinstance(transcript.text, str)
            assert isinstance(transcript.is_final, bool)
            assert transcript.confidence is None or isinstance(transcript.confidence, float)

            if transcript.is_final:
                break


class TestProviderFactory:
    """Test provider factory."""

    def test_create_mock_provider(self, test_config):
        """Test creating mock provider."""
        provider = ProviderFactory.create_provider("mock", test_config)
        assert isinstance(provider, MockSTTProvider)

    def test_create_provider_in_test_mode(self, test_config):
        """Test that test mode always creates mock provider."""
        test_config.test_mode = True
        provider = ProviderFactory.create_provider("openai", test_config)
        assert isinstance(provider, MockSTTProvider)

    def test_invalid_provider_type(self, test_config):
        """Test that invalid provider type raises error."""
        with pytest.raises(ValueError, match="Unknown provider type"):
            ProviderFactory.create_provider("invalid", test_config)


class TestSTTProviderInterface:
    """Test STT provider base interface."""

    @pytest.mark.asyncio
    async def test_provider_implements_interface(self, mock_provider):
        """Test that mock provider implements base interface."""
        assert isinstance(mock_provider, STTProvider)
        assert hasattr(mock_provider, "connect")
        assert hasattr(mock_provider, "disconnect")
        assert hasattr(mock_provider, "stream_audio")
        assert hasattr(mock_provider, "receive_transcripts")
        assert hasattr(mock_provider, "is_connected")
