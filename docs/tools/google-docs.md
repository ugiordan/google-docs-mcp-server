# Google Docs Tools

20 tools for document lifecycle management, content updates, comments, and tab management.

## Document Operations

| Tool | Description | Parameters |
|------|-------------|------------|
| `list_documents` | List documents, optionally filtered by name query | `query` (str, optional), `max_results` (int, 1-100, default 10) |
| `read_document` | Read document text content, comments, and all tabs | `document_id` (str) |
| `create_document` | Create a new document | `title` (str), `content` (str, optional), `folder_id` (str, optional) |
| `update_document` | Append to or replace document content, optionally in a specific tab | `document_id` (str), `content` (str), `mode` ("append"\|"replace", default "append"), `tab_id` (str, optional) |
| `delete_document` | Trash a document (two-step nonce confirmation) | `document_id` (str), `nonce` (str, required on second call) |
| `find_folder` | Search for a Drive folder by name | `folder_name` (str) |
| `move_document` | Move a document to a different folder | `document_id` (str), `folder_id` (str) |

## Markdown Conversion

| Tool | Description | Parameters |
|------|-------------|------------|
| `convert_markdown_to_doc` | Convert markdown to a styled document | `markdown_content` (str), `title` (str), `template_name` (str, optional), `folder_id` (str, optional) |
| `update_document_markdown` | Replace content of an existing doc with styled markdown | `document_id` (str), `markdown_content` (str), `template_name` (str, optional), `tab_id` (str, optional) |
| `upload_document` | Upload a file as a Google Doc with formatting preserved | `title` (str), `file_path` (str, optional), `file_content_base64` (str, optional), `source_file_id` (str, optional), `mime_type` (str, optional), `folder_id` (str, optional) |

## Comments

| Tool | Description | Parameters |
|------|-------------|------------|
| `comment_on_document` | Add a comment, optionally anchored to text | `document_id` (str), `comment` (str), `quoted_text` (str, optional) |
| `list_comments` | List all comments with replies, authors, and resolved status | `document_id` (str) |
| `reply_to_comment` | Reply to an existing comment | `document_id` (str), `comment_id` (str), `reply` (str) |
| `resolve_comment` | Mark a comment as resolved | `document_id` (str), `comment_id` (str) |
| `delete_comment` | Delete a comment | `document_id` (str), `comment_id` (str) |

## Tab Management

| Tool | Description | Parameters |
|------|-------------|------------|
| `create_tab` | Create a new tab in a document | `document_id` (str), `title` (str) |
| `delete_tab` | Delete a tab from a document | `document_id` (str), `tab_id` (str) |
| `rename_tab` | Rename a tab in a document | `document_id` (str), `tab_id` (str), `title` (str) |

## Find and Replace

| Tool | Description | Parameters |
|------|-------------|------------|
| `find_replace_document` | Find and replace text without losing comments | `document_id` (str), `replacements` (str, JSON array of `{"find":"old","replace":"new"}`), `tab_id` (str, optional), `match_case` (bool, default true) |

## Text Styling

| Tool | Description | Parameters |
|------|-------------|------------|
| `update_doc_text_style` | Style text without replacing content | `document_id` (str), `start_index` (int, optional), `end_index` (int, optional), `bold`/`italic`/`underline` (bool, optional), `font_family` (str, optional), `font_size` (float, optional), `foreground_color` (str '#RRGGBB', optional), `alignment` (str, optional), `tab_id` (str, optional) |

## Behavior Details

### Delete Confirmation

`delete_document` requires two calls. The first call returns a cryptographic nonce (valid for 30 seconds). The second call must include the nonce to confirm. Nonces are single-use and document-specific. Documents are moved to trash, not permanently deleted.

### Read Output Wrapping

`read_document` wraps returned content in `<document-content>` tags with an untrusted data warning. Tab content is wrapped in `<tab-content>` tags. This helps MCP clients distinguish document content from system instructions. Comments (with replies, authors, quoted text, and resolved status) are included when present.

### Comment Preservation

When `update_document_markdown` is called with a `tab_id`, it uses paragraph-level diffing to only modify changed content. Comments anchored to unchanged text are preserved. If the content is completely different, it falls back to a full replacement. See [Comment Preservation](../features/comment-preservation.md) for details.
