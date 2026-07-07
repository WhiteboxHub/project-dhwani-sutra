import asyncio
import os
import threading
from deepgram import DeepgramClient
from deepgram.listen.v1.socket_client import EventType
from .base import STTProvider
from latency_logger import latency_tracker


class DeepgramProvider(STTProvider):
    def __init__(self, api_key: str = None):
        key = api_key or os.getenv("DEEPGRAM_API_KEY")
        self.deepgram = DeepgramClient(api_key=key)
        self.latest_chunk_metadata = {}

    async def process_audio_stream(
        self,
        audio_queue: asyncio.Queue,
        handler_callback
    ):
        loop = asyncio.get_running_loop()

        try:
            with self.deepgram.listen.v1.connect(
                model="nova-3",
                punctuate=True,
                interim_results=True,
                endpointing=500,
                language="en",
                keyterm=["LangChain", "LangGraph", "land graph", "Landra", "MilvusDB", "BM25", "Agentic AI", "Agentic", "RAG", "Prometheus", "Grafana", "CloudWatch"]
            ) as connection:

                def on_message(*args, **kwargs):
                    message = args[1] if len(args) > 1 else args[0]
                    try:
                        if hasattr(message, "channel") and hasattr(message.channel, "alternatives"):
                            sentence = message.channel.alternatives[0].transcript
                            if sentence and sentence.strip():
                                is_final = getattr(message, "is_final", False)
                                # speech_final is also a useful fallback for end-of-utterance detection
                                speech_final = getattr(message, "speech_final", False)
                                is_segment_final = is_final or speech_final
                                
                                print(f"Deepgram transcript (final={is_segment_final}): {sentence}")
                                dg_response_time = latency_tracker.get_timestamp_ms()
                                meta_copy = self.latest_chunk_metadata.copy()
                                asyncio.run_coroutine_threadsafe(
                                    handler_callback(sentence, is_segment_final, meta_copy, dg_response_time), loop
                                )
                    except Exception as e:
                        print(f"Deepgram message parse error: {e}")

                def on_error(*args, **kwargs):
                    error = args[1] if len(args) > 1 else args[0]
                    print(f"Deepgram Error: {error}")

                connection.on(EventType.MESSAGE, on_message)
                connection.on(EventType.ERROR, on_error)

                listen_thread = threading.Thread(
                    target=connection.start_listening, daemon=True
                )
                listen_thread.start()

                while True:
                    try:
                        item = await audio_queue.get()

                        if item is None:  # EOF / sender disconnected
                            break

                        audio_data, metadata = item
                        metadata["deepgram_forwarded_time"] = latency_tracker.get_timestamp_ms()
                        self.latest_chunk_metadata = metadata

                        connection.send_media(audio_data)

                    except Exception as e:
                        print(f"Error sending audio to Deepgram: {e}")
                        break

                listen_thread.join(timeout=3.0)
                print("Deepgram streaming finished.")

        except Exception as e:
            print(f"Could not open Deepgram socket: {e}")
