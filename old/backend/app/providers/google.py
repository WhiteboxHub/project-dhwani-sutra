"""Google Cloud Speech-to-Text provider implementation."""

import asyncio
from typing import AsyncIterator

from google.cloud import speech
from google.oauth2 import service_account

from app.providers.base import (
    STTProvider,
    Transcript,
    AuthenticationError,
    ConnectionError as ProviderConnectionError,
)
from app.utils.logging import get_logger

logger = get_logger(__name__)


class GoogleSTTProvider(STTProvider):
    """Google Cloud Speech-to-Text streaming provider."""

    def __init__(
        self,
        credentials_path: str,
        language_code: str = "en-US",
        model: str = "latest_long",
        use_enhanced: bool = True,
        **config: any,
    ) -> None:
        """
        Initialize Google provider.

        Args:
            credentials_path: Path to service account JSON credentials
            language_code: Language code (en-US, es-ES, etc.)
            model: Model to use (latest_long, latest_short, etc.)
            use_enhanced: Use enhanced model
            **config: Additional configuration
        """
        super().__init__(**config)
        self.credentials_path = credentials_path
        self.language_code = language_code
        self.model = model
        self.use_enhanced = use_enhanced

        self.client: speech.SpeechAsyncClient | None = None
        self.stream_request_queue: asyncio.Queue[speech.StreamingRecognizeRequest] = (
            asyncio.Queue()
        )
        self.transcript_queue: asyncio.Queue[Transcript] = asyncio.Queue()
        self._streaming_task: asyncio.Task[None] | None = None

    async def connect(self) -> None:
        """Establish connection to Google Speech-to-Text."""
        try:
            logger.info("google_connecting", language=self.language_code, model=self.model)

            # Load credentials
            credentials = service_account.Credentials.from_service_account_file(
                self.credentials_path
            )

            # Create async client
            self.client = speech.SpeechAsyncClient(credentials=credentials)

            # Start streaming recognition task
            self._streaming_task = asyncio.create_task(self._streaming_recognize())

            self.connected = True
            logger.info("google_connected")

        except FileNotFoundError as e:
            logger.error("google_credentials_not_found", path=self.credentials_path)
            raise AuthenticationError(f"Credentials file not found: {e}") from e
        except Exception as e:
            logger.error("google_connection_failed", error=str(e))
            if "credentials" in str(e).lower() or "authentication" in str(e).lower():
                raise AuthenticationError(f"Google authentication failed: {e}") from e
            raise ProviderConnectionError(f"Failed to connect to Google: {e}") from e

    async def disconnect(self) -> None:
        """Close Google connection."""
        logger.info("google_disconnecting")

        if self._streaming_task:
            self._streaming_task.cancel()
            try:
                await self._streaming_task
            except asyncio.CancelledError:
                pass

        if self.client:
            try:
                await self.client.close()
            except Exception as e:
                logger.warning("google_disconnect_error", error=str(e))

        self.connected = False
        self.client = None
        logger.info("google_disconnected")

    async def stream_audio(self, audio_chunk: bytes) -> None:
        """
        Stream audio to Google.

        Args:
            audio_chunk: PCM16 audio data at 16kHz
        """
        if not self.connected:
            raise RuntimeError("Google provider not connected")

        try:
            request = speech.StreamingRecognizeRequest(audio_content=audio_chunk)
            await self.stream_request_queue.put(request)
            logger.debug("google_audio_queued", chunk_size=len(audio_chunk))

        except Exception as e:
            logger.error("google_audio_queue_failed", error=str(e))
            raise

    async def receive_transcripts(self) -> AsyncIterator[Transcript]:
        """
        Receive transcripts from Google.

        Yields:
            Transcript: Transcription results
        """
        if not self.connected:
            raise RuntimeError("Google provider not connected")

        logger.info("google_receiving_transcripts")

        while self.connected:
            try:
                transcript = await asyncio.wait_for(self.transcript_queue.get(), timeout=1.0)
                yield transcript
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error("google_receive_error", error=str(e))
                break

    async def _streaming_recognize(self) -> None:
        """Background task for streaming recognition."""
        try:
            assert self.client is not None

            # Configure recognition
            config = speech.RecognitionConfig(
                encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
                sample_rate_hertz=16000,
                language_code=self.language_code,
                model=self.model,
                use_enhanced=self.use_enhanced,
                enable_automatic_punctuation=True,
            )

            streaming_config = speech.StreamingRecognitionConfig(
                config=config,
                interim_results=True,
            )

            # Create initial request with config
            config_request = speech.StreamingRecognizeRequest(streaming_config=streaming_config)

            # Generator to yield requests
            async def request_generator() -> AsyncIterator[speech.StreamingRecognizeRequest]:
                yield config_request
                while self.connected:
                    try:
                        request = await asyncio.wait_for(
                            self.stream_request_queue.get(), timeout=0.1
                        )
                        yield request
                    except asyncio.TimeoutError:
                        continue

            # Start streaming recognition
            responses = await self.client.streaming_recognize(requests=request_generator())

            # Process responses
            async for response in responses:
                if not response.results:
                    continue

                for result in response.results:
                    if not result.alternatives:
                        continue

                    alternative = result.alternatives[0]
                    text = alternative.transcript

                    if not text.strip():
                        continue

                    is_final = result.is_final
                    confidence = alternative.confidence if is_final else None

                    transcript = Transcript(
                        text=text,
                        is_final=is_final,
                        confidence=confidence,
                        language=self.language_code,
                    )

                    await self.transcript_queue.put(transcript)

                    logger.debug(
                        "google_transcript_received",
                        text=text[:50],
                        is_final=is_final,
                        confidence=confidence,
                    )

        except asyncio.CancelledError:
            logger.info("google_streaming_task_cancelled")
        except Exception as e:
            logger.error("google_streaming_task_error", error=str(e))
            self.connected = False
