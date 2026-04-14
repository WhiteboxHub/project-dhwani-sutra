"""Session management for audio streaming."""

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from fastapi import WebSocket

from app.audio.buffer import AudioBuffer
from app.providers.base import STTProvider
from app.utils.logging import get_logger

logger = get_logger(__name__)


class SessionState(Enum):
    """Session lifecycle states."""

    INITIALIZING = "initializing"
    ACTIVE = "active"
    PAUSED = "paused"
    CLOSING = "closing"
    CLOSED = "closed"


@dataclass
class Session:
    """
    Represents an audio streaming session.

    A session connects:
    - One sender (audio input)
    - One STT provider
    - Multiple receivers (transcript output)
    """

    session_id: str
    created_at: float = field(default_factory=time.time)
    state: SessionState = SessionState.INITIALIZING

    # Connections
    sender: WebSocket | None = None
    receivers: list[WebSocket] = field(default_factory=list)

    # STT Provider
    provider: STTProvider | None = None

    # Audio buffering
    audio_buffer: AudioBuffer = field(default_factory=AudioBuffer)

    # Metadata
    last_activity: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    # Tasks
    _transcription_task: asyncio.Task[None] | None = None
    _broadcast_task: asyncio.Task[None] | None = None

    def update_activity(self) -> None:
        """Update last activity timestamp."""
        self.last_activity = time.time()

    def get_age_seconds(self) -> float:
        """Get session age in seconds."""
        return time.time() - self.created_at

    def get_idle_seconds(self) -> float:
        """Get idle time in seconds."""
        return time.time() - self.last_activity

    def is_expired(self, max_age: float, max_idle: float) -> bool:
        """
        Check if session is expired.

        Args:
            max_age: Maximum session age (seconds)
            max_idle: Maximum idle time (seconds)

        Returns:
            True if expired
        """
        return self.get_age_seconds() > max_age or self.get_idle_seconds() > max_idle

    def add_receiver(self, websocket: WebSocket) -> None:
        """Add a receiver to the session."""
        self.receivers.append(websocket)
        logger.info(
            "session_receiver_added",
            session_id=self.session_id,
            receiver_count=len(self.receivers),
        )

    def remove_receiver(self, websocket: WebSocket) -> None:
        """Remove a receiver from the session."""
        if websocket in self.receivers:
            self.receivers.remove(websocket)
            logger.info(
                "session_receiver_removed",
                session_id=self.session_id,
                receiver_count=len(self.receivers),
            )

    async def close(self) -> None:
        """Close the session and cleanup resources."""
        if self.state == SessionState.CLOSED:
            return

        logger.info("session_closing", session_id=self.session_id)
        self.state = SessionState.CLOSING

        # Cancel tasks
        if self._transcription_task:
            self._transcription_task.cancel()
            try:
                await self._transcription_task
            except asyncio.CancelledError:
                pass

        if self._broadcast_task:
            self._broadcast_task.cancel()
            try:
                await self._broadcast_task
            except asyncio.CancelledError:
                pass

        # Close provider
        if self.provider:
            try:
                await self.provider.disconnect()
            except Exception as e:
                logger.warning("session_provider_disconnect_error", error=str(e))

        # Close connections
        if self.sender:
            try:
                await self.sender.close()
            except Exception:
                pass

        for receiver in self.receivers:
            try:
                await receiver.close()
            except Exception:
                pass

        self.receivers.clear()
        self.audio_buffer.close()

        self.state = SessionState.CLOSED
        logger.info("session_closed", session_id=self.session_id)


class SessionManager:
    """
    Manages all active sessions.

    Responsibilities:
    - Session creation and cleanup
    - Session lookup
    - Periodic cleanup of expired sessions
    """

    def __init__(
        self,
        max_sessions: int = 100,
        max_age_seconds: float = 14400.0,  # 4 hours
        max_idle_seconds: float = 3600.0,  # 1 hour
        cleanup_interval_seconds: float = 60.0,
    ) -> None:
        """
        Initialize session manager.

        Args:
            max_sessions: Maximum concurrent sessions
            max_age_seconds: Maximum session age
            max_idle_seconds: Maximum idle time before cleanup
            cleanup_interval_seconds: Cleanup check interval
        """
        self.max_sessions = max_sessions
        self.max_age_seconds = max_age_seconds
        self.max_idle_seconds = max_idle_seconds
        self.cleanup_interval_seconds = cleanup_interval_seconds

        self.sessions: dict[str, Session] = {}
        self._cleanup_task: asyncio.Task[None] | None = None

        logger.info(
            "session_manager_initialized",
            max_sessions=max_sessions,
            max_age=max_age_seconds,
            max_idle=max_idle_seconds,
        )

    def create_session(self, provider: STTProvider) -> Session:
        """
        Create a new session.

        Args:
            provider: STT provider instance

        Returns:
            New session

        Raises:
            RuntimeError: If max sessions limit reached
        """
        if len(self.sessions) >= self.max_sessions:
            logger.error("session_limit_reached", current=len(self.sessions), max=self.max_sessions)
            raise RuntimeError("Maximum number of sessions reached")

        session_id = str(uuid.uuid4())
        session = Session(session_id=session_id, provider=provider)

        self.sessions[session_id] = session

        logger.info(
            "session_created",
            session_id=session_id,
            total_sessions=len(self.sessions),
        )

        return session

    def get_session(self, session_id: str) -> Session | None:
        """
        Get session by ID.

        Args:
            session_id: Session identifier

        Returns:
            Session or None if not found
        """
        return self.sessions.get(session_id)

    async def remove_session(self, session_id: str) -> None:
        """
        Remove and cleanup session.

        Args:
            session_id: Session identifier
        """
        session = self.sessions.pop(session_id, None)
        if session:
            await session.close()
            logger.info(
                "session_removed",
                session_id=session_id,
                remaining_sessions=len(self.sessions),
            )

    async def cleanup_expired_sessions(self) -> None:
        """Remove expired sessions."""
        expired = []

        for session_id, session in self.sessions.items():
            if session.is_expired(self.max_age_seconds, self.max_idle_seconds):
                expired.append(session_id)
                logger.info(
                    "session_expired",
                    session_id=session_id,
                    age=session.get_age_seconds(),
                    idle=session.get_idle_seconds(),
                )

        for session_id in expired:
            await self.remove_session(session_id)

        if expired:
            logger.info("expired_sessions_cleaned", count=len(expired))

    async def start_cleanup_task(self) -> None:
        """Start background cleanup task."""
        if self._cleanup_task is not None:
            return

        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("session_cleanup_task_started", interval=self.cleanup_interval_seconds)

    async def stop_cleanup_task(self) -> None:
        """Stop background cleanup task."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
            logger.info("session_cleanup_task_stopped")

    async def _cleanup_loop(self) -> None:
        """Background loop for cleanup."""
        try:
            while True:
                await asyncio.sleep(self.cleanup_interval_seconds)
                await self.cleanup_expired_sessions()
        except asyncio.CancelledError:
            logger.info("session_cleanup_loop_cancelled")
            raise

    async def close_all(self) -> None:
        """Close all sessions and cleanup."""
        logger.info("closing_all_sessions", count=len(self.sessions))

        await self.stop_cleanup_task()

        session_ids = list(self.sessions.keys())
        for session_id in session_ids:
            await self.remove_session(session_id)

        logger.info("all_sessions_closed")

    def get_stats(self) -> dict[str, Any]:
        """Get session statistics."""
        return {
            "total_sessions": len(self.sessions),
            "max_sessions": self.max_sessions,
            "sessions_by_state": {
                state.value: sum(1 for s in self.sessions.values() if s.state == state)
                for state in SessionState
            },
        }
