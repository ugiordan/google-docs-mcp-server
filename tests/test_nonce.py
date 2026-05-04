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

    def test_store_exhaustion_raises(self):
        mgr = NonceManager(ttl_seconds=30)
        for i in range(mgr.MAX_STORE_SIZE):
            mgr.create(f"doc{i}")
        try:
            mgr.create("one_too_many")
            assert False, "Should have raised RuntimeError"
        except RuntimeError as e:
            assert "pending delete" in str(e).lower()

    def test_cleanup_frees_space_for_new_nonces(self):
        mgr = NonceManager(ttl_seconds=0)
        for i in range(mgr.MAX_STORE_SIZE):
            mgr.create(f"doc{i}")
        time.sleep(0.05)
        nonce = mgr.create("fresh_doc")
        assert nonce is not None
