"""Tests for retry utility."""

from unittest.mock import MagicMock, patch

import pytest
from googleapiclient.errors import HttpError

from mcp_server.utils.retry import retry_on_429


class TestRetryOn429:
    def test_success_on_first_try(self):
        fn = MagicMock(return_value="ok")
        assert retry_on_429(fn) == "ok"
        assert fn.call_count == 1

    @patch("mcp_server.utils.retry.time.sleep")
    def test_retries_on_429(self, mock_sleep):
        resp = MagicMock()
        resp.status = 429
        error = HttpError(resp, b"rate limited")
        fn = MagicMock(side_effect=[error, "ok"])
        assert retry_on_429(fn) == "ok"
        assert fn.call_count == 2
        mock_sleep.assert_called_once_with(1)

    @patch("mcp_server.utils.retry.time.sleep")
    def test_exponential_backoff(self, mock_sleep):
        resp = MagicMock()
        resp.status = 429
        error = HttpError(resp, b"rate limited")
        fn = MagicMock(side_effect=[error, error, error, "ok"])
        assert retry_on_429(fn) == "ok"
        assert fn.call_count == 4
        assert mock_sleep.call_args_list[0][0][0] == 1
        assert mock_sleep.call_args_list[1][0][0] == 2
        assert mock_sleep.call_args_list[2][0][0] == 4

    def test_raises_non_429_error(self):
        resp = MagicMock()
        resp.status = 403
        error = HttpError(resp, b"forbidden")
        fn = MagicMock(side_effect=error)
        with pytest.raises(HttpError):
            retry_on_429(fn)
        assert fn.call_count == 1

    @patch("mcp_server.utils.retry.time.sleep")
    def test_raises_after_max_retries(self, mock_sleep):
        resp = MagicMock()
        resp.status = 429
        error = HttpError(resp, b"rate limited")
        fn = MagicMock(side_effect=error)
        with pytest.raises(HttpError):
            retry_on_429(fn, max_retries=2)
        assert fn.call_count == 3
