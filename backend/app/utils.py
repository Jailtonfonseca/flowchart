import os
import logging
import re
from functools import lru_cache
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger("app")

def get_env_var(key: str, default: Optional[str] = None) -> str:
    val = os.getenv(key, default)
    if val is None:
        raise ValueError(f"Environment variable {key} is not set.")
    return val

def sanitize_log(msg: str) -> str:
    """Redacts potential secrets (simple heuristic for long strings)."""
    # Simple regex to redact long token-like strings (e.g., sk-..., jwt, etc.)
    # This is a basic implementation.
    pattern = r"(sk-[a-zA-Z0-9]{20,}|eyJ[a-zA-Z0-9\-_]+\.[a-zA-Z0-9\-_]+\.[a-zA-Z0-9\-_]+)"
    return re.sub(pattern, "[REDACTED]", msg)

def safe_log(level: int, msg: str):
    logger.log(level, sanitize_log(msg))
