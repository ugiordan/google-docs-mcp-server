"""MCP tools package."""

from mcp_server.tools.google_docs_tools import register_google_docs_tools
from mcp_server.tools.google_slides_tools import register_google_slides_tools

__all__ = ["register_google_docs_tools", "register_google_slides_tools"]
