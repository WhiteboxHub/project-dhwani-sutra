
import asyncio
import threading
from typing import AsyncIterator

from deepgram import DeepgramClient
# from deepgram import LiveTranscriptionEvents as EventType
from deepgram.core.events import EventType

from app.providers.base import (
    STTProvider,
    Transcript,
    AuthenticationError,
    ConnectionError as ProviderConnectionError,
)
from app.utils.logging import get_logger

logger = get_logger(__name__)


class DeepgramSTTProvider(STTProvider):
    """Deepgram real-time STT provider (new SDK)."""

    def __init__(
        self,
        api_key: str,
        model: str = "nova-3",
        language: str = "en-US",
        smart_format: bool = True,
        punctuate: bool = True,
        **config: any,
    ) -> None:
        super().__init__(**config)

        self.api_key = api_key
        self.model = model
        self.language = language
        self.smart_format = smart_format
        self.punctuate = punctuate

        self.client: DeepgramClient | None = None
        self.connection = None

        self.transcript_queue: asyncio.Queue[Transcript] = asyncio.Queue()

        # Threading control
        self._listen_thread = None
        self._loop = asyncio.get_event_loop()

    async def connect(self) -> None:
        """Establish connection to Deepgram."""
        try:
            logger.info("deepgram_connecting", model=self.model)

            self.client = DeepgramClient()

            # Create websocket connection (NEW SDK STYLE)
            self.connection = self.client.listen.v1.connect(
                model=self.model
                # ,language=self.language,
                # smart_format=self.smart_format,
                # punctuate=self.punctuate,
                # interim_results=True,
            )

            # Register event handlers
            self.connection.on(EventType.OPEN, self._on_open)
            self.connection.on(EventType.MESSAGE, self._on_message)
            self.connection.on(EventType.ERROR, self._on_error)
            self.connection.on(EventType.CLOSE, self._on_close)

            # Start listening in background thread
            def _start():
                try:
                    self.connection.start_listening()
                except Exception as e:
                    logger.error("deepgram_listening_error", error=str(e))

            self._listen_thread = threading.Thread(target=_start, daemon=True)
            self._listen_thread.start()

            self.connected = True
            logger.info("deepgram_connected")

        except Exception as e:
            logger.error("deepgram_connection_failed", error=str(e))

            if "authentication" in str(e).lower():
                raise AuthenticationError(str(e)) from e

            raise ProviderConnectionError(str(e)) from e

    async def disconnect(self) -> None:
        """Close connection."""
        logger.info("deepgram_disconnecting")

        try:
            if self.connection:
                self.connection.finish()
        except Exception as e:
            logger.warning("deepgram_disconnect_error", error=str(e))

        self.connected = False
        self.connection = None
        self.client = None

        logger.info("deepgram_disconnected")

    async def stream_audio(self, audio_chunk: bytes) -> None:
        """Send audio chunk."""
        if not self.connected or not self.connection:
            raise RuntimeError("Not connected")

        try:
            self.connection.send_media(audio_chunk)
        except Exception as e:
            logger.error("deepgram_audio_send_failed", error=str(e))
            raise

    async def receive_transcripts(self) -> AsyncIterator[Transcript]:
        """Async generator for transcripts."""
        if not self.connected:
            raise RuntimeError("Not connected")

        while self.connected:
            try:
                transcript = await asyncio.wait_for(
                    self.transcript_queue.get(), timeout=1.0
                )
                yield transcript
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error("deepgram_receive_error", error=str(e))
                break

    # =========================
    # Event Handlers (UPDATED)
    # =========================

    def _on_open(self, *args, **kwargs):
        logger.info("deepgram_connection_opened")

    def _on_message(self, message):
        """Handle transcript messages (NEW FORMAT)."""
        try:
            if not hasattr(message, "channel"):
                return

            alternatives = message.channel.alternatives
            if not alternatives:
                return

            alt = alternatives[0]
            text = alt.transcript

            if not text.strip():
                return

            is_final = getattr(message, "is_final", True)
            confidence = getattr(alt, "confidence", None)

            transcript = Transcript(
                text=text,
                is_final=is_final,
                confidence=confidence,
                language=self.language,
            )

            # Push safely to async queue from thread
            asyncio.run_coroutine_threadsafe(
                self.transcript_queue.put(transcript), self._loop
            )

            logger.debug(
                "deepgram_transcript",
                text=text[:50],
                is_final=is_final,
            )

        except Exception as e:
            logger.error("deepgram_parse_error", error=str(e))

    def _on_error(self, error):
        logger.error("deepgram_error", error=str(error))

    def _on_close(self, *args, **kwargs):
        logger.info("deepgram_connection_closed")
        self.connected = False