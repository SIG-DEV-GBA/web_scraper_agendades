"""Retry logic with exponential backoff and jitter."""

import asyncio
import random
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import wraps
from typing import Any, ParamSpec, TypeVar

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from src.logging import get_logger

logger = get_logger(__name__)

P = ParamSpec("P")
T = TypeVar("T")


# Exceptions that should trigger a retry
RETRYABLE_EXCEPTIONS = (
    ConnectionError,
    TimeoutError,
    asyncio.TimeoutError,
)


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""

    max_attempts: int = 3
    initial_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter: float = 1.0
    retryable_status_codes: tuple[int, ...] = field(
        default_factory=lambda: (429, 500, 502, 503, 504)
    )
    retryable_exceptions: tuple[type[Exception], ...] = field(
        default_factory=lambda: RETRYABLE_EXCEPTIONS
    )


class RetryableHTTPError(Exception):
    """HTTP error that can be retried."""

    def __init__(self, status_code: int, message: str = ""):
        self.status_code = status_code
        self.message = message
        super().__init__(f"HTTP {status_code}: {message}")


class NonRetryableError(Exception):
    """Error that should not be retried."""

    pass


def calculate_delay(
    attempt: int,
    initial_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    jitter: float = 1.0,
) -> float:
    """Calculate delay with exponential backoff and jitter.

    Args:
        attempt: Current attempt number (1-indexed)
        initial_delay: Base delay in seconds
        max_delay: Maximum delay cap
        exponential_base: Base for exponential growth
        jitter: Maximum random jitter to add

    Returns:
        Delay in seconds
    """
    # Exponential backoff
    delay = initial_delay * (exponential_base ** (attempt - 1))

    # Add jitter to prevent thundering herd
    delay += random.uniform(0, jitter)

    # Cap at max_delay
    return min(delay, max_delay)


def with_retry(config: RetryConfig | None = None) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """Decorator for adding retry logic to functions.

    Usage:
        @with_retry(RetryConfig(max_attempts=5))
        async def fetch_data():
            ...
    """
    if config is None:
        config = RetryConfig()

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @wraps(func)
        async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            last_exception: Exception | None = None

            for attempt in range(1, config.max_attempts + 1):
                try:
                    return await func(*args, **kwargs)

                except NonRetryableError:
                    raise

                except RetryableHTTPError as e:
                    if e.status_code not in config.retryable_status_codes:
                        raise

                    last_exception = e
                    if attempt < config.max_attempts:
                        delay = calculate_delay(
                            attempt,
                            config.initial_delay,
                            config.max_delay,
                            config.exponential_base,
                            config.jitter,
                        )
                        logger.warning(
                            "Retryable HTTP error",
                            status_code=e.status_code,
                            attempt=attempt,
                            max_attempts=config.max_attempts,
                            delay=delay,
                            function=func.__name__,
                        )
                        await asyncio.sleep(delay)

                except config.retryable_exceptions as e:
                    last_exception = e
                    if attempt < config.max_attempts:
                        delay = calculate_delay(
                            attempt,
                            config.initial_delay,
                            config.max_delay,
                            config.exponential_base,
                            config.jitter,
                        )
                        logger.warning(
                            "Retryable error",
                            error=str(e),
                            error_type=type(e).__name__,
                            attempt=attempt,
                            max_attempts=config.max_attempts,
                            delay=delay,
                            function=func.__name__,
                        )
                        await asyncio.sleep(delay)

            # All retries exhausted
            logger.error(
                "All retries exhausted",
                function=func.__name__,
                max_attempts=config.max_attempts,
                last_error=str(last_exception),
            )
            if last_exception:
                raise last_exception
            raise RuntimeError("Retry failed without exception")

        @wraps(func)
        def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            last_exception: Exception | None = None

            for attempt in range(1, config.max_attempts + 1):
                try:
                    return func(*args, **kwargs)

                except NonRetryableError:
                    raise

                except config.retryable_exceptions as e:
                    last_exception = e
                    if attempt < config.max_attempts:
                        delay = calculate_delay(
                            attempt,
                            config.initial_delay,
                            config.max_delay,
                            config.exponential_base,
                            config.jitter,
                        )
                        logger.warning(
                            "Retryable error (sync)",
                            error=str(e),
                            attempt=attempt,
                            max_attempts=config.max_attempts,
                            delay=delay,
                            function=func.__name__,
                        )
                        import time

                        time.sleep(delay)

            if last_exception:
                raise last_exception
            raise RuntimeError("Retry failed without exception")

        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper  # type: ignore
        return sync_wrapper  # type: ignore

    return decorator


# Tenacity-based retry for more complex scenarios
def create_tenacity_retry(config: RetryConfig | None = None) -> Any:
    """Create a tenacity retry decorator with custom config.

    Usage:
        @create_tenacity_retry(RetryConfig(max_attempts=5))
        async def fetch_data():
            ...
    """
    if config is None:
        config = RetryConfig()

    return retry(
        stop=stop_after_attempt(config.max_attempts),
        wait=wait_exponential_jitter(
            initial=config.initial_delay,
            max=config.max_delay,
            jitter=config.jitter,
        ),
        retry=retry_if_exception_type(config.retryable_exceptions),
        reraise=True,
    )
