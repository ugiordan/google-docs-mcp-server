"""Authentication module for Google OAuth flow, token management, and revocation."""

import json
import logging
import os

import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

logger = logging.getLogger("google-docs-mcp")

# Define least-privilege scopes
SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/drive.metadata.readonly",
    "https://www.googleapis.com/auth/documents",
]

# OAuth callback bind address. 0.0.0.0 is required for container port forwarding
# but should only be used during --auth flow (short-lived, interactive).
_AUTH_BIND_ADDR = "0.0.0.0"  # nosec B104


def load_tokens(token_path: str) -> Credentials | None:
    """
    Load OAuth tokens from file.

    Args:
        token_path: Path to the token file

    Returns:
        Credentials object if valid tokens exist, None otherwise
    """
    if not os.path.exists(token_path):
        return None

    try:
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(token_path, flags)
        with os.fdopen(fd, "r") as f:
            token_info = json.load(f)
        creds = Credentials.from_authorized_user_info(token_info, SCOPES)

        # Refresh expired credentials if possible
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            save_tokens(creds, token_path)

        if not creds or not creds.valid:
            logger.warning("Credentials are not valid after load/refresh")
            return None

        return creds
    except Exception:
        logger.warning("Failed to load or refresh tokens from %s", token_path)
        return None


def save_tokens(creds: Credentials, token_path: str) -> None:
    """
    Save OAuth tokens to file with secure permissions (0o600).

    Args:
        creds: Credentials object to save
        token_path: Path where tokens should be saved
    """
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(token_path, flags, 0o600)
    try:
        with os.fdopen(fd, "w") as f:
            f.write(creds.to_json())
    except BaseException:
        # fd is closed by os.fdopen even on error, but ensure cleanup
        raise


def run_auth_flow(credentials_path: str, token_path: str) -> Credentials:
    """
    Run the OAuth flow to obtain credentials.

    The callback binds to 0.0.0.0 because Podman port forwarding requires it.
    This is only used during the interactive --auth flow (short-lived).

    Args:
        credentials_path: Path to the OAuth client secrets file
        token_path: Path where tokens should be saved

    Returns:
        Credentials object with access and refresh tokens
    """
    flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
    creds = flow.run_local_server(
        port=8080, bind_addr=_AUTH_BIND_ADDR, open_browser=False
    )
    save_tokens(creds, token_path)
    return creds


def revoke_tokens(token_path: str) -> None:
    """
    Revoke OAuth tokens and delete the token file.

    Args:
        token_path: Path to the token file
    """
    # Read token data first, then delete regardless of revocation outcome
    try:
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(token_path, flags)
        with os.fdopen(fd, "r") as f:
            token_data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return

    try:
        # Revoke the token via Google's revocation endpoint
        token = token_data.get("token")
        if token:
            resp = requests.post(
                "https://oauth2.googleapis.com/revoke",
                params={"token": token},
                headers={"content-type": "application/x-www-form-urlencoded"},
                timeout=10,
            )
            if resp.status_code >= 300:
                logger.warning("Token revocation returned status %d", resp.status_code)
    finally:
        # Always delete the token file
        try:
            os.remove(token_path)
        except FileNotFoundError:
            pass
