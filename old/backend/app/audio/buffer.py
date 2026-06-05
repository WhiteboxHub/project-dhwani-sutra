"""Audio buffering and chunking utilities."""

import asyncio
from collections import deque
from typing import AsyncIterator

from app.utils.logging import get_logger

logger = get_logger(__name__)


class AudioBuffer:
    """
    Buffer for managing audio chunks with configurable size and timeout.

    Handles:
    - Accumulating small chunks into larger ones
    - Managing backpressure
    - Timeout-based flushing
    """

    def __init__(
        self,
        target_chunk_size: int = 4096,
        max_buffer_size: int = 102400,
        flush_timeout: float = 0.5,
    ) -> None:
        """
        Initialize audio buffer.

        Args:
            target_chunk_size: Target size for output chunks (bytes)
            max_buffer_size: Maximum buffer size before dropping (bytes)
            flush_timeout: Time to wait before flushing incomplete chunk (seconds)
        """
        self.target_chunk_size = target_chunk_size
        self.max_buffer_size = max_buffer_size
        self.flush_timeout = flush_timeout

        self.buffer = bytearray()
        self.queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._last_chunk_time = asyncio.get_event_loop().time()
        self._closed = False

    async def add_chunk(self, chunk: bytes) -> None:
        """
        Add audio chunk to buffer.

        Args:
            chunk: Audio data to add

        Raises:
            ValueError: If buffer is full
        """
        if self._closed:
            logger.warning("audio_buffer_closed", action="add_chunk")
            return

        # Check buffer size
        if len(self.buffer) + len(chunk) > self.max_buffer_size:
            logger.warning(
                "audio_buffer_full",
                current_size=len(self.buffer),
                incoming_size=len(chunk),
                max_size=self.max_buffer_size,
            )
            # Drop oldest data to make room
            overflow = len(self.buffer) + len(chunk) - self.max_buffer_size
            self.buffer = self.buffer[overflow:]

        # Add to buffer
        self.buffer.extend(chunk)
        self._last_chunk_time = asyncio.get_event_loop().time()

        logger.debug(
            "audio_chunk_buffered",
            chunk_size=len(chunk),
            buffer_size=len(self.buffer),
        )

        # Flush if buffer is large enough
        while len(self.buffer) >= self.target_chunk_size:
            await self._flush_chunk()

    async def _flush_chunk(self) -> None:
        """Flush a complete chunk from buffer to queue."""
        if len(self.buffer) >= self.target_chunk_size:
            chunk = bytes(self.buffer[: self.target_chunk_size])
            self.buffer = self.buffer[self.target_chunk_size :]
            await self.queue.put(chunk)

            logger.debug(
                "audio_chunk_flushed",
                chunk_size=len(chunk),
                remaining=len(self.buffer),
            )

    async def flush_all(self) -> None:
        """Flush any remaining data in buffer."""
        if len(self.buffer) > 0:
            chunk = bytes(self.buffer)
            self.buffer.clear()
            await self.queue.put(chunk)

            logger.debug("audio_buffer_flushed_all", chunk_size=len(chunk))

    async def get_chunks(self) -> AsyncIterator[bytes]:
        """
        Get audio chunks as they become available.

        Yields:
            Audio chunks
        """
        while not self._closed:
            try:
                # Wait for chunk with timeout
                chunk = await asyncio.wait_for(self.queue.get(), timeout=self.flush_timeout)
                yield chunk

            except asyncio.TimeoutError:
                # Timeout - flush incomplete chunk if enough time has passed
                current_time = asyncio.get_event_loop().time()
                time_since_last = current_time - self._last_chunk_time

                if time_since_last >= self.flush_timeout and len(self.buffer) > 0:
                    await self.flush_all()

    def close(self) -> None:
        """Close the buffer."""
        self._closed = True
        logger.info("audio_buffer_closed")

    def is_empty(self) -> bool:
        """Check if buffer is empty."""
        return len(self.buffer) == 0 and self.queue.empty()

    def get_buffer_size(self) -> int:
        """Get current buffer size in bytes."""
        return len(self.buffer)


class CircularAudioBuffer:
    """
    Circular buffer for audio with fixed capacity.

    Useful for keeping recent audio history for:
    - Reconnection recovery
    - VAD (Voice Activity Detection) context
    - Error recovery
    """

    def __init__(self, capacity_seconds: float = 5.0, sample_rate: int = 16000) -> None:
        """
        Initialize circular buffer.

        Args:
            capacity_seconds: Buffer capacity in seconds
            sample_rate: Audio sample rate
        """
        # Calculate capacity in bytes (PCM16 = 2 bytes per sample)
        self.capacity_bytes = int(capacity_seconds * sample_rate * 2)
        self.sample_rate = sample_rate

        self.buffer: deque[bytes] = deque(maxlen=self._calculate_max_chunks())
        self.total_bytes = 0

    def _calculate_max_chunks(self, avg_chunk_size: int = 4096) -> int:
        """Calculate maximum number of chunks to store."""
        return max(1, self.capacity_bytes // avg_chunk_size)

    def add(self, chunk: bytes) -> None:
        """
        Add chunk to circular buffer.

        Args:
            chunk: Audio data to add
        """
        self.buffer.append(chunk)
        self.total_bytes += len(chunk)

        # Maintain total bytes count
        while len(self.buffer) > 0 and self.total_bytes > self.capacity_bytes:
            removed = self.buffer.popleft()
            self.total_bytes -= len(removed)

        logger.debug(
            "circular_buffer_add",
            chunk_size=len(chunk),
            total_chunks=len(self.buffer),
            total_bytes=self.total_bytes,
        )

    def get_recent(self, duration_seconds: float | None = None) -> bytes:
        """
        Get recent audio from buffer.

        Args:
            duration_seconds: Duration to retrieve (None for all)

        Returns:
            Audio data
        """
        if duration_seconds is None:
            # Return all
            return b"".join(self.buffer)

        # Calculate target bytes
        target_bytes = int(duration_seconds * self.sample_rate * 2)

        # Collect from end
        result = bytearray()
        for chunk in reversed(self.buffer):
            if len(result) >= target_bytes:
                break
            result[0:0] = chunk  # Prepend

        return bytes(result[-target_bytes:])

    def clear(self) -> None:
        """Clear the buffer."""
        self.buffer.clear()
        self.total_bytes = 0
        logger.info("circular_buffer_cleared")

    def get_duration_seconds(self) -> float:
        """Get current buffer duration in seconds."""
        return self.total_bytes / (self.sample_rate * 2)
