import logging
import time

logger = logging.getLogger(__name__)


def with_retry(func, max_attempts, base_delay, retryable_exceptions, description="operation"):
    """
    Execute func with retry logic and exponential backoff.

    Args:
        func: Callable to execute (no arguments).
        max_attempts: Maximum number of attempts (including the first).
        base_delay: Base delay in seconds; on the Nth retry (0-indexed attempt),
                    the sleep duration is base_delay * 2**attempt.
                    e.g. base_delay=1 gives delays of 1s, 2s, 4s before retries 1, 2, 3.
        retryable_exceptions: Tuple of exception types that trigger a retry.
        description: Human-readable label used in log messages.

    Returns:
        The return value of func() on success.

    Raises:
        The last caught exception when all attempts are exhausted.
    """
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")
    if base_delay < 0:
        raise ValueError("base_delay must be >= 0")
    if not retryable_exceptions:
        raise ValueError("retryable_exceptions must be a non-empty iterable of exception types")
    last_exception = None
    for attempt in range(max_attempts):
        try:
            return func()
        except retryable_exceptions as exc:
            last_exception = exc
            if attempt < max_attempts - 1:
                delay = base_delay * (2 ** attempt)
                logger.warning(
                    "Attempt %d/%d failed for %s: %s: %s. Retrying in %ss...",
                    attempt + 1,
                    max_attempts,
                    description,
                    type(exc).__name__,
                    exc,
                    delay,
                )
                time.sleep(delay)
            else:
                logger.error(
                    "All %d attempt(s) failed for %s: %s: %s",
                    max_attempts,
                    description,
                    type(exc).__name__,
                    exc,
                )
    raise last_exception
