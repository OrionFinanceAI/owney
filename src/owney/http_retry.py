"""HTTP timeout + retry helpers for Zyfai calls."""

from __future__ import annotations

import os
import random
import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")

_RETRYABLE_MARKERS = (
    "ECONNRESET",
    "ETIMEDOUT",
    "ENOTFOUND",
    "ECONNREFUSED",
    "EPIPE",
    "timed out",
    "Temporary failure",
    "Connection reset",
    "Remote end closed",
    "Name or service not known",
)


def resolve_http_timeout_ms() -> int:
    raw = os.getenv("OWNEY_HTTP_TIMEOUT_MS", "").strip()
    try:
        value = float(raw)
    except ValueError:
        value = float("nan")
    return int(value) if value == value and value > 0 else 60_000


def resolve_max_retries() -> int:
    raw = os.getenv("OWNEY_MAX_RETRIES", "").strip()
    try:
        value = float(raw)
    except ValueError:
        value = float("nan")
    return int(value) if value == value and value > 0 else 3


def is_owney_timeout_error(err: BaseException) -> bool:
    return isinstance(err, TimeoutError) or (
        isinstance(err, Exception) and " timed out after " in str(err)
    )


def is_owney_retryable(err: BaseException) -> bool:
    if is_owney_timeout_error(err) and " timed out after " in str(err):
        # Explicit with_timeout rejection is terminal (matches TS).
        return False
    if isinstance(err, TimeoutError):
        return True
    message = str(err)
    return any(marker in message for marker in _RETRYABLE_MARKERS)


def with_owney_retry(
    fn: Callable[[], T],
    *,
    max_attempts: int | None = None,
    base_delay_ms: int = 2_000,
    max_delay_ms: int = 30_000,
    on_retry: Callable[[int, Exception, int], None] | None = None,
) -> T:
    if max_attempts is None:
        attempts = max(1, resolve_max_retries() + 1)
    else:
        if not isinstance(max_attempts, int) or max_attempts < 1:
            raise ValueError(
                f"with_owney_retry max_attempts must be a finite integer >= 1 (got {max_attempts!r})"
            )
        attempts = max_attempts

    base_delay_ms = max(0, base_delay_ms)
    max_delay_ms = max(base_delay_ms, max_delay_ms)

    last_err: Exception = RuntimeError("No attempts made")
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except Exception as err:  # noqa: BLE001 - retry policy owns classification
            last_err = err
            if attempt == attempts or not is_owney_retryable(err):
                raise
            cap = min(max_delay_ms, base_delay_ms * (2**attempt))
            delay_ms = int(random.random() * cap)
            if on_retry is not None:
                on_retry(attempt, err, delay_ms)
            time.sleep(delay_ms / 1000)
    raise last_err
