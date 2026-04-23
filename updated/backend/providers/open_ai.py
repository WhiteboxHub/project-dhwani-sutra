import io
import asyncio
import os
from openai import OpenAI
from utils import is_hallucination, is_valid_webm
from .base import STTProvider

class OpenAIProvider(STTProvider):
    def __init__(self):
        key = os.getenv("OPEN_AI_KEY")
        self.client = OpenAI(api_key=key)

    async def process_audio_stream(
        self,
        audio_queue: asyncio.Queue,
        handler_callback
    ):
        while True:
            try:
                # Wait for next audio chunk
                chunk = await audio_queue.get()

                if chunk is None:
                    break  # Disconnected

                # Skip tiny chunks (likely silence or noise)
                if len(chunk) < 500:
                    print(f"⏭️  Skipping small chunk: {len(chunk)} bytes")
                    continue

                if not is_valid_webm(chunk):
                    print(f"  Invalid WebM chunk (missing EBML header): {len(chunk)} bytes")
                    continue

                # Transcribe the audio
                raw_text = await self._transcribe_audio(chunk)
                if raw_text:
                    await handler_callback(raw_text)

            except Exception as e:
                print(f"  OpenAI provider error: {e}")

    async def _transcribe_audio(self, audio_data: bytes) -> str:
        try:
            print(f" Transcribing {len(audio_data)} bytes")
            
            audio_file = io.BytesIO(audio_data)
            audio_file.name = "audio.webm"

            # Run blocking API call in thread pool
            response = await asyncio.to_thread(
                self.client.audio.transcriptions.create,
                model="whisper-1",
                file=audio_file,
                response_format="text",
                language="en",
                timeout=10
            )

            text = response.strip() if isinstance(response, str) else response.text.strip()

            if not text:
                print("   Empty transcription (likely silence)")
                return None
            if not text or is_hallucination(text):
                print(f"   Skipping hallucination/silence: '{text}'")
                return None
            return text

        except asyncio.TimeoutError:
            print("   Transcription timeout")
            return None
        except Exception as e:
            print(f"  Transcription error: {e}")
            return None
