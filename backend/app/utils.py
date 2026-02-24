from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass
from typing import Any, Callable

LOGGER = logging.getLogger("multiagent")


SENSITIVE_PATTERNS = [
    re.compile(r"(sk-[A-Za-z0-9_-]{8,})"),
    re.compile(r"(ghp_[A-Za-z0-9]{8,})"),
    re.compile(r"(Bearer\s+[A-Za-z0-9._-]+)", re.IGNORECASE),
]


def utc_ts() -> int:
    return int(time.time())


def sanitize_log(text: str) -> str:
    sanitized = text
    for pattern in SENSITIVE_PATTERNS:
        sanitized = pattern.sub("[REDACTED]", sanitized)
    return sanitized


def load_env_bool(key: str, default: bool = False) -> bool:
    raw = os.getenv(key)
    if raw is None:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


@dataclass
class CircuitBreaker:
    failure_threshold: int = 3
    reset_after_s: int = 60

    def __post_init__(self) -> None:
        self.failures = 0
        self.last_failure_ts = 0

    def allow(self) -> bool:
        if self.failures < self.failure_threshold:
            return True
        return (time.time() - self.last_failure_ts) > self.reset_after_s

    def mark_success(self) -> None:
        self.failures = 0
        self.last_failure_ts = 0

    def mark_failure(self) -> None:
        self.failures += 1
        self.last_failure_ts = int(time.time())


def retry_with_backoff(func: Callable[[], Any], retries: int = 3, base_delay: float = 0.5) -> Any:
    last_exc: Exception | None = None
    for i in range(retries):
        try:
            return func()
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if i == retries - 1:
                raise
            time.sleep(base_delay * (2**i))
    raise RuntimeError(f"retry failed: {last_exc}")


def safe_json_loads(raw: str) -> dict:
    """Parse JSON even when LLM includes surrounding text."""
    stripped = raw.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        return json.loads(stripped)

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found")
    return json.loads(stripped[start : end + 1])
