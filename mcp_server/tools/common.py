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


def parse_hex_color(hex_color: str) -> dict:
    """Parse '#RRGGBB' to {'red': float, 'green': float, 'blue': float}."""
    h = hex_color.lstrip("#")
    if len(h) != 6:
        raise ValueError("Invalid color format. Use 6-digit hex like '#FF0000'")
    try:
        return {
            "red": int(h[0:2], 16) / 255.0,
            "green": int(h[2:4], 16) / 255.0,
            "blue": int(h[4:6], 16) / 255.0,
        }
    except ValueError:
        raise ValueError(
            "Invalid color format. Use 6-digit hex like '#FF0000'"
        ) from None


def handle_api_error(e: Exception, operation: str) -> str:
    logger.error("%s error: %s", operation, e)
    if isinstance(e, HttpError):
        status = e.resp.status
        if status == 401:
            return error_response(
                "Authentication expired. Please re-run the --auth flow.",
                "REAUTH_REQUIRED",
            )
        if status == 403:
            return error_response(
                "Permission denied. Check that you have access to this resource.",
                "FORBIDDEN",
            )
        if status == 404:
            return error_response(
                "Resource not found. Verify the ID is correct.",
                "NOT_FOUND",
            )
    if isinstance(e, RuntimeError) and "pending delete" in str(e):
        return error_response(
            "Too many pending delete confirmations. Wait 30 seconds and retry.",
            "RATE_LIMITED",
        )
    return error_response("An internal error occurred", "API_ERROR")
