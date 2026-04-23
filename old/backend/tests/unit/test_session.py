"""Unit tests for session management."""

import asyncio

import pytest

from app.websocket.session import Session, SessionManager, SessionState


class TestSession:
    """Test session lifecycle."""

    @pytest.mark.asyncio
    async def test_session_creation(self, mock_provider):
        """Test creating a session."""
        session = Session(session_id="test-123", provider=mock_provider)

        assert session.session_id == "test-123"
        assert session.state == SessionState.INITIALIZING
        assert session.provider == mock_provider
        assert len(session.receivers) == 0

    @pytest.mark.asyncio
    async def test_session_age(self):
        """Test session age tracking."""
        session = Session(session_id="test-123")

        await asyncio.sleep(0.1)
        age = session.get_age_seconds()

        assert age >= 0.1
        assert age < 1.0

    @pytest.mark.asyncio
    async def test_session_idle_time(self):
        """Test idle time tracking."""
        session = Session(session_id="test-123")

        await asyncio.sleep(0.1)
        session.update_activity()

        idle = session.get_idle_seconds()
        assert idle < 0.1

    @pytest.mark.asyncio
    async def test_session_expiry(self):
        """Test session expiry check."""
        session = Session(session_id="test-123")

        # Not expired with large limits
        assert not session.is_expired(max_age=1000, max_idle=1000)

        # Expired by age
        assert session.is_expired(max_age=0, max_idle=1000)

        # Expired by idle
        await asyncio.sleep(0.1)
        assert session.is_expired(max_age=1000, max_idle=0.05)

    @pytest.mark.asyncio
    async def test_session_close(self, mock_provider):
        """Test closing a session."""
        session = Session(session_id="test-123", provider=mock_provider)
        session.state = SessionState.ACTIVE

        await session.close()

        assert session.state == SessionState.CLOSED


class TestSessionManager:
    """Test session manager."""

    @pytest.mark.asyncio
    async def test_manager_initialization(self):
        """Test manager initialization."""
        manager = SessionManager(max_sessions=5)

        assert manager.max_sessions == 5
        assert len(manager.sessions) == 0

    @pytest.mark.asyncio
    async def test_create_session(self, mock_provider):
        """Test creating a session."""
        manager = SessionManager()
        session = manager.create_session(mock_provider)

        assert session.session_id is not None
        assert session in manager.sessions.values()
        assert len(manager.sessions) == 1

    @pytest.mark.asyncio
    async def test_get_session(self, mock_provider):
        """Test getting a session by ID."""
        manager = SessionManager()
        session = manager.create_session(mock_provider)

        retrieved = manager.get_session(session.session_id)

        assert retrieved == session

    @pytest.mark.asyncio
    async def test_get_nonexistent_session(self):
        """Test getting a session that doesn't exist."""
        manager = SessionManager()
        session = manager.get_session("nonexistent")

        assert session is None

    @pytest.mark.asyncio
    async def test_remove_session(self, mock_provider):
        """Test removing a session."""
        manager = SessionManager()
        session = manager.create_session(mock_provider)
        session_id = session.session_id

        await manager.remove_session(session_id)

        assert session_id not in manager.sessions
        assert len(manager.sessions) == 0

    @pytest.mark.asyncio
    async def test_max_sessions_limit(self, mock_provider):
        """Test that max sessions limit is enforced."""
        manager = SessionManager(max_sessions=2)

        # Create max sessions
        manager.create_session(mock_provider)
        manager.create_session(mock_provider)

        # Try to create one more
        with pytest.raises(RuntimeError, match="Maximum number of sessions"):
            manager.create_session(mock_provider)

    @pytest.mark.asyncio
    async def test_cleanup_expired_sessions(self, mock_provider):
        """Test cleanup of expired sessions."""
        manager = SessionManager(max_age_seconds=0.2, max_idle_seconds=0.2)

        # Create session
        session = manager.create_session(mock_provider)
        session_id = session.session_id

        # Wait for expiry
        await asyncio.sleep(0.3)

        # Run cleanup
        await manager.cleanup_expired_sessions()

        # Session should be removed
        assert session_id not in manager.sessions

    @pytest.mark.asyncio
    async def test_cleanup_task(self, mock_provider):
        """Test automatic cleanup task."""
        manager = SessionManager(
            max_age_seconds=0.1,
            max_idle_seconds=0.1,
            cleanup_interval_seconds=0.2,
        )

        # Start cleanup task
        await manager.start_cleanup_task()

        # Create expired session
        session = manager.create_session(mock_provider)
        session_id = session.session_id

        # Wait for cleanup
        await asyncio.sleep(0.4)

        # Session should be cleaned up
        assert session_id not in manager.sessions

        # Stop cleanup task
        await manager.stop_cleanup_task()

    @pytest.mark.asyncio
    async def test_close_all_sessions(self, mock_provider):
        """Test closing all sessions."""
        manager = SessionManager()

        # Create multiple sessions
        for _ in range(3):
            manager.create_session(mock_provider)

        assert len(manager.sessions) == 3

        # Close all
        await manager.close_all()

        assert len(manager.sessions) == 0

    @pytest.mark.asyncio
    async def test_get_stats(self, mock_provider):
        """Test getting session statistics."""
        manager = SessionManager(max_sessions=10)

        # Create some sessions
        for _ in range(3):
            manager.create_session(mock_provider)

        stats = manager.get_stats()

        assert stats["total_sessions"] == 3
        assert stats["max_sessions"] == 10
        assert "sessions_by_state" in stats
