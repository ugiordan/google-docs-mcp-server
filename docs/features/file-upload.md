# File Upload

`upload_document` converts a file to a Google Doc, preserving formatting. Three input modes are supported.

## file_path Mode

Path to a file mounted at `/uploads/` inside the container. Best for large files.

Drop the file in `~/uploads/` on the host and pass `/uploads/filename.docx`:

```bash
# The MCP config already mounts ~/uploads read-only
# Just place your file there
cp report.docx ~/uploads/
# Then use upload_document with file_path="/uploads/report.docx"
```

MIME type is detected from the file extension.

## source_file_id Mode

ID of a file already in Google Drive. The server copies and converts it. No file data passes through MCP.

This is the most efficient option for files already in Drive.

## file_content_base64 Mode

Base64-encoded file content passed as a parameter. Only practical for small files (.docx, .pdf, .html, .rtf) since large payloads get truncated by the LLM.

## Direct Upload CLI

For large files that exceed MCP parameter limits, use `--upload` to upload directly to Google Drive:

```bash
# Upload and convert to Google Doc
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

The command prints the file ID, which you can then use with the `upload_document` MCP tool's `source_file_id` parameter.

Supported formats for `--convert`: `.docx`, `.pdf`, `.html`, `.htm`, `.rtf`.

## Security

- **Directory restriction**: only files under `/uploads/` are allowed, with symlink escape prevention via `os.path.realpath()`
- **Read-only mount**: the `/uploads` directory is mounted read-only
- **File size limit**: 50MB maximum
- **MIME type validation**: only allowed formats are accepted

See [Security](../security.md) for the full file upload security model.
