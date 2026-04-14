"""Retry and backoff utilities."""

import asyncio
from typing import Any, Callable, TypeVar

from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.utils.logging import get_logger

T = TypeVar("T")
logger = get_logger(__name__)


async def retry_with_backoff(
    func: Callable[..., Any],
    *args: Any,
    max_attempts: int = 3,
    min_wait: float = 1.0,
    max_wait: float = 10.0,
    exceptions: tuple[type[Exception], ...] = (Exception,),
    **kwargs: Any,
) -> Any:
    """
    Retry an async function with exponential backoff.

    Args:
        func: Async function to retry
        *args: Positional arguments for func
        max_attempts: Maximum number of retry attempts
        min_wait: Minimum wait time between retries (seconds)
        max_wait: Maximum wait time between retries (seconds)
        exceptions: Tuple of exception types to retry on
        **kwargs: Keyword arguments for func

    Returns:
        Result of the function call

    Raises:
        RetryError: If all retry attempts fail
    """
    async for attempt in AsyncRetrying(
        retry=retry_if_exception_type(exceptions),
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(min=min_wait, max=max_wait),
        reraise=True,
    ):
        with attempt:
            logger.debug(
                "attempting_function_call",
                function=func.__name__,
                attempt=attempt.retry_state.attempt_number,
            )
            result = await func(*args, **kwargs)
            return result


class CircuitBreaker:
    """
    Circuit breaker pattern implementation for fault tolerance.

    The circuit breaker has three states:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Failure threshold exceeded, requests fail immediately
    - HALF_OPEN: Testing if service recovered, limited requests allowed
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        expected_exception: type[Exception] = Exception,
    ) -> None:
        """
        Initialize circuit breaker.

        Args:
            failure_threshold: Number of failures before opening circuit
            recovery_timeout: Seconds to wait before attempting recovery
            expected_exception: Exception type that triggers the breaker
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception

        self.failure_count = 0
        self.last_failure_time: float | None = None
        self.state: str = "CLOSED"  # CLOSED, OPEN, HALF_OPEN

        self.logger = get_logger(f"{__name__}.CircuitBreaker")

    async def call(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """
        Execute function through circuit breaker.

        Args:
            func: Async function to call
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            Result of function call

        Raises:
            Exception: If circuit is open or function raises
        """
        if self.state == "OPEN":
            if self._should_attempt_reset():
                self.state = "HALF_OPEN"
                self.logger.info("circuit_breaker_half_open", function=func.__name__)
            else:
                self.logger.warning("circuit_breaker_open", function=func.__name__)
                raise Exception("Circuit breaker is OPEN")

        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result
        except self.expected_exception as e:
            self._on_failure()
            raise e

    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset."""
        if self.last_failure_time is None:
            return True
        import time

        return (time.time() - self.last_failure_time) >= self.recovery_timeout

    def _on_success(self) -> None:
        """Handle successful function call."""
        if self.state == "HALF_OPEN":
            self.logger.info("circuit_breaker_closed")
            self.state = "CLOSED"
        self.failure_count = 0

    def _on_failure(self) -> None:
        """Handle failed function call."""
        import time

        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"
            self.logger.error(
                "circuit_breaker_open",
                failure_count=self.failure_count,
                threshold=self.failure_threshold,
            )

    def reset(self) -> None:
        """Manually reset the circuit breaker."""
        self.failure_count = 0
        self.state = "CLOSED"
        self.last_failure_time = None
        self.logger.info("circuit_breaker_reset")
