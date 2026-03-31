"""Input validation for Google Docs MCP server."""

import re

# Google resource IDs: alphanumeric, hyphens, underscores, 10-100 chars
_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{10,100}$")

MAX_TITLE_LENGTH = 255
MAX_COMMENT_LENGTH = 2048
MAX_CONTENT_BYTES = 1_048_576  # 1MB
MAX_MARKDOWN_BYTES = 5_242_880  # 5MB

ALLOWED_MIME_TYPES = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/pdf",
    "text/html",
    "application/rtf",
}


def validate_document_id(doc_id: str) -> bool:
    if not doc_id:
        raise ValueError("Document ID cannot be empty")
    if not _ID_PATTERN.match(doc_id):
        raise ValueError(
            "Invalid document ID format: must be 10-100 alphanumeric characters, hyphens, or underscores"
        )
    return True


def validate_folder_id(folder_id: str) -> bool:
    if not folder_id:
        raise ValueError("Folder ID cannot be empty")
    if not _ID_PATTERN.match(folder_id):
        raise ValueError(
            "Invalid folder ID format: must be 10-100 alphanumeric characters, hyphens, or underscores"
        )
    return True


def sanitize_query(query: str) -> str:
    return query.replace("\\", "\\\\").replace("'", "\\'")


def validate_title(title: str) -> bool:
    if not title or not title.strip():
        raise ValueError("Title cannot be empty")
    if len(title) > MAX_TITLE_LENGTH:
        raise ValueError(f"Title exceeds {MAX_TITLE_LENGTH} characters")
    return True


def validate_content_size(content: str, max_bytes: int = MAX_CONTENT_BYTES) -> bool:
    size = len(content.encode("utf-8"))
    if size > max_bytes:
        raise ValueError(f"Content exceeds {max_bytes} bytes (got {size})")
    return True


def validate_comment(comment: str) -> bool:
    if not comment or not comment.strip():
        raise ValueError("Comment cannot be empty")
    if len(comment) > MAX_COMMENT_LENGTH:
        raise ValueError(f"Comment exceeds {MAX_COMMENT_LENGTH} characters")
    return True


def validate_template_name(name: str, available: list[str]) -> bool:
    if name not in available:
        raise ValueError(
            f"Unknown template '{name}'. Available: {', '.join(available)}"
        )
    return True


def validate_mime_type(mime_type: str) -> bool:
    if not mime_type:
        raise ValueError("MIME type cannot be empty")
    if mime_type not in ALLOWED_MIME_TYPES:
        raise ValueError(
            f"Unsupported MIME type '{mime_type}'. "
            f"Supported: {', '.join(sorted(ALLOWED_MIME_TYPES))}"
        )
    return True
