"""Deepgram STT provider implementation."""

import asyncio
from typing import AsyncIterator

from deepgram import DeepgramClient, DeepgramClientOptions, LiveOptions, LiveTranscriptionEvents
from deepgram.clients.live.v1 import LiveClient

from app.providers.base import (
    STTProvider,
    Transcript,
    AuthenticationError,
    ConnectionError as ProviderConnectionError,
)
from app.utils.logging import get_logger

logger = get_logger(__name__)


class DeepgramSTTProvider(STTProvider):
    """Deepgram real-time STT provider."""

    def __init__(
        self,
        api_key: str,
        model: str = "nova-2",
        language: str = "en-US",
        smart_format: bool = True,
        punctuate: bool = True,
        **config: any,
    ) -> None:
        """
        Initialize Deepgram provider.

        Args:
            api_key: Deepgram API key
            model: Model to use (nova-2, nova, base, enhanced, etc.)
            language: Language code
            smart_format: Enable smart formatting
            punctuate: Enable punctuation
            **config: Additional configuration
        """
        super().__init__(**config)
        self.api_key = api_key
        self.model = model
        self.language = language
        self.smart_format = smart_format
        self.punctuate = punctuate

        self.client: DeepgramClient | None = None
        self.connection: LiveClient | None = None
        self.transcript_queue: asyncio.Queue[Transcript] = asyncio.Queue()

    async def connect(self) -> None:
        """Establish connection to Deepgram."""
        try:
            logger.info("deepgram_connecting", model=self.model, language=self.language)

            # Create Deepgram client
            config = DeepgramClientOptions(options={"keepalive": "true"})
            self.client = DeepgramClient(self.api_key, config)

            # Create live transcription connection
            self.connection = self.client.listen.live.v("1")

            # Set up event handlers
            self.connection.on(LiveTranscriptionEvents.Open, self._on_open)
            self.connection.on(LiveTranscriptionEvents.Transcript, self._on_transcript)
            self.connection.on(LiveTranscriptionEvents.Error, self._on_error)
            self.connection.on(LiveTranscriptionEvents.Close, self._on_close)

            # Configure live options
            options = LiveOptions(
                model=self.model,
                language=self.language,
                smart_format=self.smart_format,
                punctuate=self.punctuate,
                encoding="linear16",
                sample_rate=16000,
                channels=1,
                interim_results=True,
            )

            # Start connection
            if not self.connection.start(options):
                raise ProviderConnectionError("Failed to start Deepgram connection")

            self.connected = True
            logger.info("deepgram_connected")

        except Exception as e:
            logger.error("deepgram_connection_failed", error=str(e))
            if "authentication" in str(e).lower() or "unauthorized" in str(e).lower():
                raise AuthenticationError(f"Deepgram authentication failed: {e}") from e
            raise ProviderConnectionError(f"Failed to connect to Deepgram: {e}") from e

    async def disconnect(self) -> None:
        """Close Deepgram connection."""
        logger.info("deepgram_disconnecting")

        if self.connection:
            try:
                self.connection.finish()
            except Exception as e:
                logger.warning("deepgram_disconnect_error", error=str(e))

        self.connected = False
        self.connection = None
        self.client = None
        logger.info("deepgram_disconnected")

    async def stream_audio(self, audio_chunk: bytes) -> None:
        """
        Stream audio to Deepgram.

        Args:
            audio_chunk: PCM16 audio data at 16kHz
        """
        if not self.connected or not self.connection:
            raise RuntimeError("Deepgram provider not connected")

        try:
            self.connection.send(audio_chunk)
            logger.debug("deepgram_audio_sent", chunk_size=len(audio_chunk))
        except Exception as e:
            logger.error("deepgram_audio_send_failed", error=str(e))
            raise

    async def receive_transcripts(self) -> AsyncIterator[Transcript]:
        """
        Receive transcripts from Deepgram.

        Yields:
            Transcript: Transcription results
        """
        if not self.connected:
            raise RuntimeError("Deepgram provider not connected")

        logger.info("deepgram_receiving_transcripts")

        while self.connected:
            try:
                # Wait for transcript with timeout
                transcript = await asyncio.wait_for(self.transcript_queue.get(), timeout=1.0)
                yield transcript
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error("deepgram_receive_error", error=str(e))
                break

    def _on_open(self, *args: any, **kwargs: any) -> None:
        """Handle connection open event."""
        logger.info("deepgram_connection_opened")

    def _on_transcript(self, *args: any, **kwargs: any) -> None:
        """Handle transcript event."""
        try:
            # Deepgram sends result as first argument
            result = args[0] if args else kwargs.get("result")

            if not result:
                return

            # Extract transcript data
            channel = result.channel
            alternatives = channel.alternatives

            if not alternatives:
                return

            alternative = alternatives[0]
            text = alternative.transcript

            if not text or not text.strip():
                return

            # Determine if this is a final transcript
            is_final = result.is_final if hasattr(result, "is_final") else True
            confidence = alternative.confidence if hasattr(alternative, "confidence") else None

            transcript = Transcript(
                text=text,
                is_final=is_final,
                confidence=confidence,
                language=self.language,
            )

            # Add to queue (non-blocking)
            self.transcript_queue.put_nowait(transcript)

            logger.debug(
                "deepgram_transcript_received",
                text=text[:50],
                is_final=is_final,
                confidence=confidence,
            )

        except Exception as e:
            logger.error("deepgram_transcript_parse_error", error=str(e))

    def _on_error(self, *args: any, **kwargs: any) -> None:
        """Handle error event."""
        error = args[0] if args else kwargs.get("error", "Unknown error")
        logger.error("deepgram_error", error=str(error))

    def _on_close(self, *args: any, **kwargs: any) -> None:
        """Handle connection close event."""
        logger.info("deepgram_connection_closed")
        self.connected = False
