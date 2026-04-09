# Google Docs MCP Server

A Model Context Protocol (MCP) server that provides Google Docs read and write operations over stdio transport. Built with [FastMCP](https://github.com/jlowin/fastmcp), packaged as a hardened Podman container.

## Features

- 14 tools for document lifecycle management: list, read, create, update, delete, comment, move, folder lookup, markdown-to-doc conversion, file upload, markdown update, and tab management (create, delete, rename)
- OAuth 2.0 authentication with least-privilege scopes (`drive.file`, `drive.metadata.readonly`, `documents`)
- Container hardening: read-only filesystem, all capabilities dropped, non-root execution, memory-limited
- Two-step delete confirmation via server-side cryptographic nonce
- Template-based styling for markdown conversion
- Prompt injection mitigation on document reads

## Prerequisites

- [Podman](https://podman.io/) (rootless mode recommended)
- Google Cloud project with OAuth 2.0 Desktop credentials ([setup instructions](#google-oauth-setup))
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) or any MCP-compatible client

## Quickstart

You need a `credentials.json` from Google Cloud Console before starting. See [Google OAuth Setup](#google-oauth-setup) if you don't have one yet.

```bash
# 1. Set up config directory and credentials
mkdir -p ~/.config/google-docs-mcp
cp /path/to/your/credentials.json ~/.config/google-docs-mcp/credentials.json

# 2. Authenticate (prints a URL, open it in your browser and grant access)
touch ~/.config/google-docs-mcp/tokens.json
podman run -it --rm -p 8080:8080 \
  -v ~/.config/google-docs-mcp/tokens.json:/app/tokens.json:rw \
  -v ~/.config/google-docs-mcp/credentials.json:/app/credentials.json:ro \
  ghcr.io/ugiordan/google-docs-mcp-server:latest --auth
```

Add to your Claude Code configuration (`~/.claude.json`):

```json
{
  "mcpServers": {
    "google-docs": {
      "command": "podman",
      "args": [
        "run", "-i", "--rm",
        "--read-only", "--cap-drop=ALL",
        "--security-opt=no-new-privileges", "--memory=256m",
        "--mount", "type=tmpfs,destination=/tmp",
        "-v", "${HOME}/.config/google-docs-mcp/tokens.json:/app/tokens.json:rw",
        "-v", "${HOME}/.config/google-docs-mcp/templates.yaml:/app/templates.yaml:ro",
        "-v", "${HOME}/.config/google-docs-mcp/credentials.json:/app/credentials.json:ro",
        "-v", "${HOME}/uploads:/uploads:ro",
        "ghcr.io/ugiordan/google-docs-mcp-server:latest"
      ]
    }
  }
}
```

Restart Claude Code. The `google-docs` MCP server should appear with 14 available tools.

### Building from source

If you prefer to build locally instead of using the published image:

```bash
git clone https://github.com/ugiordan/google-docs-mcp-server.git
cd google-docs-mcp-server
podman build -t google-docs-mcp:latest -f Containerfile .
```

Then replace `ghcr.io/ugiordan/google-docs-mcp-server:latest` with `localhost/google-docs-mcp:latest` in the commands above.

## Google OAuth Setup

### 1. Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click the project dropdown at the top and select **New Project**
3. Enter a project name (e.g., "Google Docs MCP") and click **Create**
4. Make sure the new project is selected in the dropdown

### 2. Enable APIs

1. Navigate to **APIs & Services > Library**
2. Search for and enable each of these APIs:
   - **Google Docs API**: provides document content read/write
   - **Google Drive API**: provides file listing, metadata, move, trash, and comment operations

### 3. Configure OAuth Consent Screen

1. Navigate to **APIs & Services > OAuth consent screen**
2. Select **External** user type (or **Internal** if using Google Workspace) and click **Create**
3. Fill in the required fields: app name, user support email, developer contact email
4. On the **Scopes** page, click **Add or Remove Scopes** and add:
   - `https://www.googleapis.com/auth/drive.file`
   - `https://www.googleapis.com/auth/drive.metadata.readonly`
   - `https://www.googleapis.com/auth/documents`
5. On the **Test users** page, add your Google account email
6. Click **Save and Continue** through the remaining steps

Note: while the app is in "Testing" status, only test users you explicitly added can authenticate. This is fine for personal use. Publishing the app removes that restriction but requires Google verification.

### 4. Create OAuth 2.0 Client ID

1. Navigate to **APIs & Services > Credentials**
2. Click **Create Credentials > OAuth 2.0 Client ID**
3. Select **Desktop app** as the application type
4. Give it a name (e.g., "google-docs-mcp")
5. Click **Create**
6. Click **Download JSON** on the confirmation dialog
7. Save the file as `~/.config/google-docs-mcp/credentials.json`

### OAuth Scopes

The server requests three scopes during authentication:

| Scope | Access granted |
|-------|---------------|
| `drive.file` | Read/write/delete files that the application has created or that the user has opened with it. Does not grant access to all files in Drive. |
| `drive.metadata.readonly` | Read-only access to file metadata (names, IDs, timestamps, folder structure). Cannot read file content through this scope. |
| `documents` | Read and write access to Google Docs document content and formatting. |

The `drive.file` scope is deliberately restrictive. The server can only modify documents it created or documents explicitly accessed via `read_document`. Pre-existing documents that were never opened through this server will return 403 on write operations.

## Tools

| Tool | Description | Parameters |
|------|-------------|------------|
| `list_documents` | List documents, optionally filtered by name query | `query` (str, optional), `max_results` (int, 1-100, default 10) |
| `read_document` | Read document text content, comments, and all tabs | `document_id` (str) |
| `create_document` | Create a new document | `title` (str), `content` (str, optional), `folder_id` (str, optional) |
| `update_document` | Append to or replace document content, optionally in a specific tab | `document_id` (str), `content` (str), `mode` ("append"\|"replace", default "append"), `tab_id` (str, optional) |
| `create_tab` | Create a new tab in a document | `document_id` (str), `title` (str) |
| `delete_tab` | Delete a tab from a document | `document_id` (str), `tab_id` (str) |
| `rename_tab` | Rename a tab in a document | `document_id` (str), `tab_id` (str), `title` (str) |
| `comment_on_document` | Add a comment, optionally anchored to text | `document_id` (str), `comment` (str), `quoted_text` (str, optional) |
| `find_folder` | Search for a Drive folder by name | `folder_name` (str) |
| `move_document` | Move a document to a different folder | `document_id` (str), `folder_id` (str) |
| `delete_document` | Trash a document (two-step nonce confirmation) | `document_id` (str), `nonce` (str, required on second call) |
| `convert_markdown_to_doc` | Convert markdown to a styled document | `markdown_content` (str), `title` (str), `template_name` (str, optional), `folder_id` (str, optional) |
| `upload_document` | Upload a file as a Google Doc with formatting preserved | `title` (str), `file_path` (str, optional), `file_content_base64` (str, optional), `source_file_id` (str, optional), `mime_type` (str, optional), `folder_id` (str, optional) |
| `update_document_markdown` | Replace content of an existing Google Doc with styled markdown | `document_id` (str), `markdown_content` (str), `template_name` (str, optional) |

### Delete confirmation

`delete_document` requires two calls. The first call returns a cryptographic nonce (valid for 30 seconds). The second call must include the nonce to confirm. Nonces are single-use, document-specific, and stored in-memory. Documents are moved to trash, not permanently deleted.

### Tabs

`read_document` returns all tabs when a document has multiple tabs. Each tab includes `tab_id`, `title`, and `content`. Use `create_tab`, `delete_tab`, and `rename_tab` to manage tabs. Use `update_document` with `tab_id` to write content to a specific tab.

`update_document_markdown` replaces the entire document (all tabs) since it uploads a .docx file. It cannot target individual tabs.

### Read output wrapping

`read_document` wraps returned content in `<document-content>` tags with an untrusted data warning. Tab content is wrapped in `<tab-content>` tags. This helps MCP clients distinguish document content from system instructions. Comments (with replies, authors, quoted text, and resolved status) are included when present. Comment fetching is best-effort and won't fail the read if unavailable.

### Markdown conversion

`convert_markdown_to_doc` supports optional template-based styling. If templates are configured and no `template_name` is provided, the tool returns the list of available templates. Without any template configuration, documents are created with default Google Docs styling.

### File upload

`upload_document` converts a file to a Google Doc, preserving formatting. Three modes:

1. **`file_path`**: path to a file mounted at `/uploads/` inside the container. Best for large files. Drop the file in `~/uploads/` on the host and pass `/uploads/filename.docx`. MIME type is detected from the extension.
2. **`source_file_id`**: ID of a file already in Google Drive. The server copies and converts it. No file transfer through MCP at all.
3. **`file_content_base64`**: base64-encoded file content. Only works for small files (.docx, .pdf, .html, .rtf) since large payloads get truncated by the LLM.

Provide exactly one of these. The MCP config mounts `~/uploads` read-only into the container by default.

### Styled markdown update

`update_document_markdown` replaces the content of an existing Google Doc with styled markdown. It reuses the same markdown parsing and template pipeline as `convert_markdown_to_doc`. The existing document content is cleared before the new styled content is applied.

## Templates

Templates let you apply consistent styling when converting markdown to Google Docs. Create `~/.config/google-docs-mcp/templates.yaml`:

```yaml
templates:
  - name: "standard"
    doc_id: "1aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789ABC"
    default: true
  - name: "report"
    doc_id: "2xYzAbCdEfGhIjKlMnOpQrStUvWx0123456789DEF"
```

The `doc_id` is the ID of a Google Doc whose named styles (heading fonts, body font, sizes, colors, line spacing) will be extracted and applied. Find it in the document URL: `docs.google.com/document/d/{doc_id}/edit`.

Styles copied: heading fonts (H1-H6), body text font, font sizes, line spacing, text colors. Not copied: complex layouts, columns, page breaks, headers/footers, Apps Script, macros.

If `templates.yaml` is missing or empty, all tools work normally and `convert_markdown_to_doc` uses default styling.

## Uploading Files

For large files that exceed MCP parameter limits, use `--upload` to upload directly to Google Drive, then reference the file ID with `upload_document`'s `source_file_id` parameter.

```bash
# Upload and convert to Google Doc in one step
podman run -it --rm \
  -v ~/.config/google-docs-mcp/tokens.json:/app/tokens.json:rw \
  -v ~/.config/google-docs-mcp/credentials.json:/app/credentials.json:ro \
  -v /path/to/file.docx:/tmp/file.docx:ro \
  ghcr.io/ugiordan/google-docs-mcp-server:latest --upload /tmp/file.docx --convert

# Upload without conversion (keeps original format in Drive)
podman run -it --rm \
  -v ~/.config/google-docs-mcp/tokens.json:/app/tokens.json:rw \
  -v ~/.config/google-docs-mcp/credentials.json:/app/credentials.json:ro \
  -v /path/to/file.docx:/tmp/file.docx:ro \
  ghcr.io/ugiordan/google-docs-mcp-server:latest --upload /tmp/file.docx

# With custom title and folder
podman run -it --rm \
  -v ~/.config/google-docs-mcp/tokens.json:/app/tokens.json:rw \
  -v ~/.config/google-docs-mcp/credentials.json:/app/credentials.json:ro \
  -v /path/to/file.docx:/tmp/file.docx:ro \
  ghcr.io/ugiordan/google-docs-mcp-server:latest \
  --upload /tmp/file.docx --title "My Document" --folder-id FOLDER_ID --convert
```

The command prints the file ID, which you can then use with the `upload_document` MCP tool's `source_file_id` parameter for further processing.

Supported formats for `--convert`: `.docx`, `.pdf`, `.html`, `.htm`, `.rtf`.

## Token Management

```bash
# Re-authenticate
podman run -it --rm -p 8080:8080 \
  -v ~/.config/google-docs-mcp/tokens.json:/app/tokens.json:rw \
  -v ~/.config/google-docs-mcp/credentials.json:/app/credentials.json:ro \
  ghcr.io/ugiordan/google-docs-mcp-server:latest --auth

# Revoke access and delete tokens
podman run -it --rm \
  -v ~/.config/google-docs-mcp/tokens.json:/app/tokens.json:rw \
  -v ~/.config/google-docs-mcp/credentials.json:/app/credentials.json:ro \
  ghcr.io/ugiordan/google-docs-mcp-server:latest --revoke
```

Tokens are stored at `~/.config/google-docs-mcp/tokens.json` with `0600` permissions. They refresh automatically on expiry.

## Security

See [SECURITY.md](SECURITY.md) for the full security design, including threat model, container hardening rationale, and input validation strategy.

Summary of security measures:
- **Container**: read-only filesystem, `--cap-drop=ALL`, `--security-opt=no-new-privileges`, `--memory=256m`, non-root (UID 1001), tmpfs for `/tmp`
- **Authentication**: least-privilege OAuth scopes, token file permissions `0600`, credentials mounted read-only
- **Input validation**: document/folder ID regex validation, query sanitization, content size limits (1MB content, 5MB markdown), title/comment length limits
- **Prompt injection**: document content wrapped in delimiter tags with untrusted data warning
- **Delete safety**: server-side cryptographic nonce with 30s TTL, single-use, document-bound

## Development

```bash
# Install dependencies
uv sync

# Run tests (229 unit tests)
uv run pytest -v

# Lint and format
uv run ruff check .
uv run black --check .
uv run bandit -r mcp_server/

# Run locally (set env vars for paths)
export GOOGLE_CREDENTIALS_PATH=/path/to/credentials.json
export GOOGLE_TOKEN_PATH=/path/to/tokens.json
export GOOGLE_TEMPLATES_PATH=/path/to/templates.yaml
uv run python main.py
uv run python main.py --auth    # authenticate
uv run python main.py --revoke  # revoke tokens
```

## Limitations

- **`drive.file` scope boundary**: write operations (update, delete, move, comment) only work on documents created by this server or explicitly opened via `read_document`. Other documents return 403.
- **Non-atomic replace**: `update_document` in replace mode deletes content then inserts new content via `batchUpdate`. A mid-operation failure may leave partial content.
- **Limited host filesystem access**: the server runs in a container. File uploads are restricted to the `/uploads/` mount point. Mount your upload directory in the MCP config: `-v $HOME/uploads:/uploads:ro`.
- **In-memory nonces**: delete nonces are lost on server restart. If the server restarts between the two delete steps, re-initiate the deletion.
- **Template style limits**: only heading/body fonts, sizes, spacing, and colors are copied. Complex layouts (columns, page breaks, headers/footers) are not supported.

## Troubleshooting

**403 Forbidden on write operations**: expected with `drive.file` scope. Call `read_document` on the target document first to grant access.

**AUTH_REQUIRED error**: re-run the `--auth` flow to obtain fresh tokens.

**Container won't start**: verify `credentials.json` and `tokens.json` exist at `~/.config/google-docs-mcp/`. Run `--auth` if tokens are missing.

**Template not found**: check that `templates.yaml` exists, is valid YAML, and the template name matches exactly.

## License

[Apache License 2.0](LICENSE)
