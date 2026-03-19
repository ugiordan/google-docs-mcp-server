import time

from mcp_server.nonce import NonceManager


class TestNonceManager:
    def test_create_and_verify(self):
        mgr = NonceManager(ttl_seconds=30)
        nonce = mgr.create("doc123")
        assert mgr.verify("doc123", nonce) is True

    def test_nonce_single_use(self):
        mgr = NonceManager(ttl_seconds=30)
        nonce = mgr.create("doc123")
        mgr.verify("doc123", nonce)
        assert mgr.verify("doc123", nonce) is False

    def test_nonce_wrong_doc(self):
        mgr = NonceManager(ttl_seconds=30)
        nonce = mgr.create("doc123")
        assert mgr.verify("doc456", nonce) is False

    def test_nonce_expired(self):
        mgr = NonceManager(ttl_seconds=0)
        nonce = mgr.create("doc123")
        time.sleep(0.1)
        assert mgr.verify("doc123", nonce) is False

    def test_invalid_nonce(self):
        mgr = NonceManager(ttl_seconds=30)
        assert mgr.verify("doc123", "fake-nonce") is False
