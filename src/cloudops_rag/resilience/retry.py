"""Bounded retry helpers for transient external dependency failures."""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar


logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay_seconds: float = 0.25
    multiplier: float = 2.0
    max_delay_seconds: float = 0.50
    jitter_seconds: float = 0.05
    jitter_enabled: bool = True


DEFAULT_RETRY_POLICY = RetryPolicy()


def execute_with_retry(
    operation: Callable[[], T],
    *,
    operation_name: str,
    policy: RetryPolicy = DEFAULT_RETRY_POLICY,
    on_retry: Callable[[str], None] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    random_fn: Callable[[], float] = random.random,
) -> T:
    """Execute an operation with bounded retry for selected transient failures."""

    attempt = 1
    while True:
        try:
            return operation()
        except Exception as exc:
            reason = retry_reason(exc)
            if reason is None or attempt >= policy.max_attempts:
                raise

            if on_retry is not None:
                on_retry(reason)
            delay = backoff_delay_seconds(policy, retry_index=attempt, random_fn=random_fn)
            logger.warning(
                "Retrying external dependency operation.",
                extra={
                    "operation": operation_name,
                    "reason": reason,
                    "attempt": attempt + 1,
                    "max_attempts": policy.max_attempts,
                },
            )
            sleep(delay)
            attempt += 1


def backoff_delay_seconds(
    policy: RetryPolicy,
    *,
    retry_index: int,
    random_fn: Callable[[], float] = random.random,
) -> float:
    delay = min(
        policy.base_delay_seconds * (policy.multiplier ** (retry_index - 1)),
        policy.max_delay_seconds,
    )
    if policy.jitter_enabled and policy.jitter_seconds > 0:
        delay += random_fn() * policy.jitter_seconds
    return delay


def retry_reason(exc: Exception) -> str | None:
    if is_timeout_error(exc):
        return None

    status_code = getattr(exc, "status_code", None)
    if status_code is not None:
        try:
            status_code = int(status_code)
        except (TypeError, ValueError):
            return None
        if status_code == 429:
            return "rate_limit"
        if 500 <= status_code <= 599:
            return "server_error"
        return None

    name = exc.__class__.__name__
    if name == "RateLimitError":
        return "rate_limit"
    if name == "APIConnectionError":
        return "connection_error"
    if name in {"InternalServerError", "ServiceUnavailableError"}:
        return "server_error"
    return None


def is_timeout_error(exc: Exception) -> bool:
    return exc.__class__.__name__ in {"APITimeoutError", "Timeout", "ReadTimeout", "ConnectTimeout"}
