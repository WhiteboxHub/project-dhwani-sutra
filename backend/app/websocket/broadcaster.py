"""Broadcasting utilities for multi-client transcript distribution."""

import asyncio
import json
from typing import Any

from fastapi import WebSocket

from app.providers.base import Transcript
from app.utils.logging import get_logger

logger = get_logger(__name__)


class TranscriptBroadcaster:
    """Handles broadcasting transcripts to multiple WebSocket clients."""

    @staticmethod
    async def broadcast_transcript(
        receivers: list[WebSocket],
        transcript: Transcript,
        session_id: str,
    ) -> None:
        """
        Broadcast transcript to all connected receivers.

        Args:
            receivers: List of receiver WebSocket connections
            transcript: Transcript to broadcast
            session_id: Session identifier
        """
        if not receivers:
            logger.debug("no_receivers_to_broadcast", session_id=session_id)
            return

        message = TranscriptBroadcaster._format_transcript_message(transcript, session_id)

        # Broadcast to all receivers concurrently
        tasks = [
            TranscriptBroadcaster._send_to_receiver(receiver, message)
            for receiver in receivers
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Log any failures
        failures = sum(1 for r in results if isinstance(r, Exception))
        if failures > 0:
            logger.warning(
                "broadcast_failures",
                session_id=session_id,
                failures=failures,
                total=len(receivers),
            )

    @staticmethod
    def _format_transcript_message(transcript: Transcript, session_id: str) -> str:
        """
        Format transcript as JSON message.

        Args:
            transcript: Transcript to format
            session_id: Session identifier

        Returns:
            JSON string
        """
        message_type = "transcript_final" if transcript.is_final else "transcript_partial"

        message = {
            "type": message_type,
            "session_id": session_id,
            "text": transcript.text,
            "is_final": transcript.is_final,
            "confidence": transcript.confidence,
            "language": transcript.language,
            "timestamp": asyncio.get_event_loop().time(),
        }

        if transcript.metadata:
            message["metadata"] = transcript.metadata

        return json.dumps(message)

    @staticmethod
    async def _send_to_receiver(receiver: WebSocket, message: str) -> None:
        """
        Send message to a single receiver.

        Args:
            receiver: WebSocket connection
            message: Message to send
        """
        try:
            await receiver.send_text(message)
            logger.debug("message_sent_to_receiver")
        except Exception as e:
            logger.error("receiver_send_failed", error=str(e))
            raise

    @staticmethod
    async def broadcast_status(
        receivers: list[WebSocket],
        status: str,
        session_id: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        """
        Broadcast status message to all receivers.

        Args:
            receivers: List of receiver WebSocket connections
            status: Status message
            session_id: Session identifier
            details: Optional additional details
        """
        message = {
            "type": "status",
            "session_id": session_id,
            "status": status,
            "timestamp": asyncio.get_event_loop().time(),
        }

        if details:
            message["details"] = details

        message_str = json.dumps(message)

        tasks = [
            TranscriptBroadcaster._send_to_receiver(receiver, message_str)
            for receiver in receivers
        ]

        await asyncio.gather(*tasks, return_exceptions=True)

    @staticmethod
    async def broadcast_error(
        receivers: list[WebSocket],
        error_message: str,
        session_id: str,
        error_code: str | None = None,
    ) -> None:
        """
        Broadcast error message to all receivers.

        Args:
            receivers: List of receiver WebSocket connections
            error_message: Error message
            session_id: Session identifier
            error_code: Optional error code
        """
        message = {
            "type": "error",
            "session_id": session_id,
            "message": error_message,
            "timestamp": asyncio.get_event_loop().time(),
        }

        if error_code:
            message["code"] = error_code

        message_str = json.dumps(message)

        tasks = [
            TranscriptBroadcaster._send_to_receiver(receiver, message_str)
            for receiver in receivers
        ]

        await asyncio.gather(*tasks, return_exceptions=True)
