"""WebSocket gateway for audio streaming and transcript broadcasting."""

import asyncio
import json
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.websockets import WebSocketState

from app.config import get_config
from app.providers.factory import get_provider
from app.utils.logging import get_logger, set_correlation_id
from app.websocket.broadcaster import TranscriptBroadcaster
from app.websocket.session import SessionManager, SessionState

logger = get_logger(__name__)

# Create router
router = APIRouter()

# Global session manager (will be initialized in lifespan)
session_manager: SessionManager | None = None


def get_session_manager() -> SessionManager:
    """Get or create global session manager."""
    global session_manager
    if session_manager is None:
        config = get_config()
        session_manager = SessionManager(
            max_sessions=config.session.max_concurrent,
            max_age_seconds=config.session.max_duration_seconds,
            max_idle_seconds=config.session.idle_timeout_seconds,
            cleanup_interval_seconds=config.session.cleanup_interval_seconds,
        )
    return session_manager


@router.websocket("/ws/sender")
async def sender_endpoint(websocket: WebSocket) -> None:
    """
    WebSocket endpoint for audio sender (microphone input).

    Protocol:
    1. Client sends: {"type": "init", "session_id": "optional"}
    2. Server responds: {"type": "session_created", "session_id": "..."}
    3. Client sends binary audio chunks
    4. Server streams to STT provider
    """
    await websocket.accept()
    correlation_id = set_correlation_id()

    logger.info("sender_connected", correlation_id=correlation_id)

    session_id = None
    session = None
    config = get_config()
    manager = get_session_manager()

    try:
        # Wait for initialization message
        init_message = await websocket.receive_json()

        if init_message.get("type") != "init":
            await websocket.send_json({"type": "error", "message": "Expected init message"})
            await websocket.close()
            return

        # Create session with provider
        provider = get_provider(config)
        await provider.connect()

        session = manager.create_session(provider)
        session.sender = websocket
        session.state = SessionState.ACTIVE
        session_id = session.session_id

        logger.info("session_initialized", session_id=session_id, provider=config.provider)

        # Send session info to client
        await websocket.send_json(
            {
                "type": "session_created",
                "session_id": session_id,
                "provider": config.provider,
            }
        )

        # Start transcription task
        transcription_task = asyncio.create_task(
            _transcription_worker(session, provider)
        )

        # Handle incoming audio
        while True:
            data = await websocket.receive()

            if "bytes" in data:
                # Audio chunk received
                audio_chunk = data["bytes"]
                await session.audio_buffer.add_chunk(audio_chunk)
                session.update_activity()

                logger.debug(
                    "audio_received",
                    session_id=session_id,
                    chunk_size=len(audio_chunk),
                )

            elif "text" in data:
                # Handle control messages
                try:
                    message = json.loads(data["text"])
                    await _handle_sender_message(session, message)
                except json.JSONDecodeError:
                    logger.warning("invalid_json_from_sender", session_id=session_id)

    except WebSocketDisconnect:
        logger.info("sender_disconnected", session_id=session_id)
    except Exception as e:
        logger.error("sender_error", session_id=session_id, error=str(e))
    finally:
        # Cleanup
        if session_id and manager:
            await manager.remove_session(session_id)


@router.websocket("/ws/receiver/{session_id}")
async def receiver_endpoint(websocket: WebSocket, session_id: str) -> None:
    """
    WebSocket endpoint for transcript receiver.

    Args:
        websocket: WebSocket connection
        session_id: Session to subscribe to
    """
    await websocket.accept()
    correlation_id = set_correlation_id()

    logger.info(
        "receiver_connected",
        session_id=session_id,
        correlation_id=correlation_id,
    )

    manager = get_session_manager()
    session = manager.get_session(session_id)

    if not session:
        await websocket.send_json(
            {"type": "error", "message": f"Session {session_id} not found"}
        )
        await websocket.close()
        return

    # Add receiver to session
    session.add_receiver(websocket)

    try:
        # Send connection confirmation
        await websocket.send_json(
            {
                "type": "receiver_connected",
                "session_id": session_id,
            }
        )

        # Keep connection alive
        while websocket.client_state == WebSocketState.CONNECTED:
            try:
                # Wait for messages (keepalive or control)
                message = await asyncio.wait_for(
                    websocket.receive_json(),
                    timeout=30.0,
                )
                logger.debug("receiver_message", session_id=session_id, message=message)
            except asyncio.TimeoutError:
                # Send ping to keep connection alive
                await websocket.send_json({"type": "ping"})

    except WebSocketDisconnect:
        logger.info("receiver_disconnected", session_id=session_id)
    except Exception as e:
        logger.error("receiver_error", session_id=session_id, error=str(e))
    finally:
        # Remove receiver from session
        if session:
            session.remove_receiver(websocket)


async def _transcription_worker(session: Any, provider: Any) -> None:
    """
    Background worker that processes audio and broadcasts transcripts.

    Args:
        session: Session object
        provider: STT provider
    """
    logger.info("transcription_worker_started", session_id=session.session_id)

    try:
        # Process audio chunks
        audio_task = asyncio.create_task(_stream_audio_to_provider(session, provider))

        # Receive and broadcast transcripts
        async for transcript in provider.receive_transcripts():
            logger.info(
                "transcript_received",
                session_id=session.session_id,
                text=transcript.text[:50],
                is_final=transcript.is_final,
            )

            # Broadcast to all receivers
            await TranscriptBroadcaster.broadcast_transcript(
                session.receivers,
                transcript,
                session.session_id,
            )

            session.update_activity()

    except asyncio.CancelledError:
        logger.info("transcription_worker_cancelled", session_id=session.session_id)
    except Exception as e:
        logger.error(
            "transcription_worker_error",
            session_id=session.session_id,
            error=str(e),
        )
        # Broadcast error to receivers
        await TranscriptBroadcaster.broadcast_error(
            session.receivers,
            f"Transcription error: {str(e)}",
            session.session_id,
        )
    finally:
        logger.info("transcription_worker_stopped", session_id=session.session_id)


async def _stream_audio_to_provider(session: Any, provider: Any) -> None:
    """
    Stream audio chunks from buffer to provider.

    Args:
        session: Session object
        provider: STT provider
    """
    try:
        async for chunk in session.audio_buffer.get_chunks():
            await provider.stream_audio(chunk)
            logger.debug(
                "audio_sent_to_provider",
                session_id=session.session_id,
                chunk_size=len(chunk),
            )
    except asyncio.CancelledError:
        logger.info("audio_streaming_cancelled", session_id=session.session_id)
    except Exception as e:
        logger.error(
            "audio_streaming_error",
            session_id=session.session_id,
            error=str(e),
        )


async def _handle_sender_message(session: Any, message: dict[str, Any]) -> None:
    """
    Handle control messages from sender.

    Args:
        session: Session object
        message: Message data
    """
    message_type = message.get("type")

    if message_type == "pause":
        session.state = SessionState.PAUSED
        logger.info("session_paused", session_id=session.session_id)
        await TranscriptBroadcaster.broadcast_status(
            session.receivers,
            "paused",
            session.session_id,
        )

    elif message_type == "resume":
        session.state = SessionState.ACTIVE
        logger.info("session_resumed", session_id=session.session_id)
        await TranscriptBroadcaster.broadcast_status(
            session.receivers,
            "active",
            session.session_id,
        )

    elif message_type == "end":
        logger.info("session_end_requested", session_id=session.session_id)
        await session.close()

    else:
        logger.warning(
            "unknown_message_type",
            session_id=session.session_id,
            message_type=message_type,
        )
