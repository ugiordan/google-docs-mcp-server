# Google Docs MCP Server

A Model Context Protocol (MCP) server that provides Google Docs and Google Slides read and write operations over stdio transport. Built with [FastMCP](https://github.com/jlowin/fastmcp), packaged as a hardened Podman container.

## Features

- 33 tools for document and presentation lifecycle management: Docs (list, read, create, update, delete, comment, move, folder lookup, markdown-to-doc, file upload, markdown update, tab management, text styling, find-and-replace) and Slides (list, read, create, add/delete/bulk delete/duplicate/reorder slides, update text, text styling, delete shape, speaker notes, markdown-to-slides)
- OAuth 2.0 authentication with scopes (`drive`, `drive.metadata.readonly`, `documents`)
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

Restart Claude Code. The `google-docs` MCP server should appear with 33 available tools.

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
   - **Google Slides API**: provides presentation content read/write

### 3. Configure OAuth Consent Screen

1. Navigate to **APIs & Services > OAuth consent screen**
2. Select **External** user type (or **Internal** if using Google Workspace) and click **Create**
3. Fill in the required fields: app name, user support email, developer contact email
4. On the **Scopes** page, click **Add or Remove Scopes** and add:
   - `https://www.googleapis.com/auth/drive`
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
| `drive` | Full read/write/delete access to Google Drive files. Required for comment, move, and delete operations on any document. Also covers Google Slides API operations. |
| `drive.metadata.readonly` | Read-only access to file metadata (names, IDs, timestamps, folder structure). Cannot read file content through this scope. |
| `documents` | Read and write access to Google Docs document content and formatting. |

The `drive` scope grants access to all files in the user's Drive. Container hardening (read-only filesystem, dropped capabilities, non-root, memory limits) provides defense in depth.

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
| `list_comments` | List all comments with replies, authors, and resolved status | `document_id` (str) |
| `reply_to_comment` | Reply to an existing comment | `document_id` (str), `comment_id` (str), `reply` (str) |
| `resolve_comment` | Mark a comment as resolved | `document_id` (str), `comment_id` (str) |
| `delete_comment` | Delete a comment | `document_id` (str), `comment_id` (str) |
| `find_folder` | Search for a Drive folder by name | `folder_name` (str) |
| `move_document` | Move a document to a different folder | `document_id` (str), `folder_id` (str) |
| `delete_document` | Trash a document (two-step nonce confirmation) | `document_id` (str), `nonce` (str, required on second call) |
| `convert_markdown_to_doc` | Convert markdown to a styled document | `markdown_content` (str), `title` (str), `template_name` (str, optional), `folder_id` (str, optional) |
| `upload_document` | Upload a file as a Google Doc with formatting preserved | `title` (str), `file_path` (str, optional), `file_content_base64` (str, optional), `source_file_id` (str, optional), `mime_type` (str, optional), `folder_id` (str, optional) |
| `update_document_markdown` | Replace content of an existing Google Doc with styled markdown | `document_id` (str), `markdown_content` (str), `template_name` (str, optional), `tab_id` (str, optional) |
| `update_doc_text_style` | Style text without replacing content | `document_id` (str), `start_index` (int, optional), `end_index` (int, optional), `bold`/`italic`/`underline` (bool, optional), `font_family` (str, optional), `font_size` (float, optional), `foreground_color` (str '#RRGGBB', optional), `alignment` (str, optional), `tab_id` (str, optional) |
| `find_replace_document` | Find and replace text without losing comments | `document_id` (str), `replacements` (str, JSON array of `{"find":"old","replace":"new"}`), `tab_id` (str, optional), `match_case` (bool, default true) |
| **Google Slides** | | |
| `list_presentations` | List presentations, optionally filtered by name | `query` (str, optional), `max_results` (int, 1-100, default 10) |
| `read_presentation` | Read all slide content: text, speaker notes, shape IDs, layout info | `presentation_id` (str) |
| `create_presentation` | Create a new presentation, optionally from a template | `title` (str), `folder_id` (str, optional), `template_name` (str, optional) |
| `add_slide` | Add a slide at a position with optional layout | `presentation_id` (str), `position` (int, optional), `layout` (str, optional: custom display name or predefined) |
| `delete_slide` | Delete a slide (two-step nonce confirmation) | `presentation_id` (str), `slide_id` (str), `nonce` (str, required on second call) |
| `delete_slides` | Delete multiple slides at once (two-step nonce confirmation) | `presentation_id` (str), `slide_ids` (str, comma-separated), `nonce` (str, required on second call) |
| `update_slide_text` | Replace text in a shape, preserving font/size/color | `presentation_id` (str), `slide_id` (str), `shape_id` (str), `content` (str) |
| `delete_shape` | Delete a shape, image, or element from a slide (two-step nonce confirmation) | `presentation_id` (str), `shape_id` (str), `nonce` (str, required on second call) |
| `update_speaker_notes` | Set speaker notes for a slide | `presentation_id` (str), `slide_id` (str), `notes` (str) |
| `duplicate_slide` | Copy a slide within a presentation | `presentation_id` (str), `slide_id` (str), `position` (int, optional) |
| `reorder_slides` | Move slides to new positions | `presentation_id` (str), `slide_ids` (str, comma-separated), `position` (int) |
| `update_slide_text_style` | Style all text in a shape without replacing content | `presentation_id` (str), `shape_id` (str), `bold`/`italic`/`underline` (bool, optional), `font_family` (str, optional), `font_size` (float, optional), `foreground_color` (str '#RRGGBB', optional), `alignment` (str, optional) |
| `convert_markdown_to_slides` | Convert markdown to a presentation (slides split on `---`) | `markdown_content` (str), `title` (str), `folder_id` (str, optional), `template_name` (str, optional) |

### Delete confirmation

`delete_document`, `delete_slide`, `delete_slides`, and `delete_shape` require two calls. The first call returns a cryptographic nonce (valid for 30 seconds). The second call must include the nonce to confirm. Nonces are single-use, resource-specific, and stored in-memory. Documents are moved to trash, not permanently deleted. Slides and shapes are deleted immediately on confirmation.

### Tabs

`read_document` returns all tabs when a document has multiple tabs. Each tab includes `tab_id`, `title`, and `content`. Use `create_tab`, `delete_tab`, and `rename_tab` to manage tabs. Use `update_document` with `tab_id` to write content to a specific tab.

`update_document_markdown` supports per-tab updates via the `tab_id` parameter. When `tab_id` is specified, it uses paragraph-level diffing to apply only the changes, preserving comment anchors on unchanged text. Without `tab_id`, it uploads a .docx file which replaces the entire document including all tabs.

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

`update_document_markdown` replaces the content of an existing Google Doc with styled markdown. It reuses the same markdown parsing and template pipeline as `convert_markdown_to_doc`. When no `template_name` is specified, the document's existing named styles (heading fonts, body font, sizes, colors, line spacing) are preserved.

When called with a `tab_id`, the tool uses paragraph-level diffing to only modify changed content. Comments anchored to unchanged text are preserved. When called without `tab_id`, it uploads a .docx file replacement with best-effort comment save/restore (comments whose quoted text no longer exists in the new content may not be re-anchored).

## Templates

Templates let you apply consistent styling when converting markdown to Google Docs and Slides. Create `~/.config/google-docs-mcp/templates.yaml`:

```yaml
templates:
  - name: "standard"
    doc_id: "1aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789ABC"
    default: true
  - name: "report"
    doc_id: "2xYzAbCdEfGhIjKlMnOpQrStUvWx0123456789DEF"

slides_templates:
  - name: "corporate"
    presentation_id: "1aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789ABC"
    default: true
```

### Docs templates

The `doc_id` is the ID of a Google Doc whose named styles (heading fonts, body font, sizes, colors, line spacing) will be extracted and applied. Find it in the document URL: `docs.google.com/document/d/{doc_id}/edit`.

Styles copied: heading fonts (H1-H6), body text font, font sizes, line spacing, text colors. Not copied: complex layouts, columns, page breaks, headers/footers, Apps Script, macros.

### Slides templates

The `presentation_id` is the ID of a Google Slides presentation that serves as the base for new presentations. Find it in the presentation URL: `docs.google.com/presentation/d/{presentation_id}/edit`.

When a slides template is configured, `create_presentation` and `convert_markdown_to_slides` will copy the template presentation (via Drive API `files.copy`) instead of creating a blank one. The copy inherits the template's theme, master slides, layouts, fonts, and colors. The template itself is never modified.

If a default template is set, it's used automatically. Pass `template_name` to pick a specific template. Without any slides template configuration, presentations are created blank.

If `templates.yaml` is missing or empty, all tools work normally with default styling.

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
- **Authentication**: token file permissions `0600`, credentials mounted read-only, container hardening compensates for broad `drive` scope
- **Input validation**: document/folder ID regex validation, query sanitization, content size limits (1MB content, 5MB markdown), title/comment length limits
- **Prompt injection**: document content wrapped in delimiter tags with untrusted data warning
- **Delete safety**: server-side cryptographic nonce with 30s TTL, single-use, document-bound

## Development

```bash
# Install dependencies
uv sync

# Run tests
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

- **Non-atomic replace**: `update_document` in replace mode deletes content then inserts new content via `batchUpdate`. A mid-operation failure may leave partial content.
- **Limited host filesystem access**: the server runs in a container. File uploads are restricted to the `/uploads/` mount point. Mount your upload directory in the MCP config: `-v $HOME/uploads:/uploads:ro`.
- **In-memory nonces**: delete nonces are lost on server restart. If the server restarts between the two delete steps, re-initiate the deletion.
- **Template style limits**: only heading/body fonts, sizes, spacing, and colors are copied. Complex layouts (columns, page breaks, headers/footers) are not supported.
- **Comment restoration**: full-document updates save and restore comments on a best-effort basis. Comments whose quoted text no longer exists in the new content cannot be re-anchored.

## Troubleshooting

**403 Forbidden on write operations**: re-run `--auth` to refresh tokens. Ensure the Google account has edit access to the target document.

**AUTH_REQUIRED error**: re-run the `--auth` flow to obtain fresh tokens.

**Container won't start**: verify `credentials.json` and `tokens.json` exist at `~/.config/google-docs-mcp/`. Run `--auth` if tokens are missing.

**Template not found**: check that `templates.yaml` exists, is valid YAML, and the template name matches exactly.

## License

[Apache License 2.0](LICENSE)
