import io
import asyncio
import os
from openai import OpenAI
from utils import is_hallucination, is_valid_webm
from .base import STTProvider
from latency_logger import latency_tracker

class OpenAIProvider(STTProvider):
    def __init__(self, api_key: str = None):
        key = api_key or os.getenv("OPEN_AI_KEY")
        self.client = OpenAI(api_key=key)

    async def process_audio_stream(
        self,
        audio_queue: asyncio.Queue,
        handler_callback
    ):
        while True:
            try:
                # Wait for next audio chunk
                item = await audio_queue.get()

                if item is None:
                    break  # Disconnected

                chunk, metadata = item

                # Skip tiny chunks (likely silence or noise)
                if len(chunk) < 500:
                    print(f"⏭️  Skipping small chunk: {len(chunk)} bytes")
                    continue

                if not is_valid_webm(chunk):
                    print(f"  Invalid WebM chunk (missing EBML header): {len(chunk)} bytes")
                    continue

                # Record OpenAI forward time
                metadata["deepgram_forwarded_time"] = latency_tracker.get_timestamp_ms()

                # Transcribe the audio
                raw_text = await self._transcribe_audio(chunk)
                if raw_text:
                    dg_response_time = latency_tracker.get_timestamp_ms()
                    # OpenAI chunks are always fully finalized segments (is_final=True)
                    await handler_callback(raw_text, True, metadata, dg_response_time)

            except Exception as e:
                print(f"  OpenAI provider error: {e}")

    async def _transcribe_audio(self, audio_data: bytes) -> str:
        try:
            print(f" Transcribing {len(audio_data)} bytes")
            
            audio_file = io.BytesIO(audio_data)
            audio_file.name = "audio.webm"

            response = await asyncio.to_thread(
                self.client.audio.transcriptions.create,
                model="whisper-1",
                file=audio_file,
                response_format="text",
                language="en",
                prompt="LangChain, LangGraph, MilvusDB, BM25, Agentic AI, RAG, Prometheus, Grafana, AWS CloudWatch, Docker, Kubernetes.",
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
