import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from starlette.websockets import WebSocketState
import uvicorn
from dotenv import load_dotenv
import os
import uuid
import json

from utils import is_valid_webm, safe_send
from services import normalize_text, should_invoke_gpt, llm_cleaning, validate_similarity
from providers import get_stt_provider
from latency_logger import latency_tracker

load_dotenv()

app = FastAPI()

allowed_origins_raw = os.getenv("ALLOWED_ORIGINS", "*")
if allowed_origins_raw == "*":
    allow_origins = ["*"]
    allow_credentials = False
else:
    allow_origins = [o.strip() for o in allowed_origins_raw.split(",") if o.strip()]
    allow_credentials = True

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

STT_PROVIDER = os.getenv("STT_PROVIDER", "openai").lower()

# Manage session broadcasts
class ConnectionManager:
    def __init__(self):
        self.active_listeners: dict[str, list[WebSocket]] = {}

    async def connect_listener(self, websocket: WebSocket, session_id: str):
        await websocket.accept()
        if session_id not in self.active_listeners:
            self.active_listeners[session_id] = []
        self.active_listeners[session_id].append(websocket)
        print(f"📡 Listener joined session: {session_id}")

    def disconnect_listener(self, websocket: WebSocket, session_id: str):
        if session_id in self.active_listeners:
            if websocket in self.active_listeners[session_id]:
                self.active_listeners[session_id].remove(websocket)
            if not self.active_listeners[session_id]:
                del self.active_listeners[session_id]
        print(f"🔌 Listener left session: {session_id}")

    async def broadcast_to_session(self, session_id: str, message: dict):
        if session_id in self.active_listeners:
            dead_sockets = []
            for connection in self.active_listeners[session_id]:
                try:
                    await safe_send(connection, message)
                except Exception:
                    dead_sockets.append(connection)
            for dead in dead_sockets:
                self.disconnect_listener(dead, session_id)

manager = ConnectionManager()


@app.websocket("/ws/listen/{session_id}")
async def websocket_listen(websocket: WebSocket, session_id: str):
    await manager.connect_listener(websocket, session_id)
    try:
        while True:
            # Process incoming telemetry messages from the listener frontend
            data = await websocket.receive_text()
            try:
                payload = json.loads(data)
                if payload.get("type") == "telemetry":
                    segment_id = payload.get("id")
                    listener_received = payload.get("listener_received_time")
                    rendered = payload.get("rendered_time")
                    latency_tracker.process_listener_telemetry(
                        session_id, segment_id, listener_received, rendered
                    )
            except Exception:
                pass
    except WebSocketDisconnect:
        manager.disconnect_listener(websocket, session_id)
    except Exception as e:
        print(f"Listener error: {e}")
        manager.disconnect_listener(websocket, session_id)


@app.websocket("/ws/stt/{session_id}")
async def websocket_stt(
    websocket: WebSocket,
    session_id: str,
    provider: str = None,
    openai_key: str = None,
    deepgram_key: str = None,
):
    await websocket.accept()
    latency_tracker.start_session(session_id)

    audio_queue = asyncio.Queue()
    is_connected = True
    
    # Store ORIGINAL transcripts for context, not cleaned versions
    raw_transcript_history = ""

    # Track active metadata for current audio chunk
    active_metadata = {
        "chunk_index": 0,
        "audio_created_time": 0.0,
        "audio_sent_time": 0.0,
        "backend_received_time": 0.0,
        "deepgram_forwarded_time": 0.0,
    }

    # Tracking the segment ID for the active/running stream
    active_segment_id = None
    
    async def receive_audio():
        nonlocal is_connected
        nonlocal active_metadata
        try:
            while True:
                msg = await websocket.receive()
                if "text" in msg:
                    try:
                        data = json.loads(msg["text"])
                        if data.get("type") == "chunk_metadata":
                            active_metadata.update({
                                "chunk_index": data.get("chunk_index", 0),
                                "audio_created_time": data.get("audio_created_time", 0.0),
                                "audio_sent_time": data.get("audio_sent_time", 0.0),
                            })
                    except Exception as e:
                        latency_tracker.log_error(session_id, "Receive Metadata JSON", str(e), active_metadata.get("chunk_index", 0))
                elif "bytes" in msg:
                    recv_time = latency_tracker.get_timestamp_ms()
                    active_metadata["backend_received_time"] = recv_time
                    audio_data = msg["bytes"]
                    await audio_queue.put((audio_data, active_metadata.copy()))
        except WebSocketDisconnect:
            print(f"🔌 Sender disconnected from session {session_id}")
        except Exception as e:
            print(f"  Receive error: {e}")
            latency_tracker.log_error(session_id, "Receive Audio Loop", str(e), active_metadata.get("chunk_index", 0))
        finally:
            is_connected = False
            await audio_queue.put(None)

    active_provider = provider or os.getenv("STT_PROVIDER", "openai").lower()
    stt_provider_instance = get_stt_provider(
        active_provider,
        openai_key=openai_key,
        deepgram_key=deepgram_key,
    )

    async def handler_callback(raw_text: str, is_final: bool, chunk_metadata: dict = None, dg_response_time: float = None):
        nonlocal raw_transcript_history
        nonlocal active_segment_id
        if not raw_text:
            return

        # Ensure we have a segment ID tracking this sentence
        if not active_segment_id:
            active_segment_id = str(uuid.uuid4())

        segment_id = active_segment_id

        # Fallbacks for metadata
        if not chunk_metadata:
            chunk_metadata = active_metadata.copy()
        if not dg_response_time:
            dg_response_time = latency_tracker.get_timestamp_ms()

        # Send raw text immediately (either interim or final raw)
        msg_raw = {
            "type": "transcript_raw",
            "id": segment_id,
            "text": raw_text,
            "is_final": is_final
        }

        # Send raw text to front-end sender
        await safe_send(websocket, msg_raw)
        # Broadcast to any active listeners
        await manager.broadcast_to_session(session_id, msg_raw)

        # Pipeline 2: Finalization Pipeline (only on is_final=True)
        if is_final:
            print(f"  Final raw transcript [{session_id}]: {raw_text}")
            
            # Context window update
            raw_transcript_history = (raw_transcript_history + " " + raw_text)[-2000:]
            
            # Record start timestamps for instrumentation
            latency_tracker.record_segment_start(segment_id, chunk_metadata, dg_response_time)

            # Reset active segment ID for the next sentence
            active_segment_id = None

            async def finalize_and_send(text_to_finalize: str, history: str, sid: str):
                try:
                    # 1. Technical Dictionary Normalization
                    dict_start = latency_tracker.get_timestamp_ms()
                    normalized_val, dict_modified = normalize_text(text_to_finalize)
                    dict_end = latency_tracker.get_timestamp_ms()

                    # 2. Validation Layer / Decision Engine
                    val_start = latency_tracker.get_timestamp_ms()
                    gpt_needed = should_invoke_gpt(text_to_finalize, normalized_val)
                    val_end = latency_tracker.get_timestamp_ms()

                    gpt_started = 0.0
                    gpt_completed = 0.0
                    final_val = normalized_val

                    # 3. Optional GPT Connection
                    if gpt_needed:
                        gpt_started = latency_tracker.get_timestamp_ms()
                        try:
                            gpt_cleaned = await llm_cleaning(history, normalized_val)
                        except Exception as e:
                            print(f"🔴 [CRITICAL] OpenAI API Key Error or Quota Exceeded: {e}")
                            await safe_send(websocket, {
                                "type": "error",
                                "message": f"OpenAI API Key expired or has insufficient quota: {e}"
                            })
                            gpt_cleaned = normalized_val
                        gpt_completed = latency_tracker.get_timestamp_ms()

                        if gpt_cleaned == "[SILENCE]":
                            final_val = text_to_finalize
                        else:
                            # 4. Similarity Validation
                            if validate_similarity(normalized_val, gpt_cleaned):
                                final_val = gpt_cleaned
                            else:
                                print(f"⚠️ Similarity check failed. Using normalized text instead of GPT.")
                                final_val = normalized_val
                    else:
                        print(f"⚡ Skipping GPT call (normalized text is clean and matches criteria)")

                    # Clean grammatical artifacts if needed
                    if final_val and final_val != "[SILENCE]":
                        final_val = final_val.replace(". and", ", and")
                        final_val = final_val.replace(". And", ", and")
                        final_val = final_val.replace(" .", ".")
                        final_val = final_val.replace(" ,", ",")

                    msg_cleaned = {
                        "type": "transcript_cleaned",
                        "id": sid,
                        "text": final_val
                    }

                    # Send to clients
                    await safe_send(websocket, msg_cleaned)
                    await manager.broadcast_to_session(session_id, msg_cleaned)

                    # Log latency telemetry
                    broadcast_sent = latency_tracker.get_timestamp_ms()
                    latency_tracker.record_pipeline_metrics(
                        sid, dict_start, dict_end, val_start, val_end,
                        gpt_started, gpt_completed, gpt_needed, broadcast_sent
                    )

                except Exception as e:
                    print(f"  Error in finalization pipeline: {e}")
                    latency_tracker.log_error(session_id, "Finalization Pipeline", str(e), chunk_metadata.get("chunk_index", 0))

            asyncio.create_task(finalize_and_send(raw_text, raw_transcript_history, segment_id))

    async def run_provider():
        try:
            await stt_provider_instance.process_audio_stream(audio_queue, handler_callback)
        except Exception as e:
            err_msg = str(e)
            print(f"  Provider error: {err_msg}")
            latency_tracker.log_error(session_id, "STT Provider Loop", err_msg, active_metadata.get("chunk_index", 0))
            
            user_friendly_error = f"STT Provider error: {err_msg}"
            if "unauthorized" in err_msg.lower() or "authentication" in err_msg.lower() or "401" in err_msg:
                user_friendly_error = "Deepgram API key is invalid or has expired."
            
            await safe_send(websocket, {
                "type": "error",
                "message": user_friendly_error
            })

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
        print(f"  Cleaning up WebSocket tasks for session {session_id}")

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
            pass
        except Exception as e:
            print(f"  Error during websocket close: {e}")

        print("  WebSocket safely closed")
        latency_tracker.end_session(session_id)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)