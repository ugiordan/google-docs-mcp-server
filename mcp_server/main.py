"""Google Docs MCP Server — server creation and tool registration."""

import json
import logging
import os
import sys

from fastmcp import FastMCP

from mcp_server.auth import load_tokens
from mcp_server.config import load_slides_templates, load_templates
from mcp_server.nonce import NonceManager
from mcp_server.services.google_docs_service import GoogleDocsService
from mcp_server.services.google_sheets_service import GoogleSheetsService
from mcp_server.services.google_slides_service import GoogleSlidesService
from mcp_server.tools.google_docs_tools import register_google_docs_tools
from mcp_server.tools.google_sheets_tools import register_google_sheets_tools
from mcp_server.tools.google_slides_tools import register_google_slides_tools


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
    credentials_path = os.environ.get(
        "GOOGLE_CREDENTIALS_PATH", "/app/credentials.json"
    )
    token_path = os.environ.get("GOOGLE_TOKEN_PATH", "/app/tokens.json")
    templates_path = os.environ.get("GOOGLE_TEMPLATES_PATH", "/app/templates.yaml")

    # Load templates (graceful degradation if missing)
    template_config = load_templates(templates_path)
    slides_template_config = load_slides_templates(templates_path)

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
    mcp = FastMCP(
        name="google-docs-mcp",
        instructions="""\
Google Workspace MCP server for Docs, Slides, and Sheets.

## Tool selection guide

### Google Docs: choosing the right update tool
- **convert_markdown_to_doc**: Create a NEW styled document from markdown. Use for initial document creation.
- **update_document_markdown**: REPLACE content of an existing doc (or tab) with styled markdown. Full heading/bold/table/list formatting. Use when you need to restyle or rewrite a section.
- **update_document**: Insert or replace PLAIN TEXT only. No formatting. Mode 'append' adds to end, 'replace' clears and rewrites. Use for quick text additions where styling doesn't matter.
- **find_replace_document**: Find and replace specific text strings. Preserves ALL existing formatting and comments. Use for targeted edits to existing content without touching styles.
- **insert_table_rows**: Add rows to existing tables. Use table_index (0-based) and after_row (0=after header, -1=append).
- **update_doc_text_style**: Apply formatting (bold, italic, font, color, alignment) to a range WITHOUT changing text content.

### Common mistakes to avoid
1. Do NOT use update_document(mode='append') when you need styled content. Use update_document_markdown instead.
2. Do NOT use update_document_markdown to add a single line. Use find_replace_document to insert text at a known anchor point.
3. Do NOT use update_doc_text_style on the entire document when you only want to style one paragraph. Always specify start_index/end_index.
4. When editing existing styled documents, prefer find_replace_document over update_document_markdown. find_replace preserves all formatting and comments.

### Google Slides
- **read_presentation**: Always read first to get slide_id and shape_id values before modifying.
- **create_shape**: Create rectangles, ellipses, text boxes, etc. Positions in PT. Returns shape_id.
- **create_line**: Create lines/arrows between points. Coordinates in PT. Returns line_id.
- **update_slide_text**: Replace text in an existing shape. Preserves original style.

### Google Sheets
- **read_spreadsheet**: Read all sheets or a specific range (A1 notation like 'Sheet1!A1:C10').
- **update_cells**: Write to specific cells. Values as JSON array of arrays. Supports formulas (=SUM...).
- **append_rows**: Add rows after the last row with data.\
""",
    )

    # Create nonce manager for delete confirmations
    nonce_manager = NonceManager(ttl_seconds=30)

    # Register tools
    if service:
        slides_service = GoogleSlidesService(creds)
        sheets_service = GoogleSheetsService(creds)
        register_google_docs_tools(
            mcp,
            service,
            nonce_manager,
            template_config,
            credentials_path=credentials_path,
            token_path=token_path,
        )
        register_google_slides_tools(
            mcp, slides_service, nonce_manager, slides_template_config
        )
        register_google_sheets_tools(mcp, sheets_service)
    else:
        # Register a single tool that tells the user to authenticate
        @mcp.tool()
        def auth_required() -> str:
            """Authentication required. Run the server with --auth flag first."""
            return '{"error": "Not authenticated. Run with --auth flag to set up Google OAuth.", "code": "AUTH_REQUIRED"}'

    logger.info("Google Docs MCP server initialized")
    return mcp
