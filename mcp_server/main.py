"""Google Docs MCP Server — server creation and tool registration."""

import json
import logging
import os
import sys

from fastmcp import FastMCP

from mcp_server.auth import load_tokens
from mcp_server.config import load_templates
from mcp_server.nonce import NonceManager
from mcp_server.services.google_docs_service import GoogleDocsService
from mcp_server.tools.google_docs_tools import register_google_docs_tools


class JsonFormatter(logging.Formatter):
    """Format log records as valid JSON."""

    def format(self, record):
        log_data = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        return json.dumps(log_data)


# Configure logging to stderr (MCP protocol uses stdout for JSON-RPC)
handler = logging.StreamHandler(sys.stderr)
handler.setFormatter(JsonFormatter())
logging.basicConfig(
    handlers=[handler],
    level=logging.INFO,
)
logger = logging.getLogger("google-docs-mcp")


def create_server() -> FastMCP:
    """Create and configure the MCP server."""
    # Load configuration
    token_path = os.environ.get("GOOGLE_TOKEN_PATH", "/app/tokens.json")
    templates_path = os.environ.get("GOOGLE_TEMPLATES_PATH", "/app/templates.yaml")

    # Load templates (graceful degradation if missing)
    template_config = load_templates(templates_path)

    # Load auth tokens
    creds = load_tokens(token_path)
    if creds is None:
        logger.error(
            "No valid tokens found. Run with --auth flag to authenticate: "
            "podman run -it --rm -p 8080:8080 "
            "-v ~/.config/google-docs-mcp/tokens.json:/app/tokens.json:rw "
            "-v ~/.config/google-docs-mcp/credentials.json:/app/credentials.json:ro "
            "localhost/google-docs-mcp:latest --auth"
        )
        # Still create the server so MCP handshake works, but tools will fail
        # Create a stub service that raises on every call
        service = None
    else:
        service = GoogleDocsService(creds)

    # Create MCP server
    mcp = FastMCP(name="google-docs-mcp")

    # Create nonce manager for delete confirmations
    nonce_manager = NonceManager(ttl_seconds=30)

    # Register tools
    if service:
        register_google_docs_tools(mcp, service, nonce_manager, template_config)
    else:
        # Register a single tool that tells the user to authenticate
        @mcp.tool()
        def auth_required() -> str:
            """Authentication required. Run the server with --auth flag first."""
            return '{"error": "Not authenticated. Run with --auth flag to set up Google OAuth.", "code": "AUTH_REQUIRED"}'

    logger.info("Google Docs MCP server initialized")
    return mcp
