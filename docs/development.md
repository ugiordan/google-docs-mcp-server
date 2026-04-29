# Development

## Setup

```bash
# Clone and install
git clone https://github.com/ugiordan/google-docs-mcp-server.git
cd google-docs-mcp-server
uv sync

# Run tests (604 unit tests)
uv run pytest -v

# Lint and format
uv run ruff check .
uv run black --check .
uv run bandit -r mcp_server/ -c pyproject.toml

# Run locally
export GOOGLE_CREDENTIALS_PATH=/path/to/credentials.json
export GOOGLE_TOKEN_PATH=/path/to/tokens.json
export GOOGLE_TEMPLATES_PATH=/path/to/templates.yaml
uv run python main.py
uv run python main.py --auth    # authenticate
uv run python main.py --revoke  # revoke tokens
```

## Project Structure

```
google-docs-mcp-server/
├── main.py                          # Entry point, CLI args, logging
├── mcp_server/
│   ├── tools/
│   │   ├── common.py                # Shared utilities (tag_untrusted, error_response)
│   │   ├── google_docs_tools.py     # 19 Google Docs MCP tools
│   │   └── google_slides_tools.py   # 13 Google Slides MCP tools
│   └── services/
│       ├── google_docs_service.py   # Google Docs API client
│       ├── google_slides_service.py # Google Slides API client
│       ├── markdown_converter.py    # Markdown parser for Docs
│       ├── batch_style_writer.py    # batchUpdate request builder (styled content)
│       ├── diff_updater.py          # Paragraph-level diff for comment preservation
│       ├── docx_converter.py        # Markdown to .docx converter
│       └── slides_markdown_converter.py  # Markdown parser for Slides
├── tests/                           # 604 unit tests
├── Containerfile                    # UBI9-based container image
├── pyproject.toml                   # Dependencies and tool config
└── mkdocs.yml                       # Documentation site config
```

## Architecture

The server uses FastMCP for MCP protocol handling over stdio transport. Tools are registered in the tools layer and delegate to service classes for Google API calls.

### Update Paths

Content updates follow two paths:

1. **Tab path** (`update_document_markdown` with `tab_id`): parses markdown into blocks, generates batchUpdate requests with `batch_style_writer`, then uses `diff_updater` to compute minimal changes against the current tab content. Preserves comment anchors on unchanged text.

2. **Full document path** (`update_document_markdown` without `tab_id`, or `convert_markdown_to_doc`): converts markdown to .docx via `docx_converter`, uploads via Drive API. For updates, saves and restores comments before and after replacement.

### Index Math

The Google Docs API uses UTF-16 code unit offsets, not Python character counts. The `_utf16_len()` function in `batch_style_writer` handles this. Emoji and other characters outside the Basic Multilingual Plane (like `\U0001f600`) count as 2 UTF-16 code units.

The diff updater processes opcodes in reverse document order so each operation uses original indices (changes at higher indices don't affect lower-index content).

## Limitations

- **Non-atomic replace**: `update_document` in replace mode deletes then inserts via batchUpdate. A mid-operation failure may leave partial content.
- **Limited host filesystem access**: file uploads restricted to the `/uploads/` mount point.
- **In-memory nonces**: delete nonces lost on server restart.
- **Template style limits**: only heading/body fonts, sizes, spacing, and colors are copied. Complex layouts are not supported.
- **Comment restoration is best-effort**: full-document updates may fail to re-anchor comments if the quoted text no longer exists in the new content.
