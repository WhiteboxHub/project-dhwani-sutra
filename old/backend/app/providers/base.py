"""Base interface for STT providers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import AsyncIterator


class TranscriptType(Enum):
    """Type of transcript message."""

    PARTIAL = "partial"
    FINAL = "final"


@dataclass
class Transcript:
    """Transcript result from STT provider."""

    text: str
    is_final: bool
    confidence: float | None = None
    transcript_type: TranscriptType = TranscriptType.PARTIAL
    language: str | None = None
    metadata: dict[str, any] | None = None

    def __post_init__(self) -> None:
        """Set transcript type based on is_final flag."""
        if self.is_final:
            self.transcript_type = TranscriptType.FINAL


class STTProvider(ABC):
    """
    Base interface for Speech-to-Text providers.

    All STT provider implementations must inherit from this class
    and implement the required methods.
    """

    def __init__(self, **config: any) -> None:
        """
        Initialize the STT provider.

        Args:
            **config: Provider-specific configuration
        """
        self.config = config
        self.connected = False

    @abstractmethod
    async def connect(self) -> None:
        """
        Establish connection to the STT provider.

        Raises:
            ConnectionError: If connection fails
        """
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """
        Close connection to the STT provider.

        This should gracefully close any open connections and cleanup resources.
        """
        pass

    @abstractmethod
    async def stream_audio(self, audio_chunk: bytes) -> None:
        """
        Stream audio chunk to the STT provider.

        Args:
            audio_chunk: Raw audio bytes to process

        Raises:
            RuntimeError: If provider is not connected
            ValueError: If audio format is invalid
        """
        pass

    @abstractmethod
    async def receive_transcripts(self) -> AsyncIterator[Transcript]:
        """
        Receive transcripts from the STT provider.

        Yields:
            Transcript: Partial or final transcription results

        Raises:
            RuntimeError: If provider is not connected
        """
        pass

    async def __aenter__(self) -> "STTProvider":
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type: any, exc_val: any, exc_tb: any) -> None:
        """Async context manager exit."""
        await self.disconnect()

    def is_connected(self) -> bool:
        """Check if provider is connected."""
        return self.connected


class STTProviderError(Exception):
    """Base exception for STT provider errors."""

    pass


class ConnectionError(STTProviderError):
    """Raised when connection to provider fails."""

    pass


class AuthenticationError(STTProviderError):
    """Raised when authentication with provider fails."""

    pass


class RateLimitError(STTProviderError):
    """Raised when provider rate limit is exceeded."""

    pass


class AudioFormatError(STTProviderError):
    """Raised when audio format is not supported."""

    pass
