"""Entry point for Google Docs MCP server."""

import sys


def _upload_file():
    """Upload a local file to Google Drive and print the file ID."""
    import os

    from mcp_server.auth import load_tokens
    from mcp_server.services.google_docs_service import GoogleDocsService

    MIME_BY_EXT = {
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".pdf": "application/pdf",
        ".html": "text/html",
        ".htm": "text/html",
        ".rtf": "application/rtf",
    }

    # Parse args: --upload <file_path> [--title <title>] [--folder-id <id>] [--convert]
    args = sys.argv[1:]
    try:
        upload_idx = args.index("--upload")
    except ValueError:
        print(
            "Usage: --upload <file_path> [--title <title>] [--folder-id <id>] [--convert]"
        )
        sys.exit(1)

    if upload_idx + 1 >= len(args) or args[upload_idx + 1].startswith("--"):
        print("Error: --upload requires a file path")
        sys.exit(1)

    file_path = args[upload_idx + 1]
    title = None
    folder_id = None
    convert = "--convert" in args

    if "--title" in args:
        ti = args.index("--title")
        if ti + 1 < len(args):
            title = args[ti + 1]

    if "--folder-id" in args:
        fi = args.index("--folder-id")
        if fi + 1 < len(args):
            folder_id = args[fi + 1]

    # Restrict uploads to allowed directories (same as MCP tool)
    from mcp_server.validation import MAX_UPLOAD_BYTES

    ALLOWED_UPLOAD_DIRS = ("/uploads/",)
    resolved = os.path.realpath(file_path)
    if not any(resolved.startswith(d) for d in ALLOWED_UPLOAD_DIRS):
        print(
            "Error: file_path must be under /uploads/. "
            "Mount a host directory: -v $HOME/uploads:/uploads:ro"
        )
        sys.exit(1)

    if not os.path.isfile(resolved):
        print(f"Error: file not found: {file_path}")
        sys.exit(1)

    file_size = os.path.getsize(resolved)
    if file_size > MAX_UPLOAD_BYTES:
        print(f"Error: file exceeds {MAX_UPLOAD_BYTES} bytes")
        sys.exit(1)

    ext = os.path.splitext(resolved)[1].lower()
    mime_type = MIME_BY_EXT.get(ext)
    if convert and not mime_type:
        print(f"Error: unsupported extension '{ext}' for conversion")
        print(f"Supported: {', '.join(sorted(MIME_BY_EXT.keys()))}")
        sys.exit(1)

    if not title:
        title = os.path.splitext(os.path.basename(file_path))[0]

    token_path = os.environ.get("GOOGLE_TOKEN_PATH", "/app/tokens.json")
    creds = load_tokens(token_path)
    if not creds:
        print("Error: no valid tokens. Run --auth first.")
        sys.exit(1)

    service = GoogleDocsService(creds)

    with open(resolved, "rb") as f:
        file_bytes = f.read()

    if convert:
        result = service.upload_file(file_bytes, title, mime_type, folder_id=folder_id)
        print("Uploaded and converted to Google Doc:")
    else:
        from googleapiclient.http import MediaInMemoryUpload

        body = {"name": title}
        if mime_type:
            body["mimeType"] = mime_type
        if folder_id:
            body["parents"] = [folder_id]

        media = MediaInMemoryUpload(
            file_bytes, mimetype=mime_type or "application/octet-stream"
        )
        result_raw = (
            service.drive_service.files()
            .create(body=body, media_body=media, fields="id,name")
            .execute()
        )
        result = {
            "id": result_raw["id"],
            "name": result_raw["name"],
        }
        print("Uploaded to Google Drive (no conversion):")

    print(f"  ID:   {result['id']}")
    print(f"  Name: {result['name']}")
    if "url" in result:
        print(f"  URL:  {result['url']}")
    print(f"\nUse source_file_id=\"{result['id']}\" with upload_document to convert.")


def main():
    if "--auth" in sys.argv:
        import os

        from mcp_server.auth import run_auth_flow

        credentials_path = os.environ.get(
            "GOOGLE_CREDENTIALS_PATH", "/app/credentials.json"
        )
        token_path = os.environ.get("GOOGLE_TOKEN_PATH", "/app/tokens.json")
        run_auth_flow(credentials_path, token_path)
    elif "--revoke" in sys.argv:
        import os

        from mcp_server.auth import revoke_tokens

        token_path = os.environ.get("GOOGLE_TOKEN_PATH", "/app/tokens.json")
        revoke_tokens(token_path)
    elif "--upload" in sys.argv:
        _upload_file()
    else:
        from mcp_server.main import create_server

        mcp = create_server()
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
