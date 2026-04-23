"""Shared utilities for MCP tool definitions."""

import json
import logging
import secrets

from googleapiclient.errors import HttpError

logger = logging.getLogger("google-docs-mcp")


def tag_untrusted(data: str) -> str:
    boundary = secrets.token_hex(8)
    return f"<untrusted-data-{boundary}>{data}</untrusted-data-{boundary}>"


def error_response(message: str, code: str) -> str:
    return json.dumps({"error": message, "code": code})


def handle_api_error(e: Exception, operation: str) -> str:
    logger.error("%s error: %s", operation, e)
    if isinstance(e, HttpError) and e.resp.status == 401:
        return error_response(
            "Authentication expired. Please re-run the --auth flow.",
            "REAUTH_REQUIRED",
        )
    return error_response("An internal error occurred", "API_ERROR")
