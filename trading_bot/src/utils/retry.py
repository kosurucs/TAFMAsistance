"""
retry.py – Exponential-backoff retry helper.

Usage::

    from src.utils.retry import retry

    result = retry(lambda: kite.ltp(["NSE:RELIANCE"]), retries=3)
"""

from __future__ import annotations

import time
from typing import Callable, Optional, Tuple, TypeVar

T = TypeVar("T")


def retry(
    fn: Callable[[], T],
    *,
    retries: int = 3,
    base_delay_s: float = 0.5,
    max_delay_s: float = 5.0,
    retry_on: Tuple[type, ...] = (Exception,),
    should_retry: Optional[Callable[[Exception], bool]] = None,
) -> T:
    """Call *fn* up to *retries + 1* times with exponential back-off.

    Args:
        fn: Zero-argument callable to invoke.
        retries: Maximum number of *additional* attempts after the first call.
        base_delay_s: Initial sleep duration (seconds) before the 2nd attempt.
            Subsequent delays are ``base_delay_s * 2 ** attempt`` capped at
            ``max_delay_s``.
        max_delay_s: Upper bound for the sleep duration.
        retry_on: Tuple of exception types that trigger a retry.
        should_retry: Optional callable that receives the caught exception and
            returns ``True`` if the call should be retried, ``False`` if the
            exception should be re-raised immediately.

    Returns:
        The return value of *fn* on success.

    Raises:
        The last exception raised by *fn* after all retries are exhausted.
    """
    last_exc: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            return fn()
        except retry_on as exc:  # type: ignore[misc]
            last_exc = exc
            if should_retry is not None and not should_retry(exc):
                raise
            if attempt == retries:
                raise
            delay = min(max_delay_s, base_delay_s * (2**attempt))
            time.sleep(delay)
    raise last_exc  # pragma: no cover
