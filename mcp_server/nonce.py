"""In-memory nonce manager for delete confirmation."""

import secrets
import time


class NonceManager:
    MAX_STORE_SIZE = 1000

    def __init__(self, ttl_seconds: int = 30):
        self._ttl = ttl_seconds
        self._store: dict[str, tuple[str, float]] = {}  # nonce -> (doc_id, expiry)

    def create(self, document_id: str) -> str:
        self._cleanup()
        if len(self._store) >= self.MAX_STORE_SIZE:
            raise RuntimeError("Too many pending delete confirmations")
        nonce = secrets.token_urlsafe(32)
        self._store[nonce] = (document_id, time.monotonic() + self._ttl)
        return nonce

    def verify(self, document_id: str, nonce: str) -> bool:
        entry = self._store.pop(nonce, None)
        if entry is None:
            return False
        stored_doc_id, expiry = entry
        if stored_doc_id != document_id:
            return False
        if time.monotonic() > expiry:
            return False
        return True

    def _cleanup(self):
        now = time.monotonic()
        expired = [k for k, (_, exp) in self._store.items() if now > exp]
        for k in expired:
            del self._store[k]
