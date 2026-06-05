"""OpenAI Realtime API STT provider implementation."""

import asyncio
import json
from typing import AsyncIterator

import websockets
from websockets.client import WebSocketClientProtocol

from app.providers.base import (
    STTProvider,
    Transcript,
    AuthenticationError,
    ConnectionError as ProviderConnectionError,
)
from app.utils.logging import get_logger

logger = get_logger(__name__)


class OpenAISTTProvider(STTProvider):
    """OpenAI Realtime API STT provider."""

    REALTIME_API_URL = "wss://api.openai.com/v1/realtime"

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-realtime-preview-2024-10-01",
        voice: str = "alloy",
        **config: any,
    ) -> None:
        """
        Initialize OpenAI provider.

        Args:
            api_key: OpenAI API key
            model: Model to use
            voice: Voice preference
            **config: Additional configuration
        """
        super().__init__(**config)
        self.api_key = api_key
        self.model = model
        self.voice = voice

        self.websocket: WebSocketClientProtocol | None = None
        self.transcript_queue: asyncio.Queue[Transcript] = asyncio.Queue()
        self._receive_task: asyncio.Task[None] | None = None

    async def connect(self) -> None:
        """Establish connection to OpenAI Realtime API."""
        try:
            logger.info("openai_connecting", model=self.model)

            # Connect to WebSocket with API key
            url = f"{self.REALTIME_API_URL}?model={self.model}"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "OpenAI-Beta": "realtime=v1",
            }

            self.websocket = await websockets.connect(url, extra_headers=headers)

            # Send session configuration
            session_config = {
                "type": "session.update",
                "session": {
                    "modalities": ["text", "audio"],
                    "instructions": "Transcribe audio input accurately.",
                    "voice": self.voice,
                    "input_audio_format": "pcm16",
                    "output_audio_format": "pcm16",
                    "input_audio_transcription": {"model": "whisper-1"},
                    "turn_detection": {"type": "server_vad"},
                },
            }

            await self.websocket.send(json.dumps(session_config))

            # Start receiving messages
            self._receive_task = asyncio.create_task(self._receive_messages())

            self.connected = True
            logger.info("openai_connected")

        except Exception as e:
            logger.error("openai_connection_failed", error=str(e))
            if "unauthorized" in str(e).lower() or "401" in str(e):
                raise AuthenticationError(f"OpenAI authentication failed: {e}") from e
            raise ProviderConnectionError(f"Failed to connect to OpenAI: {e}") from e

    async def disconnect(self) -> None:
        """Close OpenAI connection."""
        logger.info("openai_disconnecting")

        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass

        if self.websocket:
            try:
                await self.websocket.close()
            except Exception as e:
                logger.warning("openai_disconnect_error", error=str(e))

        self.connected = False
        self.websocket = None
        logger.info("openai_disconnected")

    async def stream_audio(self, audio_chunk: bytes) -> None:
        """
        Stream audio to OpenAI.

        Args:
            audio_chunk: PCM16 audio data at 24kHz
        """
        if not self.connected or not self.websocket:
            raise RuntimeError("OpenAI provider not connected")

        try:
            # Send audio in OpenAI's format
            import base64

            audio_message = {
                "type": "input_audio_buffer.append",
                "audio": base64.b64encode(audio_chunk).decode("utf-8"),
            }

            await self.websocket.send(json.dumps(audio_message))
            logger.debug("openai_audio_sent", chunk_size=len(audio_chunk))

        except Exception as e:
            logger.error("openai_audio_send_failed", error=str(e))
            raise

    async def receive_transcripts(self) -> AsyncIterator[Transcript]:
        """
        Receive transcripts from OpenAI.

        Yields:
            Transcript: Transcription results
        """
        if not self.connected:
            raise RuntimeError("OpenAI provider not connected")

        logger.info("openai_receiving_transcripts")

        while self.connected:
            try:
                transcript = await asyncio.wait_for(self.transcript_queue.get(), timeout=1.0)
                yield transcript
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error("openai_receive_error", error=str(e))
                break

    async def _receive_messages(self) -> None:
        """Background task to receive and process WebSocket messages."""
        try:
            assert self.websocket is not None

            async for message in self.websocket:
                try:
                    data = json.loads(message)
                    await self._handle_message(data)
                except json.JSONDecodeError as e:
                    logger.error("openai_json_decode_error", error=str(e))
                except Exception as e:
                    logger.error("openai_message_handle_error", error=str(e))

        except asyncio.CancelledError:
            logger.info("openai_receive_task_cancelled")
        except Exception as e:
            logger.error("openai_receive_task_error", error=str(e))
            self.connected = False

    async def _handle_message(self, data: dict[str, any]) -> None:
        """Handle incoming WebSocket message."""
        message_type = data.get("type")

        if message_type == "conversation.item.input_audio_transcription.completed":
            # Extract transcript
            transcript_text = data.get("transcript", "")

            if transcript_text.strip():
                transcript = Transcript(
                    text=transcript_text,
                    is_final=True,
                    confidence=None,  # OpenAI doesn't provide confidence
                    language="en",
                )

                self.transcript_queue.put_nowait(transcript)
                logger.debug("openai_transcript_received", text=transcript_text[:50])

        elif message_type == "conversation.item.input_audio_transcription.failed":
            error = data.get("error", {})
            logger.error("openai_transcription_failed", error=error)

        elif message_type == "error":
            error = data.get("error", {})
            logger.error("openai_error", error=error)
