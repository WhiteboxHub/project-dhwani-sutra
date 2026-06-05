"""Unit tests for audio utilities."""

import numpy as np
import pytest

from app.audio.buffer import AudioBuffer, CircularAudioBuffer
from app.audio.encoder import AudioEncoder


class TestAudioEncoder:
    """Test audio encoder utilities."""

    def test_pcm16_to_float32(self):
        """Test PCM16 to float32 conversion."""
        # Create test PCM16 data
        pcm_data = np.array([0, 16384, -16384, 32767, -32768], dtype=np.int16).tobytes()

        # Convert to float32
        float_data = AudioEncoder.pcm16_to_float32(pcm_data)

        assert isinstance(float_data, np.ndarray)
        assert float_data.dtype == np.float32
        assert len(float_data) == 5
        assert float_data[0] == pytest.approx(0.0, abs=0.01)
        assert -1.0 <= float_data.min() <= 1.0
        assert -1.0 <= float_data.max() <= 1.0

    def test_float32_to_pcm16(self):
        """Test float32 to PCM16 conversion."""
        # Create test float32 data
        float_data = np.array([0.0, 0.5, -0.5, 1.0, -1.0], dtype=np.float32)

        # Convert to PCM16
        pcm_data = AudioEncoder.float32_to_pcm16(float_data)

        assert isinstance(pcm_data, bytes)
        assert len(pcm_data) == 10  # 5 samples * 2 bytes

    def test_resample(self):
        """Test audio resampling."""
        # Create test audio at 48kHz
        duration = 1.0  # 1 second
        orig_sr = 48000
        audio = np.random.randn(int(duration * orig_sr)).astype(np.float32)

        # Resample to 16kHz
        target_sr = 16000
        resampled = AudioEncoder.resample(audio, orig_sr, target_sr)

        # Check output length
        expected_length = int(duration * target_sr)
        assert len(resampled) == pytest.approx(expected_length, rel=0.01)

    def test_resample_same_rate(self):
        """Test that resampling at same rate returns original."""
        audio = np.random.randn(16000).astype(np.float32)
        resampled = AudioEncoder.resample(audio, 16000, 16000)

        assert np.array_equal(audio, resampled)

    def test_stereo_to_mono(self):
        """Test stereo to mono conversion."""
        # Create stereo audio (N, 2)
        stereo = np.random.randn(1000, 2).astype(np.float32)

        # Convert to mono
        mono = AudioEncoder.stereo_to_mono(stereo)

        assert mono.shape == (1000,)
        # Mono should be average of channels
        expected = np.mean(stereo, axis=1)
        assert np.array_equal(mono, expected)

    def test_stereo_to_mono_already_mono(self):
        """Test that mono audio is unchanged."""
        mono = np.random.randn(1000).astype(np.float32)
        result = AudioEncoder.stereo_to_mono(mono)

        assert np.array_equal(mono, result)

    def test_validate_audio_chunk_valid(self):
        """Test validation of valid audio chunk."""
        # Create valid chunk (100ms @ 16kHz)
        chunk_size = 16000 * 2 // 10  # 100ms
        chunk = bytes([0] * chunk_size)

        assert AudioEncoder.validate_audio_chunk(chunk, 16000, 1)

    def test_validate_audio_chunk_empty(self):
        """Test validation rejects empty chunk."""
        assert not AudioEncoder.validate_audio_chunk(b"", 16000, 1)

    def test_validate_audio_chunk_too_small(self):
        """Test validation rejects too-small chunk."""
        chunk = bytes([0] * 100)  # Too small
        assert not AudioEncoder.validate_audio_chunk(chunk, 16000, 1)

    def test_validate_audio_chunk_bad_alignment(self):
        """Test validation rejects misaligned chunk."""
        chunk = bytes([0] * 3201)  # Odd number (PCM16 requires even)
        assert not AudioEncoder.validate_audio_chunk(chunk, 16000, 1)


class TestAudioBuffer:
    """Test audio buffer."""

    @pytest.mark.asyncio
    async def test_buffer_initialization(self):
        """Test buffer initialization."""
        buffer = AudioBuffer(target_chunk_size=1000)

        assert buffer.target_chunk_size == 1000
        assert buffer.is_empty()

    @pytest.mark.asyncio
    async def test_add_and_flush_chunk(self):
        """Test adding and flushing chunks."""
        buffer = AudioBuffer(target_chunk_size=100)

        # Add small chunk
        await buffer.add_chunk(b"x" * 50)
        assert not buffer.is_empty()
        assert buffer.get_buffer_size() == 50

        # Add another chunk to trigger flush
        await buffer.add_chunk(b"y" * 60)

        # Should have flushed 100 bytes
        assert buffer.get_buffer_size() == 10  # 50 + 60 - 100

    @pytest.mark.asyncio
    async def test_get_chunks(self):
        """Test getting chunks."""
        buffer = AudioBuffer(target_chunk_size=100, flush_timeout=0.1)

        # Add chunks
        await buffer.add_chunk(b"a" * 100)
        await buffer.add_chunk(b"b" * 100)

        # Get chunks
        chunks = []
        async for chunk in buffer.get_chunks():
            chunks.append(chunk)
            if len(chunks) == 2:
                break

        assert len(chunks) == 2
        assert chunks[0] == b"a" * 100
        assert chunks[1] == b"b" * 100

    @pytest.mark.asyncio
    async def test_buffer_overflow(self):
        """Test buffer handles overflow."""
        buffer = AudioBuffer(target_chunk_size=100, max_buffer_size=500)

        # Add data exceeding max buffer size
        await buffer.add_chunk(b"x" * 600)

        # Buffer should not exceed max size
        assert buffer.get_buffer_size() <= 500

    @pytest.mark.asyncio
    async def test_flush_all(self):
        """Test flushing remaining data."""
        buffer = AudioBuffer(target_chunk_size=100)

        # Add incomplete chunk
        await buffer.add_chunk(b"x" * 50)
        assert buffer.get_buffer_size() == 50

        # Flush all
        await buffer.flush_all()
        assert buffer.is_empty()


class TestCircularAudioBuffer:
    """Test circular audio buffer."""

    def test_initialization(self):
        """Test circular buffer initialization."""
        buffer = CircularAudioBuffer(capacity_seconds=1.0, sample_rate=16000)

        assert buffer.capacity_bytes == 16000 * 2  # 1 second @ 16kHz PCM16
        assert buffer.total_bytes == 0

    def test_add_and_overflow(self):
        """Test adding data with overflow."""
        buffer = CircularAudioBuffer(capacity_seconds=0.5, sample_rate=16000)

        # Add more data than capacity
        chunk_size = 4000  # 0.125 seconds
        for _ in range(10):  # Total 1.25 seconds
            buffer.add(b"x" * chunk_size)

        # Should not exceed capacity
        assert buffer.total_bytes <= buffer.capacity_bytes

    def test_get_recent_all(self):
        """Test getting all recent audio."""
        buffer = CircularAudioBuffer(capacity_seconds=1.0, sample_rate=16000)

        # Add some data
        buffer.add(b"a" * 1000)
        buffer.add(b"b" * 1000)

        recent = buffer.get_recent()
        assert len(recent) == 2000

    def test_get_recent_duration(self):
        """Test getting specific duration."""
        buffer = CircularAudioBuffer(capacity_seconds=1.0, sample_rate=16000)

        # Add 1 second of data
        buffer.add(b"x" * 32000)

        # Get 0.5 seconds
        recent = buffer.get_recent(duration_seconds=0.5)
        expected_bytes = int(0.5 * 16000 * 2)
        assert len(recent) == expected_bytes

    def test_clear(self):
        """Test clearing buffer."""
        buffer = CircularAudioBuffer(capacity_seconds=1.0, sample_rate=16000)

        buffer.add(b"x" * 1000)
        assert buffer.total_bytes > 0

        buffer.clear()
        assert buffer.total_bytes == 0

    def test_get_duration_seconds(self):
        """Test getting buffer duration."""
        buffer = CircularAudioBuffer(capacity_seconds=1.0, sample_rate=16000)

        # Add 0.5 seconds of data
        buffer.add(b"x" * 16000)  # 0.5 seconds @ 16kHz PCM16

        duration = buffer.get_duration_seconds()
        assert duration == pytest.approx(0.5, abs=0.01)
