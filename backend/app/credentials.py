from __future__ import annotations

import base64
import os
import threading
from collections import defaultdict
from typing import Optional

try:
    from cryptography.fernet import Fernet
except Exception:  # noqa: BLE001
    Fernet = None

from .utils import load_env_bool


class CredentialStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._store: dict[str, dict[str, bytes]] = defaultdict(dict)
        self._events: dict[tuple[str, str], threading.Event] = {}
        self.dev_mode = load_env_bool("DEV_MODE", default=False)
        self._fernet = self._build_fernet()

    def _build_fernet(self):
        if Fernet is None:
            return None
        key = os.getenv("SERVER_SECRET_KEY", "")
        if self.dev_mode:
            key = key or Fernet.generate_key().decode()
        if not key:
            # fallback for local dev; production should always pass env
            key = Fernet.generate_key().decode()
        normalized = key.encode()
        return Fernet(normalized)

    def _encrypt(self, value: str) -> bytes:
        if self.dev_mode or self._fernet is None:
            return value.encode()
        return self._fernet.encrypt(value.encode())

    def _decrypt(self, value: bytes) -> str:
        if self.dev_mode or self._fernet is None:
            return value.decode()
        return self._fernet.decrypt(value).decode()

    def set(self, user_id: str, provider: str, value: str) -> None:
        key = (user_id, provider)
        with self._lock:
            self._store[user_id][provider] = self._encrypt(value)
            evt = self._events.get(key)
            if evt:
                evt.set()

    def get(self, user_id: str, provider: str) -> Optional[str]:
        with self._lock:
            encrypted = self._store.get(user_id, {}).get(provider)
            if encrypted is None:
                return None
            return self._decrypt(encrypted)

    def has(self, user_id: str, provider: str) -> bool:
        with self._lock:
            return provider in self._store.get(user_id, {})

    def wait_for(self, user_id: str, provider: str, timeout: Optional[int] = None) -> Optional[str]:
        existing = self.get(user_id, provider)
        if existing:
            return existing
        key = (user_id, provider)
        with self._lock:
            evt = self._events.setdefault(key, threading.Event())
        wait_timeout = timeout if timeout is not None else 60 * 60 * 24
        signaled = evt.wait(timeout=wait_timeout)
        if not signaled:
            return None
        return self.get(user_id, provider)

    def list_providers(self, user_id: str) -> list[str]:
        with self._lock:
            return sorted(self._store.get(user_id, {}).keys())
