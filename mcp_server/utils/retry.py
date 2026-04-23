"""Retry utilities for Google API rate limit handling."""

import time

from googleapiclient.errors import HttpError


def retry_on_429(fn, max_retries=3):
    """Execute function with retry logic for 429 rate limit errors.

    Args:
        fn: Function to execute
        max_retries: Maximum number of retries (default: 3)

    Returns:
        Result of the function call

    Raises:
        HttpError: If max retries exceeded or non-429 error occurs
    """
    retries = 0
    backoff = 1

    while True:
        try:
            return fn()
        except HttpError as e:
            if e.resp.status == 429 and retries < max_retries:
                time.sleep(backoff)
                retries += 1
                backoff *= 2
            else:
                raise
