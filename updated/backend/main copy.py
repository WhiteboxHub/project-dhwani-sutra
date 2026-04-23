import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState
import uvicorn
from dotenv import load_dotenv

from utils import is_valid_webm, safe_send
from services import llm_cleaning
from providers import get_stt_provider
import os
app = FastAPI()
load_dotenv()

STT_PROVIDER= os.getenv("STT_PROVIDER", "openai").lower()

@app.websocket("/ws/stt")
async def websocket_stt(websocket: WebSocket, provider: str = None):
    await websocket.accept()

    audio_queue = asyncio.Queue()
    is_connected = True
    
    #   FIX 2: Store ORIGINAL transcripts for context, not cleaned versions
    raw_transcript_history = ""
    
    async def receive_audio():
        nonlocal is_connected
        try:
            while True:
                data = await websocket.receive_bytes()
                await audio_queue.put(data)
        except WebSocketDisconnect:
            print("🔌 Client disconnected")
        except Exception as e:
            print(f"  Receive error: {e}")
        finally:
            is_connected = False
            await audio_queue.put(None)

    active_provider = provider or os.getenv("STT_PROVIDER", "openai").lower()
    stt_provider_instance = get_stt_provider(active_provider)

    async def handler_callback(raw_text: str):
        nonlocal raw_transcript_history
        if not raw_text:
            return

        print(f"  Raw transcript: {raw_text}")

        # Update context with RAW transcript, not cleaned
        # This prevents feedback loop where cleaned text influences future cleaning
        raw_transcript_history = (raw_transcript_history + " " + raw_text)[-2000:]

        import uuid
        segment_id = str(uuid.uuid4())

        # Send raw text to frontend immediately
        await safe_send(websocket, {
            "type": "transcript_raw",
            "id": segment_id,
            "text": raw_text
        })

        # Define background task for cleaning
        async def clean_and_send(text_to_clean: str, history: str, sid: str):
            try:
                cleaned_val = await llm_cleaning(history, text_to_clean)
                print(f"  Cleaned transcript: {cleaned_val}")
                # Don't send [SILENCE] to frontend, just drop or send as empty?
                # The llm_cleaning returns "[SILENCE]" for hallucinations. We might want to pass it as "" 
                if cleaned_val == "[SILENCE]":
                     cleaned_val = ""
                await safe_send(websocket, {
                    "type": "transcript_cleaned",
                    "id": sid,
                    "text": cleaned_val
                })
            except Exception as e:
                print(f"  Error during LLM clean background task: {e}")

        # Kick off background cleaning task (does not block websocket)
        asyncio.create_task(clean_and_send(raw_text, raw_transcript_history, segment_id))

    async def run_provider():
        try:
            await stt_provider_instance.process_audio_stream(audio_queue, handler_callback)
        except Exception as e:
            print(f"  Provider error: {e}")

    # Create tasks for receiving and processing
    receive_task = asyncio.create_task(receive_audio())
    send_task = asyncio.create_task(run_provider())

    try:
        # Wait for either task to complete
        await asyncio.wait(
            [receive_task, send_task],
            return_when=asyncio.FIRST_COMPLETED
        )
    finally:
        print("  Cleaning up WebSocket tasks")

        # Cancel both tasks
        receive_task.cancel()
        send_task.cancel()

        # Wait for cancellation to complete
        try:
            await receive_task
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"  Receive task error during cleanup: {e}")

        try:
            await send_task
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"  Send task error during cleanup: {e}")

        # Close WebSocket if still open
        try:
            if websocket.application_state != WebSocketState.DISCONNECTED and websocket.client_state != WebSocketState.DISCONNECTED:
                await websocket.close()
        except RuntimeError:
            # Client already disconnected
            pass
        except Exception as e:
            print(f"  Error during websocket close: {e}")

        print("  WebSocket safely closed")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)