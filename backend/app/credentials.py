import os
import threading
import base64
import hashlib
from typing import Optional, List, Dict
from cryptography.fernet import Fernet
import logging

logger = logging.getLogger("app.credentials")

class CredentialStore:
    """
    In-memory credential store with simple Fernet encryption.
    Uses threading.Event to pause/resume runners waiting for credentials.
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(CredentialStore, cls).__new__(cls)
                    cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        # In production, use a vault. For POC, use ENV key or generate one.
        key = os.getenv("SERVER_SECRET_KEY")
        if not key:
            key = Fernet.generate_key().decode()
            logger.warning("SERVER_SECRET_KEY not found. Using a temporary generated key. Data will be lost on restart.")

        # Ensure key is bytes
        if isinstance(key, str):
            key_bytes = key.encode()
        else:
            key_bytes = key

        try:
            self.fernet = Fernet(key_bytes)
        except Exception as e:
            logger.warning(f"SERVER_SECRET_KEY provided is invalid for Fernet directly ({e}). Deriving a valid key using SHA256.")
            # Fallback: Use SHA256 to get 32 bytes, then urlsafe base64 encode
            digest = hashlib.sha256(key_bytes).digest()
            derived_key = base64.urlsafe_b64encode(digest)
            self.fernet = Fernet(derived_key)

        self.store: Dict[str, bytes] = {} # Key: "user_id:provider", Value: encrypted_bytes
        self.waiters: Dict[str, threading.Event] = {} # Key: "user_id:provider", Value: Event
        self.waiters_lock = threading.Lock()

    def _key(self, user_id: str, provider: str) -> str:
        return f"{user_id}:{provider}"

    def set(self, user_id: str, provider: str, value: str) -> None:
        """Encrypts and stores a credential, then notifies any waiters."""
        k = self._key(user_id, provider)
        encrypted_val = self.fernet.encrypt(value.encode())
        self.store[k] = encrypted_val
        logger.info(f"Credential stored for {k}")

        # Notify waiters
        with self.waiters_lock:
            if k in self.waiters:
                logger.info(f"Releasing waiter for {k}")
                self.waiters[k].set()
                # Clean up event? No, keep it set so future calls return immediately.
                # Or remove it? Since 'set' makes it available, wait_for should just check store first.

    def get(self, user_id: str, provider: str) -> Optional[str]:
        """Retrieves and decrypts a credential if it exists."""
        k = self._key(user_id, provider)
        encrypted_val = self.store.get(k)
        if not encrypted_val:
            return None
        try:
            return self.fernet.decrypt(encrypted_val).decode()
        except Exception as e:
            logger.error(f"Error decrypting credential for {k}: {e}")
            return None

    def has(self, user_id: str, provider: str) -> bool:
        return self._key(user_id, provider) in self.store

    def wait_for(self, user_id: str, provider: str, timeout: Optional[int] = 86400) -> Optional[str]:
        """
        Blocks until the credential is available or timeout (default 24h).
        Returns the decrypted value.
        """
        k = self._key(user_id, provider)

        # Check if already exists
        val = self.get(user_id, provider)
        if val:
            return val

        # Prepare to wait
        with self.waiters_lock:
            if k not in self.waiters:
                self.waiters[k] = threading.Event()
            event = self.waiters[k]

        logger.info(f"Waiting for credential {k} (timeout={timeout}s)...")
        signaled = event.wait(timeout=timeout)

        if signaled:
            return self.get(user_id, provider)
        else:
            logger.error(f"Timeout waiting for credential {k}")
            return None

    def list_providers(self, user_id: str) -> List[str]:
        """Returns a list of providers for which the user has credentials."""
        prefix = f"{user_id}:"
        return [k.split(":", 1)[1] for k in self.store.keys() if k.startswith(prefix)]

# Global instance
credential_store = CredentialStore()
