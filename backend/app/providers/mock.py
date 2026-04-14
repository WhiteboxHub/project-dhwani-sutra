"""Mock STT provider for testing and development."""

import asyncio
import random
from typing import AsyncIterator

from app.providers.base import STTProvider, Transcript
from app.utils.logging import get_logger

logger = get_logger(__name__)


class MockSTTProvider(STTProvider):
    """
    Mock STT provider that returns predefined transcripts.

    This provider simulates realistic STT behavior without making
    external API calls. Useful for:
    - Development and testing
    - CI/CD pipelines
    - Demonstrations
    - Cost-free experimentation
    """

    SAMPLE_TRANSCRIPTS = [
        "Hello, this is a test of the speech to text system.",
        "The quick brown fox jumps over the lazy dog.",
        "Python is a great programming language for building real-time applications.",
        "WebSockets enable bidirectional communication between clients and servers.",
        "Machine learning models are revolutionizing speech recognition technology.",
        "Real-time transcription has many applications in accessibility and productivity.",
        "FastAPI makes it easy to build high-performance async web services.",
        "The weather today is sunny with a chance of cloud cover in the afternoon.",
        "Remember to check your email for important updates and notifications.",
        "Thank you for using our speech to text platform.",
    ]

    def __init__(
        self,
        latency_ms: int = 300,
        partial_delay_ms: int = 150,
        error_rate: float = 0.0,
        **config: any,
    ) -> None:
        """
        Initialize mock provider.

        Args:
            latency_ms: Simulated latency for final transcripts (milliseconds)
            partial_delay_ms: Delay between partial updates (milliseconds)
            error_rate: Probability of simulating an error (0.0 to 1.0)
            **config: Additional configuration
        """
        super().__init__(**config)
        self.latency_ms = latency_ms
        self.partial_delay_ms = partial_delay_ms
        self.error_rate = error_rate
        self.audio_buffer: list[bytes] = []
        self.transcript_index = 0
        self._should_stop = False

    async def connect(self) -> None:
        """Establish mock connection."""
        logger.info("mock_provider_connecting")
        await asyncio.sleep(0.1)  # Simulate connection delay
        self.connected = True
        logger.info("mock_provider_connected")

    async def disconnect(self) -> None:
        """Close mock connection."""
        logger.info("mock_provider_disconnecting")
        self._should_stop = True
        self.connected = False
        self.audio_buffer.clear()
        logger.info("mock_provider_disconnected")

    async def stream_audio(self, audio_chunk: bytes) -> None:
        """
        Buffer audio chunks.

        Args:
            audio_chunk: Audio data to buffer
        """
        if not self.connected:
            raise RuntimeError("Provider not connected")

        self.audio_buffer.append(audio_chunk)
        logger.debug("mock_provider_audio_received", chunk_size=len(audio_chunk))

    async def receive_transcripts(self) -> AsyncIterator[Transcript]:
        """
        Generate mock transcripts.

        Simulates realistic STT behavior with:
        - Partial transcripts that build up progressively
        - Final transcripts after full processing
        - Realistic latency
        - Optional errors for testing error handling

        Yields:
            Transcript: Mock transcription results
        """
        if not self.connected:
            raise RuntimeError("Provider not connected")

        logger.info("mock_provider_starting_transcription")

        while not self._should_stop:
            # Wait for audio buffer to accumulate
            if len(self.audio_buffer) < 5:
                await asyncio.sleep(0.1)
                continue

            # Simulate random errors
            if random.random() < self.error_rate:
                logger.warning("mock_provider_simulated_error")
                await asyncio.sleep(1.0)
                continue

            # Get next sample transcript
            transcript_text = self.SAMPLE_TRANSCRIPTS[
                self.transcript_index % len(self.SAMPLE_TRANSCRIPTS)
            ]
            self.transcript_index += 1

            # Split into words for progressive partial transcripts
            words = transcript_text.split()

            # Send partial transcripts
            for i in range(1, len(words)):
                partial_text = " ".join(words[:i])
                yield Transcript(
                    text=partial_text,
                    is_final=False,
                    confidence=0.85 + random.random() * 0.1,
                )
                logger.debug("mock_provider_partial", text=partial_text)
                await asyncio.sleep(self.partial_delay_ms / 1000.0)

            # Send final transcript
            await asyncio.sleep(self.latency_ms / 1000.0)
            yield Transcript(
                text=transcript_text,
                is_final=True,
                confidence=0.95 + random.random() * 0.05,
                language="en-US",
            )
            logger.info("mock_provider_final", text=transcript_text)

            # Clear some of the buffer
            self.audio_buffer = self.audio_buffer[5:]

            # Add delay before next transcript
            await asyncio.sleep(0.5)
