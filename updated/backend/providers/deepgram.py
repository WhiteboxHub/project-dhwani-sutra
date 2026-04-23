import asyncio
import threading
from deepgram import DeepgramClient
from deepgram.core.events import EventType
from .base import STTProvider

class DeepgramProvider(STTProvider):
    def __init__(self):
        # DeepgramClient will automatically use DEEPGRAM_API_KEY from env
        self.deepgram = DeepgramClient()

    async def process_audio_stream(
        self,
        audio_queue: asyncio.Queue,
        handler_callback
    ):
        loop = asyncio.get_running_loop()
        
        try:
            # Create a websocket connection to Deepgram
            with self.deepgram.listen.v1.connect(model="nova-3") as connection:

                def on_message(*args, **kwargs) -> None:
                    # Depending on python SDK version, signature can be `on_message(self, message, **kwargs)` or `on_message(message)`
                    message = args[1] if len(args) > 1 else args[0]
                    
                    if hasattr(message, 'channel') and hasattr(message.channel, 'alternatives'):
                        sentence = message.channel.alternatives[0].transcript
                        if len(sentence) == 0:
                            return
                        print(f"Deepgram raw text: {sentence}")
                        # Execute the async handler callback
                        asyncio.run_coroutine_threadsafe(handler_callback(sentence), loop)

                def on_error(*args, **kwargs):
                    error = args[1] if len(args) > 1 else args[0]
                    print(f"Deepgram Error: {error}")

                connection.on(EventType.MESSAGE, on_message)
                connection.on(EventType.ERROR, on_error)

                # Thread logic based on Deepgram doc snippet
                def listening_thread():
                    try:
                        connection.start_listening()
                    except Exception as e:
                        print(f"Error in listening thread: {e}")

                listen_thread = threading.Thread(target=listening_thread)
                listen_thread.start()

                # Process the audio queue and stream data
                while True:
                    try:
                        chunk = await audio_queue.get()
                        
                        if chunk is None: # EOF
                            break
                            
                        # WebM chunk to Deepgram
                        connection.send_media(chunk)

                    except Exception as e:
                        print(f"Error in Deepgram data stream: {e}")
                        break
                        
                listen_thread.join(timeout=5.0)
                print("Deepgram streaming finished.")

        except Exception as e:
            print(f"Could not open Deepgram socket: {e}")
