"""AssemblyAI STT provider implementation."""

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


class AssemblyAISTTProvider(STTProvider):
    """AssemblyAI real-time STT provider."""

    REALTIME_URL = "wss://api.assemblyai.com/v2/realtime/ws"

    def __init__(
        self,
        api_key: str,
        language_code: str = "en_us",
        punctuate: bool = True,
        format_text: bool = True,
        **config: any,
    ) -> None:
        """
        Initialize AssemblyAI provider.

        Args:
            api_key: AssemblyAI API key
            language_code: Language code (en_us, es, etc.)
            punctuate: Enable punctuation
            format_text: Enable text formatting
            **config: Additional configuration
        """
        super().__init__(**config)
        self.api_key = api_key
        self.language_code = language_code
        self.punctuate = punctuate
        self.format_text = format_text

        self.websocket: WebSocketClientProtocol | None = None
        self.transcript_queue: asyncio.Queue[Transcript] = asyncio.Queue()
        self._receive_task: asyncio.Task[None] | None = None

    async def connect(self) -> None:
        """Establish connection to AssemblyAI."""
        try:
            logger.info("assemblyai_connecting", language=self.language_code)

            # Build URL with parameters
            params = {
                "sample_rate": "16000",
                "word_boost": json.dumps([]),
                "encoding": "pcm_s16le",
            }

            url = (
                f"{self.REALTIME_URL}"
                f"?sample_rate={params['sample_rate']}"
                f"&encoding={params['encoding']}"
            )

            # Connect with API key in header
            headers = {"Authorization": self.api_key}

            self.websocket = await websockets.connect(url, extra_headers=headers)

            # Wait for session begins message
            response = await self.websocket.recv()
            data = json.loads(response)

            if data.get("message_type") != "SessionBegins":
                raise ProviderConnectionError(
                    f"Unexpected initial message: {data.get('message_type')}"
                )

            # Start receiving messages
            self._receive_task = asyncio.create_task(self._receive_messages())

            self.connected = True
            logger.info("assemblyai_connected", session_id=data.get("session_id"))

        except Exception as e:
            logger.error("assemblyai_connection_failed", error=str(e))
            if "unauthorized" in str(e).lower() or "401" in str(e):
                raise AuthenticationError(f"AssemblyAI authentication failed: {e}") from e
            raise ProviderConnectionError(f"Failed to connect to AssemblyAI: {e}") from e

    async def disconnect(self) -> None:
        """Close AssemblyAI connection."""
        logger.info("assemblyai_disconnecting")

        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass

        if self.websocket:
            try:
                # Send termination message
                await self.websocket.send(json.dumps({"terminate_session": True}))
                await self.websocket.close()
            except Exception as e:
                logger.warning("assemblyai_disconnect_error", error=str(e))

        self.connected = False
        self.websocket = None
        logger.info("assemblyai_disconnected")

    async def stream_audio(self, audio_chunk: bytes) -> None:
        """
        Stream audio to AssemblyAI.

        Args:
            audio_chunk: PCM16 audio data at 16kHz
        """
        if not self.connected or not self.websocket:
            raise RuntimeError("AssemblyAI provider not connected")

        try:
            # AssemblyAI expects base64-encoded audio
            import base64

            audio_data = {
                "audio_data": base64.b64encode(audio_chunk).decode("utf-8"),
            }

            await self.websocket.send(json.dumps(audio_data))
            logger.debug("assemblyai_audio_sent", chunk_size=len(audio_chunk))

        except Exception as e:
            logger.error("assemblyai_audio_send_failed", error=str(e))
            raise

    async def receive_transcripts(self) -> AsyncIterator[Transcript]:
        """
        Receive transcripts from AssemblyAI.

        Yields:
            Transcript: Transcription results
        """
        if not self.connected:
            raise RuntimeError("AssemblyAI provider not connected")

        logger.info("assemblyai_receiving_transcripts")

        while self.connected:
            try:
                transcript = await asyncio.wait_for(self.transcript_queue.get(), timeout=1.0)
                yield transcript
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error("assemblyai_receive_error", error=str(e))
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
                    logger.error("assemblyai_json_decode_error", error=str(e))
                except Exception as e:
                    logger.error("assemblyai_message_handle_error", error=str(e))

        except asyncio.CancelledError:
            logger.info("assemblyai_receive_task_cancelled")
        except Exception as e:
            logger.error("assemblyai_receive_task_error", error=str(e))
            self.connected = False

    async def _handle_message(self, data: dict[str, any]) -> None:
        """Handle incoming WebSocket message."""
        message_type = data.get("message_type")

        if message_type == "PartialTranscript":
            text = data.get("text", "")
            if text.strip():
                transcript = Transcript(
                    text=text,
                    is_final=False,
                    confidence=data.get("confidence"),
                    language=self.language_code,
                )
                self.transcript_queue.put_nowait(transcript)
                logger.debug("assemblyai_partial_transcript", text=text[:50])

        elif message_type == "FinalTranscript":
            text = data.get("text", "")
            if text.strip():
                transcript = Transcript(
                    text=text,
                    is_final=True,
                    confidence=data.get("confidence"),
                    language=self.language_code,
                )
                self.transcript_queue.put_nowait(transcript)
                logger.debug("assemblyai_final_transcript", text=text[:50])

        elif message_type == "SessionTerminated":
            logger.info("assemblyai_session_terminated")
            self.connected = False
