"""Tests for Google Docs MCP tools."""

import json
from unittest.mock import MagicMock, patch

from mcp_server.config import Template, TemplateConfig
from mcp_server.nonce import NonceManager
from mcp_server.tools.common import error_response
from mcp_server.tools.google_docs_tools import (
    _comment_on_document,
    _convert_markdown_to_doc,
    _create_document,
    _create_tab,
    _delete_comment,
    _delete_document,
    _delete_tab,
    _find_folder,
    _find_replace_document,
    _insert_table_rows,
    _list_comments,
    _list_documents,
    _move_document,
    _read_document,
    _rename_tab,
    _reply_to_comment,
    _resolve_comment,
    _restore_comments,
    _save_comments,
    _update_document,
    _update_document_markdown,
    _update_text_style,
    _upload_document,
)


class TestErrorResponse:
    def test_error_response_format(self):
        result = error_response("Something went wrong", "API_ERROR")
        data = json.loads(result)
        assert data == {"error": "Something went wrong", "code": "API_ERROR"}


class TestListDocuments:
    def test_list_documents_success(self):
        service = MagicMock()
        service.list_documents.return_value = [
            {
                "id": "doc123",
                "name": "Test Doc",
                "url": "https://docs.google.com/document/d/doc123/edit",
                "createdTime": "2024-01-01T00:00:00Z",
                "modifiedTime": "2024-01-02T00:00:00Z",
            }
        ]

        result = _list_documents(service, query="", max_results=10)
        data = json.loads(result)

        assert len(data) == 1
        assert data[0]["id"] == "doc123"
        service.list_documents.assert_called_once_with(query=None, max_results=10)

    def test_list_documents_with_query(self):
        service = MagicMock()
        service.list_documents.return_value = []

        result = _list_documents(service, query="test", max_results=5)
        data = json.loads(result)

        assert data == []
        service.list_documents.assert_called_once_with(query="test", max_results=5)

    def test_list_documents_validation_error(self):
        service = MagicMock()

        result = _list_documents(service, query="", max_results=0)
        data = json.loads(result)

        assert "error" in data
        assert data["code"] == "VALIDATION_ERROR"
        assert "between 1 and 100" in data["error"]

    def test_list_documents_api_error(self):
        service = MagicMock()
        service.list_documents.side_effect = Exception("API error")

        result = _list_documents(service, query="", max_results=10)
        data = json.loads(result)

        assert "error" in data
        assert data["code"] == "API_ERROR"


class TestReadDocument:
    def test_read_document_success(self):
        service = MagicMock()
        service.read_document.return_value = {
            "id": "doc123",
            "title": "Test Doc",
            "content": "Hello, world!",
        }
        service.list_comments.return_value = []

        result = _read_document(service, document_id="doc1234567890")
        data = json.loads(result)

        assert data["id"] == "doc123"
        assert "<untrusted-data-" in data["title"]
        assert "Test Doc" in data["title"]
        assert "<document-content-" in data["content"]
        assert "Hello, world!" in data["content"]
        assert "</document-content-" in data["content"]
        assert "untrusted external data" in data["content"]

    def test_read_document_includes_comments(self):
        service = MagicMock()
        service.read_document.return_value = {
            "id": "doc123",
            "title": "Test Doc",
            "content": "Hello",
        }
        service.list_comments.return_value = [
            {
                "id": "c1",
                "author": "Alice",
                "content": "Fix this",
                "quoted_text": "Hello",
                "resolved": False,
                "replies": [{"author": "Bob", "content": "Done"}],
            }
        ]

        result = _read_document(service, document_id="doc1234567890")
        data = json.loads(result)

        assert data["comment_count"] == 1
        assert len(data["comments"]) == 1
        comment = data["comments"][0]
        assert comment["id"] == "c1"
        assert "<untrusted-data-" in comment["content"]
        assert "Fix this" in comment["content"]
        assert "<untrusted-data-" in comment["quoted_text"]
        assert "<untrusted-data-" in comment["author"]
        assert len(comment["replies"]) == 1
        assert "<untrusted-data-" in comment["replies"][0]["content"]
        assert "<untrusted-data-" in comment["replies"][0]["author"]

    def test_read_document_no_comments(self):
        service = MagicMock()
        service.read_document.return_value = {
            "id": "doc123",
            "title": "Test Doc",
            "content": "Hello",
        }
        service.list_comments.return_value = []

        result = _read_document(service, document_id="doc1234567890")
        data = json.loads(result)

        assert "comments" not in data
        assert "comment_count" not in data

    def test_read_document_comments_failure_nonfatal(self):
        service = MagicMock()
        service.read_document.return_value = {
            "id": "doc123",
            "title": "Test Doc",
            "content": "Hello",
        }
        service.list_comments.side_effect = Exception("Permission denied")

        result = _read_document(service, document_id="doc1234567890")
        data = json.loads(result)

        # Read should still succeed even if comments fail
        assert data["id"] == "doc123"
        assert "comments" not in data

    def test_read_document_multi_tab(self):
        service = MagicMock()
        service.read_document.return_value = {
            "id": "doc123",
            "title": "Multi-Tab Doc",
            "content": "Tab 1 content",
            "tabs": [
                {"tab_id": "t.0", "title": "Overview", "content": "Tab 1 content"},
                {"tab_id": "t.1", "title": "Details", "content": "Tab 2 content"},
            ],
        }
        service.list_comments.return_value = []

        result = _read_document(service, document_id="doc1234567890")
        data = json.loads(result)

        assert len(data["tabs"]) == 2
        assert "<untrusted-data-" in data["tabs"][0]["title"]
        assert "Overview" in data["tabs"][0]["title"]
        assert "<tab-content-" in data["tabs"][0]["content"]
        assert "Tab 1 content" in data["tabs"][0]["content"]
        assert "<tab-content-" in data["tabs"][1]["content"]
        assert "Tab 2 content" in data["tabs"][1]["content"]

    def test_read_document_validation_error(self):
        service = MagicMock()

        result = _read_document(service, document_id="invalid")
        data = json.loads(result)

        assert "error" in data
        assert data["code"] == "VALIDATION_ERROR"

    def test_read_document_api_error(self):
        service = MagicMock()
        service.read_document.side_effect = Exception("Document not found")

        result = _read_document(service, document_id="doc1234567890")
        data = json.loads(result)

        assert "error" in data
        assert data["code"] == "API_ERROR"


class TestCreateDocument:
    def test_create_document_success(self):
        service = MagicMock()
        service.create_document.return_value = {
            "id": "newdoc123",
            "name": "New Document",
            "url": "https://docs.google.com/document/d/newdoc123/edit",
        }

        result = _create_document(
            service, title="New Document", content="", folder_id=""
        )
        data = json.loads(result)

        assert data["id"] == "newdoc123"
        assert "<untrusted-data-" in data["name"]
        assert "New Document" in data["name"]
        service.create_document.assert_called_once_with(
            "New Document", content=None, folder_id=None
        )

    def test_create_document_with_content_and_folder(self):
        service = MagicMock()
        service.create_document.return_value = {
            "id": "newdoc123",
            "name": "New Document",
            "url": "https://docs.google.com/document/d/newdoc123/edit",
        }

        result = _create_document(
            service, title="New Document", content="Hello", folder_id="folder123456789"
        )
        data = json.loads(result)

        assert data["id"] == "newdoc123"
        service.create_document.assert_called_once_with(
            "New Document", content="Hello", folder_id="folder123456789"
        )

    def test_create_document_validation_error_title(self):
        service = MagicMock()

        result = _create_document(service, title="", content="", folder_id="")
        data = json.loads(result)

        assert "error" in data
        assert data["code"] == "VALIDATION_ERROR"

    def test_create_document_validation_error_content_size(self):
        service = MagicMock()

        result = _create_document(
            service, title="Test", content="x" * 2_000_000, folder_id=""
        )
        data = json.loads(result)

        assert "error" in data
        assert data["code"] == "VALIDATION_ERROR"

    def test_create_document_api_error(self):
        service = MagicMock()
        service.create_document.side_effect = Exception("API error")

        result = _create_document(service, title="Test", content="", folder_id="")
        data = json.loads(result)

        assert "error" in data
        assert data["code"] == "API_ERROR"


class TestUpdateDocument:
    def test_update_document_append(self):
        service = MagicMock()
        service.update_document.return_value = {
            "id": "doc123",
            "name": "Updated Doc",
            "url": "https://docs.google.com/document/d/doc123/edit",
            "updatedTime": "2024-01-02T00:00:00Z",
        }

        result = _update_document(
            service, document_id="doc1234567890", content="New content", mode="append"
        )
        data = json.loads(result)

        assert data["id"] == "doc123"
        service.update_document.assert_called_once_with(
            "doc1234567890", "New content", mode="append", tab_id=None
        )

    def test_update_document_replace(self):
        service = MagicMock()
        service.update_document.return_value = {
            "id": "doc123",
            "name": "Updated Doc",
            "url": "https://docs.google.com/document/d/doc123/edit",
            "updatedTime": "2024-01-02T00:00:00Z",
        }

        result = _update_document(
            service, document_id="doc1234567890", content="New content", mode="replace"
        )
        data = json.loads(result)

        assert data["id"] == "doc123"
        service.update_document.assert_called_once_with(
            "doc1234567890", "New content", mode="replace", tab_id=None
        )

    def test_update_document_invalid_mode(self):
        service = MagicMock()

        result = _update_document(
            service, document_id="doc1234567890", content="New content", mode="invalid"
        )
        data = json.loads(result)

        assert "error" in data
        assert data["code"] == "VALIDATION_ERROR"
        assert "append" in data["error"] and "replace" in data["error"]

    def test_update_document_with_tab_id(self):
        service = MagicMock()
        service.update_document.return_value = {
            "id": "doc123",
            "name": "Updated Doc",
            "url": "https://docs.google.com/document/d/doc123/edit",
            "updatedTime": "2024-01-02T00:00:00Z",
        }

        result = _update_document(
            service,
            document_id="doc1234567890",
            content="Tab content",
            mode="append",
            tab_id="t.123",
        )
        data = json.loads(result)

        assert data["id"] == "doc123"
        service.update_document.assert_called_once_with(
            "doc1234567890", "Tab content", mode="append", tab_id="t.123"
        )

    def test_update_document_invalid_tab_id(self):
        service = MagicMock()

        result = _update_document(
            service,
            document_id="doc1234567890",
            content="test",
            mode="append",
            tab_id="invalid tab id with spaces!",
        )
        data = json.loads(result)

        assert "error" in data
        assert data["code"] == "VALIDATION_ERROR"

    def test_update_document_validation_error(self):
        service = MagicMock()

        result = _update_document(
            service, document_id="invalid", content="test", mode="append"
        )
        data = json.loads(result)

        assert "error" in data
        assert data["code"] == "VALIDATION_ERROR"


class TestCommentPreservation:
    def _sample_comments(self):
        return [
            {
                "id": "c1",
                "author": "Gerard",
                "content": "Fix the wording here",
                "resolved": False,
                "quoted_text": "broken sentence",
                "replies": [
                    {"author": "Ugo", "content": "Good catch, will fix"},
                ],
            },
            {
                "id": "c2",
                "author": "Ana",
                "content": "LGTM",
                "resolved": True,
            },
        ]

    def test_save_comments_success(self):
        service = MagicMock()
        service.list_comments.return_value = self._sample_comments()
        result = _save_comments(service, "doc1234567890")
        assert len(result) == 2
        service.list_comments.assert_called_once_with("doc1234567890")

    def test_save_comments_api_failure_returns_empty(self):
        service = MagicMock()
        service.list_comments.side_effect = Exception("API error")
        result = _save_comments(service, "doc1234567890")
        assert result == []

    def test_restore_comments_skips_resolved(self):
        service = MagicMock()
        service.comment_on_document.return_value = {"comment_id": "new1"}
        result = _restore_comments(service, "doc1234567890", self._sample_comments())
        assert result["restored"] == 1
        assert result["failed"] == []
        service.comment_on_document.assert_called_once()

    def test_restore_comments_preserves_author_and_quoted_text(self):
        service = MagicMock()
        service.comment_on_document.return_value = {"comment_id": "new1"}
        _restore_comments(service, "doc1234567890", self._sample_comments())
        call_args = service.comment_on_document.call_args
        assert call_args[0][1] == "[Gerard] Fix the wording here"
        assert call_args[1]["quoted_text"] == "broken sentence"

    def test_restore_comments_recreates_replies(self):
        service = MagicMock()
        service.comment_on_document.return_value = {"comment_id": "new1"}
        _restore_comments(service, "doc1234567890", self._sample_comments())
        service.reply_to_comment.assert_called_once_with(
            "doc1234567890", "new1", "[Ugo] Good catch, will fix"
        )

    def test_restore_comments_handles_creation_failure(self):
        service = MagicMock()
        service.comment_on_document.side_effect = Exception("API error")
        result = _restore_comments(service, "doc1234567890", self._sample_comments())
        assert result["restored"] == 0
        assert len(result["failed"]) == 1
        assert result["failed"][0]["author"] == "Gerard"
        assert result["failed"][0]["quoted_text"] == "broken sentence"

    def test_restore_comments_handles_reply_failure(self):
        service = MagicMock()
        service.comment_on_document.return_value = {"comment_id": "new1"}
        service.reply_to_comment.side_effect = Exception("Reply failed")
        result = _restore_comments(service, "doc1234567890", self._sample_comments())
        assert result["restored"] == 1

    def test_restore_comments_empty_list(self):
        service = MagicMock()
        result = _restore_comments(service, "doc1234567890", [])
        assert result["restored"] == 0
        assert result["failed"] == []
        service.comment_on_document.assert_not_called()

    def test_update_document_replace_preserves_comments(self):
        service = MagicMock()
        service.list_comments.return_value = self._sample_comments()
        service.comment_on_document.return_value = {"comment_id": "new1"}
        service.update_document.return_value = {
            "id": "doc123",
            "name": "Test",
        }
        result = _update_document(
            service, document_id="doc1234567890", content="New", mode="replace"
        )
        data = json.loads(result)
        assert data["comments_restored"] == 1
        assert data["comments_total"] == 2

    def test_update_document_append_skips_comment_preservation(self):
        service = MagicMock()
        service.update_document.return_value = {"id": "doc123", "name": "Test"}
        result = _update_document(
            service, document_id="doc1234567890", content="More", mode="append"
        )
        data = json.loads(result)
        assert "comments_restored" not in data
        service.list_comments.assert_not_called()

    def test_update_markdown_full_doc_preserves_comments(self):
        service = MagicMock()
        service.list_comments.return_value = self._sample_comments()
        service.comment_on_document.return_value = {"comment_id": "new1"}
        service.get_template_styles.return_value = {"namedStyles": {"styles": []}}
        service.update_file_content.return_value = {
            "id": "doc1234567890",
            "name": "Test",
        }
        template_config = TemplateConfig(templates=[])

        with patch("mcp_server.tools.google_docs_tools.markdown_to_docx") as mock_docx:
            mock_docx.return_value = b"PK\x03\x04fake-docx"
            result = _update_document_markdown(
                service,
                template_config,
                document_id="doc1234567890",
                markdown_content="Hello",
            )
            data = json.loads(result)
            assert data["comments_restored"] == 1
            assert data["comments_total"] == 2

    def test_update_markdown_tab_uses_diff(self):
        service = MagicMock()
        service.get_template_styles.return_value = {"namedStyles": {"styles": []}}
        service.update_tab_diff.return_value = {
            "id": "doc1234567890",
            "name": "Test",
            "diff_used": True,
        }
        template_config = TemplateConfig(templates=[])

        result = _update_document_markdown(
            service,
            template_config,
            document_id="doc1234567890",
            markdown_content="Hello",
            tab_id="t.abc123",
        )
        data = json.loads(result)
        assert data["diff_used"] is True
        assert "comments_restored" not in data
        service.list_comments.assert_not_called()

    def test_update_markdown_no_comments_no_extra_fields(self):
        service = MagicMock()
        service.list_comments.return_value = []
        service.get_template_styles.return_value = {"namedStyles": {"styles": []}}
        service.update_file_content.return_value = {
            "id": "doc1234567890",
            "name": "Test",
        }
        template_config = TemplateConfig(templates=[])

        with patch("mcp_server.tools.google_docs_tools.markdown_to_docx") as mock_docx:
            mock_docx.return_value = b"PK\x03\x04fake-docx"
            result = _update_document_markdown(
                service,
                template_config,
                document_id="doc1234567890",
                markdown_content="Hello",
            )
            data = json.loads(result)
            assert "comments_restored" not in data


class TestCommentOnDocument:
    def test_comment_on_document_success(self):
        service = MagicMock()
        service.comment_on_document.return_value = {
            "comment_id": "comment123",
            "document_id": "doc123",
            "content": "Great work!",
        }

        result = _comment_on_document(
            service, document_id="doc1234567890", comment="Great work!", quoted_text=""
        )
        data = json.loads(result)

        assert data["comment_id"] == "comment123"
        service.comment_on_document.assert_called_once_with(
            "doc1234567890", "Great work!", quoted_text=None
        )

    def test_comment_on_document_with_quoted_text(self):
        service = MagicMock()
        service.comment_on_document.return_value = {
            "comment_id": "comment123",
            "document_id": "doc123",
            "content": "Fix this",
        }

        result = _comment_on_document(
            service,
            document_id="doc1234567890",
            comment="Fix this",
            quoted_text="Some text",
        )
        data = json.loads(result)

        assert data["comment_id"] == "comment123"
        service.comment_on_document.assert_called_once_with(
            "doc1234567890", "Fix this", quoted_text="Some text"
        )

    def test_comment_on_document_validation_error(self):
        service = MagicMock()

        result = _comment_on_document(
            service, document_id="doc1234567890", comment="", quoted_text=""
        )
        data = json.loads(result)

        assert "error" in data
        assert data["code"] == "VALIDATION_ERROR"


class TestListComments:
    def test_list_comments_success(self):
        service = MagicMock()
        service.list_comments.return_value = [
            {
                "id": "c1",
                "author": "Alice",
                "content": "Fix this",
                "resolved": False,
                "quoted_text": "broken",
                "replies": [{"author": "Bob", "content": "Done"}],
            }
        ]

        result = _list_comments(service, document_id="doc1234567890")
        data = json.loads(result)

        assert data["comment_count"] == 1
        assert data["document_id"] == "doc1234567890"
        assert len(data["comments"]) == 1

    def test_list_comments_empty(self):
        service = MagicMock()
        service.list_comments.return_value = []

        result = _list_comments(service, document_id="doc1234567890")
        data = json.loads(result)

        assert data["comment_count"] == 0
        assert data["comments"] == []

    def test_list_comments_validation_error(self):
        service = MagicMock()

        result = _list_comments(service, document_id="bad")
        data = json.loads(result)

        assert data["code"] == "VALIDATION_ERROR"


class TestReplyToComment:
    def test_reply_success(self):
        service = MagicMock()
        service.reply_to_comment.return_value = {
            "reply_id": "r1",
            "comment_id": "c1",
            "document_id": "doc123",
            "content": "Fixed!",
        }

        result = _reply_to_comment(
            service,
            document_id="doc1234567890",
            comment_id="comment123",
            reply="Fixed!",
        )
        data = json.loads(result)

        assert data["reply_id"] == "r1"
        service.reply_to_comment.assert_called_once_with(
            "doc1234567890", "comment123", "Fixed!"
        )

    def test_reply_empty_text_error(self):
        service = MagicMock()

        result = _reply_to_comment(
            service,
            document_id="doc1234567890",
            comment_id="comment123",
            reply="",
        )
        data = json.loads(result)

        assert data["code"] == "VALIDATION_ERROR"

    def test_reply_invalid_comment_id(self):
        service = MagicMock()

        result = _reply_to_comment(
            service,
            document_id="doc1234567890",
            comment_id="bad id!",
            reply="test",
        )
        data = json.loads(result)

        assert data["code"] == "VALIDATION_ERROR"


class TestResolveComment:
    def test_resolve_success(self):
        service = MagicMock()
        service.resolve_comment.return_value = {
            "comment_id": "c1",
            "document_id": "doc123",
            "resolved": True,
        }

        result = _resolve_comment(
            service, document_id="doc1234567890", comment_id="comment123"
        )
        data = json.loads(result)

        assert data["resolved"] is True
        service.resolve_comment.assert_called_once_with("doc1234567890", "comment123")

    def test_resolve_invalid_doc_id(self):
        service = MagicMock()

        result = _resolve_comment(service, document_id="bad", comment_id="comment123")
        data = json.loads(result)

        assert data["code"] == "VALIDATION_ERROR"


class TestDeleteComment:
    def test_delete_success(self):
        service = MagicMock()
        service.delete_comment.return_value = {
            "comment_id": "c1",
            "document_id": "doc123",
            "status": "deleted",
        }

        result = _delete_comment(
            service, document_id="doc1234567890", comment_id="comment123"
        )
        data = json.loads(result)

        assert data["status"] == "deleted"
        service.delete_comment.assert_called_once_with("doc1234567890", "comment123")

    def test_delete_invalid_comment_id(self):
        service = MagicMock()

        result = _delete_comment(service, document_id="doc1234567890", comment_id="")
        data = json.loads(result)

        assert data["code"] == "VALIDATION_ERROR"


class TestFindFolder:
    def test_find_folder_found(self):
        service = MagicMock()
        service.find_folder.return_value = {
            "found": True,
            "folder_id": "folder123",
            "name": "My Folder",
        }

        result = _find_folder(service, folder_name="My Folder")
        data = json.loads(result)

        assert data["found"] is True
        assert data["folder_id"] == "folder123"

    def test_find_folder_not_found(self):
        service = MagicMock()
        service.find_folder.return_value = {"found": False}

        result = _find_folder(service, folder_name="Nonexistent")
        data = json.loads(result)

        assert data["found"] is False
        assert "folder_id" not in data

    def test_find_folder_api_error(self):
        service = MagicMock()
        service.find_folder.side_effect = Exception("API error")

        result = _find_folder(service, folder_name="Test")
        data = json.loads(result)

        assert "error" in data
        assert data["code"] == "API_ERROR"


class TestMoveDocument:
    def test_move_document_success(self):
        service = MagicMock()
        service.move_document.return_value = {
            "id": "doc123",
            "name": "My Doc",
            "new_parent_id": "folder456",
        }

        result = _move_document(
            service, document_id="doc1234567890", folder_id="folder123456789"
        )
        data = json.loads(result)

        assert data["id"] == "doc123"
        assert data["new_parent_id"] == "folder456"
        service.move_document.assert_called_once_with(
            "doc1234567890", "folder123456789"
        )

    def test_move_document_validation_error(self):
        service = MagicMock()

        result = _move_document(
            service, document_id="invalid", folder_id="folder123456789"
        )
        data = json.loads(result)

        assert "error" in data
        assert data["code"] == "VALIDATION_ERROR"


class TestDeleteDocument:
    def test_delete_document_step1_nonce_creation(self):
        service = MagicMock()
        nonce_manager = NonceManager()

        result = _delete_document(
            service, nonce_manager, document_id="doc1234567890", nonce=""
        )
        data = json.loads(result)

        assert data["status"] == "confirm_required"
        assert "nonce" in data
        assert data["document_id"] == "doc1234567890"
        assert data["expires_in_seconds"] == 30
        service.trash_document.assert_not_called()

    def test_delete_document_step2_successful_deletion(self):
        service = MagicMock()
        service.trash_document.return_value = {
            "id": "doc123",
            "name": "Deleted Doc",
            "trashed": True,
        }
        nonce_manager = NonceManager()

        # Step 1: Create nonce
        result1 = _delete_document(
            service, nonce_manager, document_id="doc1234567890", nonce=""
        )
        data1 = json.loads(result1)
        nonce = data1["nonce"]

        # Step 2: Delete with nonce
        result2 = _delete_document(
            service, nonce_manager, document_id="doc1234567890", nonce=nonce
        )
        data2 = json.loads(result2)

        assert data2["status"] == "trashed"
        assert data2["document_id"] == "doc1234567890"
        service.trash_document.assert_called_once_with("doc1234567890")

    def test_delete_document_invalid_nonce(self):
        service = MagicMock()
        nonce_manager = NonceManager()

        result = _delete_document(
            service, nonce_manager, document_id="doc1234567890", nonce="invalid_nonce"
        )
        data = json.loads(result)

        assert "error" in data
        assert data["code"] == "NONCE_ERROR"
        service.trash_document.assert_not_called()

    def test_delete_document_validation_error(self):
        service = MagicMock()
        nonce_manager = NonceManager()

        result = _delete_document(
            service, nonce_manager, document_id="invalid", nonce=""
        )
        data = json.loads(result)

        assert "error" in data
        assert data["code"] == "VALIDATION_ERROR"


class TestConvertMarkdownToDoc:
    def test_convert_markdown_template_selection_required(self):
        service = MagicMock()
        template_config = TemplateConfig(
            templates=[
                Template(name="default", doc_id="template123456", default=True),
                Template(name="fancy", doc_id="template789012", default=False),
            ]
        )

        result = _convert_markdown_to_doc(
            service,
            template_config,
            markdown_content="# Hello",
            title="Test",
            template_name="",
            folder_id="",
        )
        data = json.loads(result)

        assert data["status"] == "template_selection_required"
        assert len(data["available_templates"]) == 2
        assert data["available_templates"][0]["name"] == "default"
        assert data["available_templates"][0]["default"] is True

    def test_convert_markdown_with_template(self):
        service = MagicMock()
        service.upload_file.return_value = {
            "id": "newdoc123",
            "name": "Test",
            "url": "https://docs.google.com/document/d/newdoc123/edit",
        }
        service.get_template_styles.return_value = {
            "namedStyles": {
                "styles": [
                    {
                        "namedStyleType": "HEADING_1",
                        "textStyle": {"fontSize": {"magnitude": 20}},
                    }
                ]
            }
        }

        template_config = TemplateConfig(
            templates=[Template(name="default", doc_id="template123456", default=True)]
        )

        with patch("mcp_server.tools.google_docs_tools.markdown_to_docx") as mock_docx:
            mock_docx.return_value = b"PK\x03\x04fake-docx"

            result = _convert_markdown_to_doc(
                service,
                template_config,
                markdown_content="# Hello",
                title="Test",
                template_name="default",
                folder_id="",
            )
            data = json.loads(result)

            assert data["id"] == "newdoc123"
            assert data["template_used"] == "default"
            service.upload_file.assert_called_once()
            mock_docx.assert_called_once()

    def test_convert_markdown_validation_error_title(self):
        service = MagicMock()
        template_config = TemplateConfig(templates=[])

        result = _convert_markdown_to_doc(
            service,
            template_config,
            markdown_content="# Hello",
            title="",
            template_name="",
            folder_id="",
        )
        data = json.loads(result)

        assert "error" in data
        assert data["code"] == "VALIDATION_ERROR"

    def test_convert_markdown_validation_error_invalid_template(self):
        service = MagicMock()
        template_config = TemplateConfig(
            templates=[Template(name="default", doc_id="template123456", default=True)]
        )

        result = _convert_markdown_to_doc(
            service,
            template_config,
            markdown_content="# Hello",
            title="Test",
            template_name="invalid",
            folder_id="",
        )
        data = json.loads(result)

        assert "error" in data
        assert data["code"] == "VALIDATION_ERROR"
        assert "Unknown template" in data["error"]

    def test_convert_markdown_no_templates_config(self):
        service = MagicMock()
        service.upload_file.return_value = {
            "id": "newdoc123",
            "name": "Test",
            "url": "https://docs.google.com/document/d/newdoc123/edit",
        }

        template_config = TemplateConfig(templates=[])

        with patch("mcp_server.tools.google_docs_tools.markdown_to_docx") as mock_docx:
            mock_docx.return_value = b"PK\x03\x04fake-docx"

            result = _convert_markdown_to_doc(
                service,
                template_config,
                markdown_content="Hello",
                title="Test",
                template_name="",
                folder_id="",
            )
            data = json.loads(result)

            assert data["id"] == "newdoc123"
            assert data["template_used"] is None
            service.upload_file.assert_called_once()


class TestUploadDocument:
    def test_upload_document_success(self):
        service = MagicMock()
        service.upload_file.return_value = {
            "id": "uploaded123",
            "name": "My Document",
            "url": "https://docs.google.com/document/d/uploaded123/edit",
        }

        import base64

        file_content = base64.b64encode(b"fake docx content").decode()

        result = _upload_document(
            service,
            file_content_base64=file_content,
            title="My Document",
            mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            folder_id="",
        )
        data = json.loads(result)

        assert data["id"] == "uploaded123"
        assert "<untrusted-data-" in data["name"]
        assert "My Document" in data["name"]
        service.upload_file.assert_called_once()

    def test_upload_document_with_folder(self):
        service = MagicMock()
        service.upload_file.return_value = {
            "id": "uploaded123",
            "name": "My Document",
            "url": "https://docs.google.com/document/d/uploaded123/edit",
        }

        import base64

        file_content = base64.b64encode(b"fake content").decode()

        result = _upload_document(
            service,
            file_content_base64=file_content,
            title="My Document",
            mime_type="application/pdf",
            folder_id="folder123456789",
        )
        data = json.loads(result)

        assert data["id"] == "uploaded123"
        call_args = service.upload_file.call_args
        assert call_args[1]["folder_id"] == "folder123456789"

    def test_upload_document_invalid_mime_type(self):
        service = MagicMock()

        result = _upload_document(
            service,
            file_content_base64="dGVzdA==",
            title="My Document",
            mime_type="application/zip",
            folder_id="",
        )
        data = json.loads(result)

        assert "error" in data
        assert data["code"] == "VALIDATION_ERROR"
        assert "Unsupported MIME type" in data["error"]
        service.upload_file.assert_not_called()

    def test_upload_document_invalid_base64(self):
        service = MagicMock()

        result = _upload_document(
            service,
            file_content_base64="not-valid-base64!!!",
            title="My Document",
            mime_type="application/pdf",
            folder_id="",
        )
        data = json.loads(result)

        assert "error" in data
        assert data["code"] == "VALIDATION_ERROR"

    def test_upload_document_empty_title(self):
        service = MagicMock()

        result = _upload_document(
            service,
            file_content_base64="dGVzdA==",
            title="",
            mime_type="application/pdf",
            folder_id="",
        )
        data = json.loads(result)

        assert "error" in data
        assert data["code"] == "VALIDATION_ERROR"

    def test_upload_document_default_mime_type(self):
        service = MagicMock()
        service.upload_file.return_value = {
            "id": "uploaded123",
            "name": "My Document",
            "url": "https://docs.google.com/document/d/uploaded123/edit",
        }

        import base64

        file_content = base64.b64encode(b"fake content").decode()

        result = _upload_document(
            service,
            file_content_base64=file_content,
            title="My Document",
            mime_type="",
            folder_id="",
        )
        data = json.loads(result)

        assert data["id"] == "uploaded123"
        call_args = service.upload_file.call_args
        assert (
            call_args[1]["mime_type"]
            == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )

    def test_upload_document_api_error(self):
        service = MagicMock()
        service.upload_file.side_effect = Exception("Upload failed")

        import base64

        file_content = base64.b64encode(b"content").decode()

        result = _upload_document(
            service,
            file_content_base64=file_content,
            title="My Document",
            mime_type="application/pdf",
            folder_id="",
        )
        data = json.loads(result)

        assert "error" in data
        assert data["code"] == "API_ERROR"

    def test_upload_document_base64_with_whitespace(self):
        service = MagicMock()
        service.upload_file.return_value = {
            "id": "uploaded123",
            "name": "My Document",
            "url": "https://docs.google.com/document/d/uploaded123/edit",
        }

        import base64

        clean_b64 = base64.b64encode(b"fake docx content").decode()
        # Simulate whitespace/newlines injected by MCP transport
        dirty_b64 = "\n".join(
            clean_b64[i : i + 10] for i in range(0, len(clean_b64), 10)
        )

        result = _upload_document(
            service,
            file_content_base64=dirty_b64,
            title="My Document",
            mime_type="application/pdf",
            folder_id="",
        )
        data = json.loads(result)

        assert data["id"] == "uploaded123"
        service.upload_file.assert_called_once()

    def test_upload_document_from_source_file_id(self):
        service = MagicMock()
        service.copy_file_as_doc.return_value = {
            "id": "copied123456",
            "name": "Copied Document",
            "url": "https://docs.google.com/document/d/copied123456/edit",
        }

        result = _upload_document(
            service,
            title="Copied Document",
            source_file_id="source1234567890",
        )
        data = json.loads(result)

        assert data["id"] == "copied123456"
        assert "<untrusted-data-" in data["name"]
        assert "Copied Document" in data["name"]
        service.copy_file_as_doc.assert_called_once_with(
            file_id="source1234567890",
            title="Copied Document",
            folder_id=None,
        )
        service.upload_file.assert_not_called()

    def test_upload_document_source_file_id_with_folder(self):
        service = MagicMock()
        service.copy_file_as_doc.return_value = {
            "id": "copied123456",
            "name": "Copied Document",
            "url": "https://docs.google.com/document/d/copied123456/edit",
        }

        result = _upload_document(
            service,
            title="Copied Document",
            source_file_id="source1234567890",
            folder_id="folder123456789",
        )
        data = json.loads(result)

        assert data["id"] == "copied123456"
        call_args = service.copy_file_as_doc.call_args
        assert call_args[1]["folder_id"] == "folder123456789"

    def test_upload_document_multiple_inputs_error(self):
        service = MagicMock()

        result = _upload_document(
            service,
            title="My Document",
            file_content_base64="dGVzdA==",
            source_file_id="source1234567890",
        )
        data = json.loads(result)

        assert "error" in data
        assert data["code"] == "VALIDATION_ERROR"
        assert "exactly one" in data["error"]

    def test_upload_document_no_input_error(self):
        service = MagicMock()

        result = _upload_document(
            service,
            title="My Document",
        )
        data = json.loads(result)

        assert "error" in data
        assert data["code"] == "VALIDATION_ERROR"
        assert "exactly one" in data["error"]

    def test_upload_document_file_path_success(self, tmp_path):
        service = MagicMock()
        service.upload_file.return_value = {
            "id": "uploaded123",
            "name": "My Document",
            "url": "https://docs.google.com/document/d/uploaded123/edit",
        }

        # Create a fake docx file
        test_file = tmp_path / "test.docx"
        test_file.write_bytes(b"fake docx content")

        with patch(
            "mcp_server.tools.google_docs_tools._ALLOWED_UPLOAD_DIRS",
            (str(tmp_path) + "/",),
        ):
            result = _upload_document(
                service,
                title="My Document",
                file_path=str(test_file),
            )
            data = json.loads(result)

        assert data["id"] == "uploaded123"
        service.upload_file.assert_called_once()
        call_kwargs = service.upload_file.call_args[1]
        assert call_kwargs["file_bytes"] == b"fake docx content"
        assert (
            call_kwargs["mime_type"]
            == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )

    def test_upload_document_file_path_outside_allowed_dir(self):
        service = MagicMock()

        result = _upload_document(
            service,
            title="My Document",
            file_path="/etc/passwd",
        )
        data = json.loads(result)

        assert "error" in data
        assert data["code"] == "VALIDATION_ERROR"
        assert "/uploads/" in data["error"]
        service.upload_file.assert_not_called()

    def test_upload_document_file_path_not_found(self, tmp_path):
        service = MagicMock()

        with patch(
            "mcp_server.tools.google_docs_tools._ALLOWED_UPLOAD_DIRS",
            (str(tmp_path) + "/",),
        ):
            result = _upload_document(
                service,
                title="My Document",
                file_path=str(tmp_path / "nonexistent.docx"),
            )
            data = json.loads(result)

        assert "error" in data
        assert data["code"] == "VALIDATION_ERROR"
        assert "not found" in data["error"].lower()

    def test_upload_document_file_path_unknown_extension(self, tmp_path):
        service = MagicMock()

        test_file = tmp_path / "test.zip"
        test_file.write_bytes(b"fake content")

        with patch(
            "mcp_server.tools.google_docs_tools._ALLOWED_UPLOAD_DIRS",
            (str(tmp_path) + "/",),
        ):
            result = _upload_document(
                service,
                title="My Document",
                file_path=str(test_file),
            )
            data = json.loads(result)

        assert "error" in data
        assert data["code"] == "VALIDATION_ERROR"
        service.upload_file.assert_not_called()

    def test_upload_document_file_path_symlink_escape(self, tmp_path):
        """Verify symlinks that escape the allowed directory are rejected."""
        service = MagicMock()

        # Create a symlink inside tmp_path that points outside
        link = tmp_path / "escape.docx"
        link.symlink_to("/etc/passwd")

        with patch(
            "mcp_server.tools.google_docs_tools._ALLOWED_UPLOAD_DIRS",
            (str(tmp_path) + "/",),
        ):
            result = _upload_document(
                service,
                title="My Document",
                file_path=str(link),
            )
            data = json.loads(result)

        assert "error" in data
        assert data["code"] == "VALIDATION_ERROR"
        service.upload_file.assert_not_called()


class TestUpdateDocumentMarkdown:
    def test_update_markdown_without_template_skips_style_fetch(self):
        service = MagicMock()
        service.update_file_content.return_value = {
            "id": "doc1234567890",
            "name": "Test",
            "url": "https://docs.google.com/document/d/doc1234567890/edit",
        }

        template_config = TemplateConfig(templates=[])

        service.get_template_styles.return_value = {
            "namedStyles": {
                "styles": [
                    {
                        "namedStyleType": "NORMAL_TEXT",
                        "textStyle": {
                            "fontSize": {"magnitude": 11},
                            "weightedFontFamily": {"fontFamily": "Red Hat Text"},
                        },
                    }
                ]
            }
        }

        with patch("mcp_server.tools.google_docs_tools.markdown_to_docx") as mock_docx:
            mock_docx.return_value = b"PK\x03\x04fake-docx"

            result = _update_document_markdown(
                service,
                template_config,
                document_id="doc1234567890",
                markdown_content="Hello",
                template_name="",
            )
            data = json.loads(result)

            assert data["id"] == "doc1234567890"
            assert data["template_used"] == "preserved"
            # No template specified: reads existing doc styles to preserve them
            service.get_template_styles.assert_called_once_with("doc1234567890")
            service.update_file_content.assert_called_once()
            # Styles extracted from existing doc should be passed through
            mock_docx.assert_called_once()
            assert mock_docx.call_args[0][1] is not None

    def test_update_markdown_no_template_no_existing_styles(self):
        service = MagicMock()
        service.update_file_content.return_value = {
            "id": "doc1234567890",
            "name": "Test",
        }
        service.get_template_styles.return_value = {"namedStyles": {"styles": []}}
        template_config = TemplateConfig(templates=[])

        with patch("mcp_server.tools.google_docs_tools.markdown_to_docx") as mock_docx:
            mock_docx.return_value = b"PK\x03\x04fake-docx"

            result = _update_document_markdown(
                service,
                template_config,
                document_id="doc1234567890",
                markdown_content="Hello",
                template_name="",
            )
            data = json.loads(result)

            assert data["template_used"] is None
            mock_docx.assert_called_once_with("Hello", {})

    def test_update_markdown_with_template(self):
        service = MagicMock()
        service.update_file_content.return_value = {
            "id": "doc1234567890",
            "name": "Test",
            "url": "https://docs.google.com/document/d/doc1234567890/edit",
        }
        service.get_template_styles.return_value = {
            "namedStyles": {
                "styles": [
                    {
                        "namedStyleType": "HEADING_1",
                        "textStyle": {"fontSize": {"magnitude": 20}},
                    }
                ]
            }
        }

        template_config = TemplateConfig(
            templates=[Template(name="default", doc_id="template123456", default=True)]
        )

        with patch("mcp_server.tools.google_docs_tools.markdown_to_docx") as mock_docx:
            mock_docx.return_value = b"PK\x03\x04fake-docx"

            result = _update_document_markdown(
                service,
                template_config,
                document_id="doc1234567890",
                markdown_content="# Title",
                template_name="default",
            )
            data = json.loads(result)

            assert data["id"] == "doc1234567890"
            assert data["template_used"] == "default"
            service.update_file_content.assert_called_once()
            mock_docx.assert_called_once()

    def test_update_markdown_validation_error_doc_id(self):
        service = MagicMock()
        template_config = TemplateConfig(templates=[])

        result = _update_document_markdown(
            service,
            template_config,
            document_id="invalid",
            markdown_content="Hello",
            template_name="",
        )
        data = json.loads(result)

        assert "error" in data
        assert data["code"] == "VALIDATION_ERROR"

    def test_update_markdown_validation_error_content_size(self):
        service = MagicMock()
        template_config = TemplateConfig(templates=[])

        result = _update_document_markdown(
            service,
            template_config,
            document_id="doc1234567890",
            markdown_content="x" * 6_000_000,
            template_name="",
        )
        data = json.loads(result)

        assert "error" in data
        assert data["code"] == "VALIDATION_ERROR"

    def test_update_markdown_invalid_template(self):
        service = MagicMock()
        template_config = TemplateConfig(
            templates=[Template(name="default", doc_id="template123456", default=True)]
        )

        result = _update_document_markdown(
            service,
            template_config,
            document_id="doc1234567890",
            markdown_content="# Hello",
            template_name="nonexistent",
        )
        data = json.loads(result)

        assert "error" in data
        assert data["code"] == "VALIDATION_ERROR"
        assert "Unknown template" in data["error"]

    def test_update_markdown_api_error(self):
        service = MagicMock()
        service.update_file_content.side_effect = Exception("API error")
        service.get_template_styles.return_value = {"namedStyles": {"styles": []}}
        template_config = TemplateConfig(templates=[])

        with patch("mcp_server.tools.google_docs_tools.markdown_to_docx") as mock_docx:
            mock_docx.return_value = b"PK\x03\x04fake-docx"

            result = _update_document_markdown(
                service,
                template_config,
                document_id="doc1234567890",
                markdown_content="Hello",
                template_name="",
            )
            data = json.loads(result)

            assert "error" in data
            assert data["code"] == "API_ERROR"


class TestUpdateDocumentMarkdownWithTabId:
    def test_update_markdown_with_tab_id(self):
        service = MagicMock()
        service.get_template_styles.return_value = {"namedStyles": {"styles": []}}
        service.update_tab_diff.return_value = {
            "id": "doc1234567890",
            "name": "Test",
            "url": "https://docs.google.com/document/d/doc1234567890/edit",
            "updatedTime": "2026-01-01T00:00:00Z",
            "diff_used": True,
        }
        template_config = TemplateConfig(templates=[])

        result = _update_document_markdown(
            service,
            template_config,
            document_id="doc1234567890",
            markdown_content="# Hello\n\nWorld",
            template_name="",
            tab_id="t.abc123",
        )
        data = json.loads(result)

        assert data["id"] == "doc1234567890"
        assert data["tab_id"] == "t.abc123"
        service.update_tab_diff.assert_called_once()
        service.update_file_content.assert_not_called()

    def test_update_markdown_with_tab_id_and_template(self):
        service = MagicMock()
        service.get_template_styles.return_value = {
            "namedStyles": {
                "styles": [
                    {
                        "namedStyleType": "HEADING_1",
                        "textStyle": {"fontSize": {"magnitude": 20}},
                    }
                ]
            }
        }
        service.update_tab_diff.return_value = {
            "id": "doc1234567890",
            "name": "Test",
            "url": "https://docs.google.com/document/d/doc1234567890/edit",
            "updatedTime": "2026-01-01T00:00:00Z",
            "diff_used": True,
        }
        template_config = TemplateConfig(
            templates=[Template(name="default", doc_id="template123456", default=True)]
        )

        result = _update_document_markdown(
            service,
            template_config,
            document_id="doc1234567890",
            markdown_content="# Hello",
            template_name="default",
            tab_id="t.abc123",
        )
        data = json.loads(result)

        assert data["template_used"] == "default"
        assert data["tab_id"] == "t.abc123"
        service.update_tab_diff.assert_called_once()

    def test_update_markdown_invalid_tab_id(self):
        service = MagicMock()
        template_config = TemplateConfig(templates=[])

        result = _update_document_markdown(
            service,
            template_config,
            document_id="doc1234567890",
            markdown_content="Hello",
            template_name="",
            tab_id="invalid tab id!",
        )
        data = json.loads(result)

        assert "error" in data
        assert data["code"] == "VALIDATION_ERROR"

    def test_update_markdown_tab_id_calls_batch_requests(self):
        service = MagicMock()
        service.get_template_styles.return_value = {"namedStyles": {"styles": []}}
        service.update_tab_diff.return_value = {
            "id": "doc1234567890",
            "name": "Test",
            "diff_used": True,
        }
        template_config = TemplateConfig(templates=[])

        with patch(
            "mcp_server.tools.google_docs_tools.blocks_to_batch_requests"
        ) as mock_batch:
            mock_batch.return_value = [
                {"insertText": {"location": {"index": 1}, "text": "Hi\n"}}
            ]

            _update_document_markdown(
                service,
                template_config,
                document_id="doc1234567890",
                markdown_content="Hi",
                template_name="",
                tab_id="t.abc123",
            )

            mock_batch.assert_called_once()
            assert mock_batch.call_args[1]["tab_id"] == "t.abc123"


class TestCreateTab:
    def test_create_tab_success(self):
        service = MagicMock()
        service.add_tab.return_value = {
            "tab_id": "t.abc123",
            "title": "New Tab",
            "document_id": "doc1234567890",
        }

        result = _create_tab(service, document_id="doc1234567890", title="New Tab")
        data = json.loads(result)

        assert data["tab_id"] == "t.abc123"
        assert data["title"] == "New Tab"
        assert data["document_id"] == "doc1234567890"
        service.add_tab.assert_called_once_with("doc1234567890", "New Tab")

    def test_create_tab_validation_error_doc_id(self):
        service = MagicMock()

        result = _create_tab(service, document_id="bad", title="Tab")
        data = json.loads(result)

        assert data["code"] == "VALIDATION_ERROR"

    def test_create_tab_validation_error_title(self):
        service = MagicMock()

        result = _create_tab(service, document_id="doc1234567890", title="")
        data = json.loads(result)

        assert data["code"] == "VALIDATION_ERROR"

    def test_create_tab_api_error(self):
        service = MagicMock()
        service.add_tab.side_effect = Exception("API error")

        result = _create_tab(service, document_id="doc1234567890", title="Tab")
        data = json.loads(result)

        assert data["code"] == "API_ERROR"


class TestDeleteTab:
    def test_delete_tab_step1_nonce_creation(self):
        service = MagicMock()
        nonce_manager = NonceManager()

        result = _delete_tab(
            service, nonce_manager, document_id="doc1234567890", tab_id="t.abc123"
        )
        data = json.loads(result)

        assert data["status"] == "confirm_required"
        assert "nonce" in data
        assert data["document_id"] == "doc1234567890"
        assert data["tab_id"] == "t.abc123"
        assert data["expires_in_seconds"] == 30
        service.delete_tab.assert_not_called()

    def test_delete_tab_step2_successful_deletion(self):
        service = MagicMock()
        service.delete_tab.return_value = {
            "document_id": "doc1234567890",
            "deleted_tab_id": "t.abc123",
        }
        nonce_manager = NonceManager()

        result1 = _delete_tab(
            service, nonce_manager, document_id="doc1234567890", tab_id="t.abc123"
        )
        data1 = json.loads(result1)
        nonce = data1["nonce"]

        result2 = _delete_tab(
            service,
            nonce_manager,
            document_id="doc1234567890",
            tab_id="t.abc123",
            nonce=nonce,
        )
        data2 = json.loads(result2)

        assert data2["deleted_tab_id"] == "t.abc123"
        service.delete_tab.assert_called_once_with("doc1234567890", "t.abc123")

    def test_delete_tab_invalid_nonce(self):
        service = MagicMock()
        nonce_manager = NonceManager()

        result = _delete_tab(
            service,
            nonce_manager,
            document_id="doc1234567890",
            tab_id="t.abc123",
            nonce="invalid_nonce",
        )
        data = json.loads(result)

        assert data["code"] == "NONCE_ERROR"
        service.delete_tab.assert_not_called()

    def test_delete_tab_validation_error_tab_id(self):
        service = MagicMock()
        nonce_manager = NonceManager()

        result = _delete_tab(
            service, nonce_manager, document_id="doc1234567890", tab_id=""
        )
        data = json.loads(result)

        assert data["code"] == "VALIDATION_ERROR"

    def test_delete_tab_api_error(self):
        service = MagicMock()
        service.delete_tab.side_effect = Exception("Cannot delete last tab")
        nonce_manager = NonceManager()

        result1 = _delete_tab(
            service, nonce_manager, document_id="doc1234567890", tab_id="t.0"
        )
        nonce = json.loads(result1)["nonce"]

        result2 = _delete_tab(
            service,
            nonce_manager,
            document_id="doc1234567890",
            tab_id="t.0",
            nonce=nonce,
        )
        data = json.loads(result2)

        assert data["code"] == "API_ERROR"


class TestRenameTab:
    def test_rename_tab_success(self):
        service = MagicMock()
        service.rename_tab.return_value = {
            "document_id": "doc1234567890",
            "tab_id": "t.abc123",
            "title": "Renamed Tab",
        }

        result = _rename_tab(
            service,
            document_id="doc1234567890",
            tab_id="t.abc123",
            title="Renamed Tab",
        )
        data = json.loads(result)

        assert data["tab_id"] == "t.abc123"
        assert data["title"] == "Renamed Tab"
        service.rename_tab.assert_called_once_with(
            "doc1234567890", "t.abc123", "Renamed Tab"
        )

    def test_rename_tab_validation_error_tab_id(self):
        service = MagicMock()

        result = _rename_tab(
            service, document_id="doc1234567890", tab_id="", title="New"
        )
        data = json.loads(result)

        assert data["code"] == "VALIDATION_ERROR"

    def test_rename_tab_validation_error_title(self):
        service = MagicMock()

        result = _rename_tab(
            service, document_id="doc1234567890", tab_id="t.0", title=""
        )
        data = json.loads(result)

        assert data["code"] == "VALIDATION_ERROR"

    def test_rename_tab_api_error(self):
        service = MagicMock()
        service.rename_tab.side_effect = Exception("API error")

        result = _rename_tab(
            service, document_id="doc1234567890", tab_id="t.0", title="New"
        )
        data = json.loads(result)

        assert data["code"] == "API_ERROR"


class TestUpdateTextStyle:
    def test_bold_and_font_size(self):
        service = MagicMock()
        service.update_text_style.return_value = {
            "id": "doc1234567890",
            "name": "Test Doc",
            "url": "https://docs.google.com/document/d/doc1234567890/edit",
            "updatedTime": "2024-01-01T00:00:00Z",
        }
        result = json.loads(
            _update_text_style(service, "doc1234567890", bold=True, font_size=14.0)
        )
        assert result["id"] == "doc1234567890"
        service.update_text_style.assert_called_once_with(
            "doc1234567890", bold=True, font_size=14.0
        )

    def test_all_properties(self):
        service = MagicMock()
        service.update_text_style.return_value = {
            "id": "doc1234567890",
            "name": "Test Doc",
            "url": "https://docs.google.com/document/d/doc1234567890/edit",
            "updatedTime": "2024-01-01T00:00:00Z",
        }
        result = json.loads(
            _update_text_style(
                service,
                "doc1234567890",
                start_index=5,
                end_index=20,
                bold=True,
                italic=False,
                underline=True,
                font_family="Arial",
                font_size=18.0,
                foreground_color="#FF0000",
                alignment="CENTER",
                tab_id="t.0",
            )
        )
        assert result["id"] == "doc1234567890"
        service.update_text_style.assert_called_once_with(
            "doc1234567890",
            start_index=5,
            end_index=20,
            bold=True,
            italic=False,
            underline=True,
            font_family="Arial",
            font_size=18.0,
            foreground_color_rgb="#FF0000",
            alignment="CENTER",
            tab_id="t.0",
        )

    def test_no_properties_returns_error(self):
        service = MagicMock()
        result = json.loads(_update_text_style(service, "doc1234567890"))
        assert result["code"] == "VALIDATION_ERROR"
        assert "At least one" in result["error"]

    def test_only_range_no_style_returns_error(self):
        service = MagicMock()
        result = json.loads(
            _update_text_style(service, "doc1234567890", start_index=0, end_index=10)
        )
        assert result["code"] == "VALIDATION_ERROR"
        assert "At least one" in result["error"]

    def test_bold_false_is_valid_style(self):
        service = MagicMock()
        service.update_text_style.return_value = {
            "id": "doc1234567890",
            "name": "D",
            "url": "https://docs.google.com/document/d/doc1234567890/edit",
            "updatedTime": "2024-01-01T00:00:00Z",
        }
        result = json.loads(_update_text_style(service, "doc1234567890", bold=False))
        assert "id" in result
        service.update_text_style.assert_called_once_with("doc1234567890", bold=False)

    def test_invalid_alignment(self):
        service = MagicMock()
        result = json.loads(
            _update_text_style(service, "doc1234567890", alignment="LEFT")
        )
        assert result["code"] == "VALIDATION_ERROR"
        assert "alignment" in result["error"]

    def test_valid_alignments(self):
        for align in ("START", "CENTER", "END", "JUSTIFIED"):
            service = MagicMock()
            service.update_text_style.return_value = {
                "id": "doc1234567890",
                "name": "D",
                "url": "https://docs.google.com/document/d/doc1234567890/edit",
                "updatedTime": "2024-01-01T00:00:00Z",
            }
            result = json.loads(
                _update_text_style(service, "doc1234567890", alignment=align)
            )
            assert "id" in result

    def test_alignment_case_insensitive(self):
        service = MagicMock()
        service.update_text_style.return_value = {
            "id": "doc1234567890",
            "name": "D",
            "url": "https://docs.google.com/document/d/doc1234567890/edit",
            "updatedTime": "2024-01-01T00:00:00Z",
        }
        result = json.loads(
            _update_text_style(service, "doc1234567890", alignment="justified")
        )
        assert "id" in result
        service.update_text_style.assert_called_once_with(
            "doc1234567890", alignment="JUSTIFIED"
        )

    def test_invalid_color_format(self):
        service = MagicMock()
        result = json.loads(
            _update_text_style(service, "doc1234567890", foreground_color="red")
        )
        assert result["code"] == "VALIDATION_ERROR"

    def test_valid_hex_color(self):
        service = MagicMock()
        service.update_text_style.return_value = {
            "id": "doc1234567890",
            "name": "D",
            "url": "https://docs.google.com/document/d/doc1234567890/edit",
            "updatedTime": "2024-01-01T00:00:00Z",
        }
        result = json.loads(
            _update_text_style(service, "doc1234567890", foreground_color="#00FF00")
        )
        assert "id" in result

    def test_font_size_zero_returns_error(self):
        service = MagicMock()
        result = json.loads(_update_text_style(service, "doc1234567890", font_size=0.0))
        assert result["code"] == "VALIDATION_ERROR"

    def test_font_size_too_large(self):
        service = MagicMock()
        result = json.loads(
            _update_text_style(service, "doc1234567890", font_size=1001.0)
        )
        assert result["code"] == "VALIDATION_ERROR"

    def test_font_family_too_long(self):
        service = MagicMock()
        result = json.loads(
            _update_text_style(service, "doc1234567890", font_family="A" * 256)
        )
        assert result["code"] == "VALIDATION_ERROR"

    def test_invalid_document_id(self):
        service = MagicMock()
        result = json.loads(_update_text_style(service, "bad!", bold=True))
        assert result["code"] == "VALIDATION_ERROR"

    def test_with_tab_id(self):
        service = MagicMock()
        service.update_text_style.return_value = {
            "id": "doc1234567890",
            "name": "D",
            "url": "https://docs.google.com/document/d/doc1234567890/edit",
            "updatedTime": "2024-01-01T00:00:00Z",
        }
        result = json.loads(
            _update_text_style(service, "doc1234567890", bold=True, tab_id="t.0")
        )
        assert "id" in result
        service.update_text_style.assert_called_once_with(
            "doc1234567890", bold=True, tab_id="t.0"
        )

    def test_name_tagged_untrusted(self):
        service = MagicMock()
        service.update_text_style.return_value = {
            "id": "doc1234567890",
            "name": "My Doc",
            "url": "https://docs.google.com/document/d/doc1234567890/edit",
            "updatedTime": "2024-01-01T00:00:00Z",
        }
        result = json.loads(_update_text_style(service, "doc1234567890", bold=True))
        assert "<untrusted-data-" in result["name"]
        assert "My Doc" in result["name"]

    def test_api_error(self):
        service = MagicMock()
        service.update_text_style.side_effect = Exception("API failure")
        result = json.loads(_update_text_style(service, "doc1234567890", bold=True))
        assert result["code"] == "API_ERROR"


class TestFindReplaceDocument:
    def test_single_replacement(self):
        service = MagicMock()
        service.batch_update.return_value = {
            "replies": [{"replaceAllText": {"occurrencesChanged": 3}}]
        }
        replacements = json.dumps([{"find": "foo", "replace": "bar"}])
        result = json.loads(
            _find_replace_document(service, "doc1234567890", replacements)
        )
        assert result["status"] == "success"
        assert result["total_occurrences_changed"] == 3
        assert result["per_replacement"] == [3]
        assert result["replacements_requested"] == 1
        reqs = service.batch_update.call_args[0][1]
        assert len(reqs) == 1
        assert reqs[0]["replaceAllText"]["containsText"]["text"] == "foo"
        assert reqs[0]["replaceAllText"]["replaceText"] == "bar"
        assert reqs[0]["replaceAllText"]["containsText"]["matchCase"] is True

    def test_multiple_replacements(self):
        service = MagicMock()
        service.batch_update.return_value = {
            "replies": [
                {"replaceAllText": {"occurrencesChanged": 2}},
                {"replaceAllText": {"occurrencesChanged": 1}},
            ]
        }
        replacements = json.dumps(
            [
                {"find": "old1", "replace": "new1"},
                {"find": "old2", "replace": "new2"},
            ]
        )
        result = json.loads(
            _find_replace_document(service, "doc1234567890", replacements)
        )
        assert result["total_occurrences_changed"] == 3
        assert result["per_replacement"] == [2, 1]
        assert result["replacements_requested"] == 2

    def test_with_tab_id(self):
        service = MagicMock()
        service.batch_update.return_value = {
            "replies": [{"replaceAllText": {"occurrencesChanged": 1}}]
        }
        replacements = json.dumps([{"find": "x", "replace": "y"}])
        result = json.loads(
            _find_replace_document(
                service, "doc1234567890", replacements, tab_id="t.abc123456"
            )
        )
        assert result["tab_id"] == "t.abc123456"
        reqs = service.batch_update.call_args[0][1]
        assert reqs[0]["replaceAllText"]["tabsCriteria"] == {"tabIds": ["t.abc123456"]}

    def test_case_insensitive(self):
        service = MagicMock()
        service.batch_update.return_value = {
            "replies": [{"replaceAllText": {"occurrencesChanged": 5}}]
        }
        replacements = json.dumps([{"find": "Hello", "replace": "Hi"}])
        result = json.loads(
            _find_replace_document(
                service, "doc1234567890", replacements, match_case=False
            )
        )
        assert result["total_occurrences_changed"] == 5
        reqs = service.batch_update.call_args[0][1]
        assert reqs[0]["replaceAllText"]["containsText"]["matchCase"] is False

    def test_no_tab_id_omits_tabs_criteria(self):
        service = MagicMock()
        service.batch_update.return_value = {
            "replies": [{"replaceAllText": {"occurrencesChanged": 1}}]
        }
        replacements = json.dumps([{"find": "a", "replace": "b"}])
        _find_replace_document(service, "doc1234567890", replacements)
        reqs = service.batch_update.call_args[0][1]
        assert "tabsCriteria" not in reqs[0]["replaceAllText"]

    def test_invalid_json(self):
        service = MagicMock()
        result = json.loads(
            _find_replace_document(service, "doc1234567890", "not json")
        )
        assert result["code"] == "VALIDATION_ERROR"
        assert "valid JSON" in result["error"]

    def test_not_array(self):
        service = MagicMock()
        result = json.loads(
            _find_replace_document(service, "doc1234567890", '{"find":"a"}')
        )
        assert result["code"] == "VALIDATION_ERROR"
        assert "array" in result["error"]

    def test_empty_array(self):
        service = MagicMock()
        result = json.loads(_find_replace_document(service, "doc1234567890", "[]"))
        assert result["code"] == "VALIDATION_ERROR"
        assert "empty" in result["error"]

    def test_too_many_replacements(self):
        service = MagicMock()
        pairs = [{"find": f"f{i}", "replace": f"r{i}"} for i in range(101)]
        result = json.loads(
            _find_replace_document(service, "doc1234567890", json.dumps(pairs))
        )
        assert result["code"] == "VALIDATION_ERROR"
        assert "100" in result["error"]

    def test_missing_find_key(self):
        service = MagicMock()
        replacements = json.dumps([{"replace": "bar"}])
        result = json.loads(
            _find_replace_document(service, "doc1234567890", replacements)
        )
        assert result["code"] == "VALIDATION_ERROR"
        assert "find" in result["error"]

    def test_empty_find_value(self):
        service = MagicMock()
        replacements = json.dumps([{"find": "", "replace": "bar"}])
        result = json.loads(
            _find_replace_document(service, "doc1234567890", replacements)
        )
        assert result["code"] == "VALIDATION_ERROR"

    def test_non_string_values(self):
        service = MagicMock()
        replacements = json.dumps([{"find": 123, "replace": "bar"}])
        result = json.loads(
            _find_replace_document(service, "doc1234567890", replacements)
        )
        assert result["code"] == "VALIDATION_ERROR"

    def test_invalid_document_id(self):
        service = MagicMock()
        replacements = json.dumps([{"find": "a", "replace": "b"}])
        result = json.loads(_find_replace_document(service, "short", replacements))
        assert result["code"] == "VALIDATION_ERROR"

    def test_api_error(self):
        service = MagicMock()
        service.batch_update.side_effect = Exception("API failure")
        replacements = json.dumps([{"find": "a", "replace": "b"}])
        result = json.loads(
            _find_replace_document(service, "doc1234567890", replacements)
        )
        assert result["code"] == "API_ERROR"

    def test_zero_occurrences(self):
        service = MagicMock()
        service.batch_update.return_value = {
            "replies": [{"replaceAllText": {"occurrencesChanged": 0}}]
        }
        replacements = json.dumps([{"find": "nonexistent", "replace": "new"}])
        result = json.loads(
            _find_replace_document(service, "doc1234567890", replacements)
        )
        assert result["status"] == "success"
        assert result["total_occurrences_changed"] == 0
        assert result["per_replacement"] == [0]

    def test_replace_with_empty_string(self):
        service = MagicMock()
        service.batch_update.return_value = {
            "replies": [{"replaceAllText": {"occurrencesChanged": 2}}]
        }
        replacements = json.dumps([{"find": "remove me", "replace": ""}])
        result = json.loads(
            _find_replace_document(service, "doc1234567890", replacements)
        )
        assert result["status"] == "success"
        assert result["total_occurrences_changed"] == 2


def _make_table_content(rows, cols, start_index=10):
    """Build a mock document body content list with one table."""
    idx = start_index
    table_start = idx
    table_rows = []
    for _r in range(rows):
        row_start = idx + 1
        cells = []
        for c in range(cols):
            cell_start = row_start + c * 3
            cells.append(
                {
                    "startIndex": cell_start,
                    "endIndex": cell_start + 2,
                    "content": [
                        {
                            "startIndex": cell_start + 1,
                            "endIndex": cell_start + 2,
                            "paragraph": {
                                "elements": [
                                    {
                                        "startIndex": cell_start + 1,
                                        "endIndex": cell_start + 2,
                                        "textRun": {"content": "\n"},
                                    }
                                ]
                            },
                        }
                    ],
                }
            )
        row_end = row_start + cols * 3
        table_rows.append(
            {
                "startIndex": row_start,
                "endIndex": row_end,
                "tableCells": cells,
            }
        )
        idx = row_end
    return [
        {
            "startIndex": table_start,
            "endIndex": idx,
            "table": {
                "rows": rows,
                "columns": cols,
                "tableRows": table_rows,
            },
        }
    ]


class TestInsertTableRows:
    def test_insert_single_row(self):
        service = MagicMock()
        before = _make_table_content(2, 3)
        after = _make_table_content(3, 3)
        service.get_document_body_content.side_effect = [before, after]
        service.batch_update.return_value = {}

        rows = json.dumps([["a", "b", "c"]])
        result = json.loads(_insert_table_rows(service, "doc1234567890", 0, 0, rows))

        assert result["status"] == "success"
        assert result["rows_inserted"] == 1
        assert result["table_index"] == 0
        assert result["after_row"] == 0
        assert service.batch_update.call_count == 2

        insert_reqs = service.batch_update.call_args_list[0][0][1]
        assert len(insert_reqs) == 1
        assert "insertTableRow" in insert_reqs[0]
        loc = insert_reqs[0]["insertTableRow"]
        assert loc["tableCellLocation"]["rowIndex"] == 0
        assert loc["insertBelow"] is True

    def test_insert_multiple_rows(self):
        service = MagicMock()
        before = _make_table_content(2, 2)
        after = _make_table_content(4, 2)
        service.get_document_body_content.side_effect = [before, after]
        service.batch_update.return_value = {}

        rows = json.dumps([["a", "b"], ["c", "d"]])
        result = json.loads(_insert_table_rows(service, "doc1234567890", 0, 0, rows))

        assert result["rows_inserted"] == 2
        insert_reqs = service.batch_update.call_args_list[0][0][1]
        assert len(insert_reqs) == 2
        assert insert_reqs[0]["insertTableRow"]["tableCellLocation"]["rowIndex"] == 0
        assert insert_reqs[1]["insertTableRow"]["tableCellLocation"]["rowIndex"] == 1

    def test_append_row_with_minus_one(self):
        service = MagicMock()
        before = _make_table_content(3, 2)
        after = _make_table_content(4, 2)
        service.get_document_body_content.side_effect = [before, after]
        service.batch_update.return_value = {}

        rows = json.dumps([["x", "y"]])
        result = json.loads(_insert_table_rows(service, "doc1234567890", 0, -1, rows))

        assert result["status"] == "success"
        assert result["after_row"] == 2
        insert_reqs = service.batch_update.call_args_list[0][0][1]
        assert insert_reqs[0]["insertTableRow"]["tableCellLocation"]["rowIndex"] == 2

    def test_with_tab_id(self):
        service = MagicMock()
        before = _make_table_content(2, 2)
        after = _make_table_content(3, 2)
        service.get_document_body_content.side_effect = [before, after]
        service.batch_update.return_value = {}

        rows = json.dumps([["a", "b"]])
        result = json.loads(
            _insert_table_rows(
                service, "doc1234567890", 0, 0, rows, tab_id="t.abc123456"
            )
        )

        assert result["tab_id"] == "t.abc123456"
        insert_reqs = service.batch_update.call_args_list[0][0][1]
        loc = insert_reqs[0]["insertTableRow"]["tableCellLocation"]
        assert loc["tableStartLocation"]["tabId"] == "t.abc123456"

        service.get_document_body_content.assert_any_call(
            "doc1234567890", "t.abc123456"
        )

    def test_empty_cells_skip_insert_text(self):
        service = MagicMock()
        before = _make_table_content(2, 3)
        after = _make_table_content(3, 3)
        service.get_document_body_content.side_effect = [before, after]
        service.batch_update.return_value = {}

        rows = json.dumps([["a", "", "c"]])
        _insert_table_rows(service, "doc1234567890", 0, 0, rows)

        text_reqs = service.batch_update.call_args_list[1][0][1]
        texts = [r["insertText"]["text"] for r in text_reqs]
        assert "a" in texts
        assert "c" in texts
        assert "" not in texts
        assert len(text_reqs) == 2

    def test_all_empty_cells_no_second_batch(self):
        service = MagicMock()
        before = _make_table_content(2, 2)
        after = _make_table_content(3, 2)
        service.get_document_body_content.side_effect = [before, after]
        service.batch_update.return_value = {}

        rows = json.dumps([["", ""]])
        _insert_table_rows(service, "doc1234567890", 0, 0, rows)

        assert service.batch_update.call_count == 1

    def test_text_inserted_in_reverse_index_order(self):
        service = MagicMock()
        before = _make_table_content(2, 3)
        after = _make_table_content(3, 3)
        service.get_document_body_content.side_effect = [before, after]
        service.batch_update.return_value = {}

        rows = json.dumps([["a", "b", "c"]])
        _insert_table_rows(service, "doc1234567890", 0, 0, rows)

        text_reqs = service.batch_update.call_args_list[1][0][1]
        indices = [r["insertText"]["location"]["index"] for r in text_reqs]
        assert indices == sorted(indices, reverse=True)

    def test_second_table_index(self):
        service = MagicMock()
        table1 = _make_table_content(2, 2, start_index=10)
        table2 = _make_table_content(2, 3, start_index=100)
        before = table1 + table2
        after_table1 = _make_table_content(2, 2, start_index=10)
        after_table2 = _make_table_content(3, 3, start_index=100)
        after = after_table1 + after_table2
        service.get_document_body_content.side_effect = [before, after]
        service.batch_update.return_value = {}

        rows = json.dumps([["a", "b", "c"]])
        result = json.loads(_insert_table_rows(service, "doc1234567890", 1, 0, rows))

        assert result["table_index"] == 1
        insert_reqs = service.batch_update.call_args_list[0][0][1]
        assert (
            insert_reqs[0]["insertTableRow"]["tableCellLocation"]["tableStartLocation"][
                "index"
            ]
            == 100
        )

    def test_invalid_json(self):
        service = MagicMock()
        result = json.loads(
            _insert_table_rows(service, "doc1234567890", 0, 0, "not json")
        )
        assert result["code"] == "VALIDATION_ERROR"
        assert "valid JSON" in result["error"]

    def test_rows_not_array(self):
        service = MagicMock()
        result = json.loads(
            _insert_table_rows(service, "doc1234567890", 0, 0, '{"a": 1}')
        )
        assert result["code"] == "VALIDATION_ERROR"
        assert "array" in result["error"]

    def test_empty_rows(self):
        service = MagicMock()
        result = json.loads(_insert_table_rows(service, "doc1234567890", 0, 0, "[]"))
        assert result["code"] == "VALIDATION_ERROR"
        assert "empty" in result["error"]

    def test_too_many_rows(self):
        service = MagicMock()
        rows = json.dumps([["a"] for _ in range(51)])
        result = json.loads(_insert_table_rows(service, "doc1234567890", 0, 0, rows))
        assert result["code"] == "VALIDATION_ERROR"
        assert "50" in result["error"]

    def test_row_not_array(self):
        service = MagicMock()
        rows = json.dumps(["not an array"])
        result = json.loads(_insert_table_rows(service, "doc1234567890", 0, 0, rows))
        assert result["code"] == "VALIDATION_ERROR"
        assert "array" in result["error"]

    def test_negative_table_index(self):
        service = MagicMock()
        rows = json.dumps([["a"]])
        result = json.loads(_insert_table_rows(service, "doc1234567890", -1, 0, rows))
        assert result["code"] == "VALIDATION_ERROR"
        assert "table_index" in result["error"]

    def test_table_index_out_of_range(self):
        service = MagicMock()
        service.get_document_body_content.return_value = _make_table_content(2, 2)
        rows = json.dumps([["a", "b"]])
        result = json.loads(_insert_table_rows(service, "doc1234567890", 5, 0, rows))
        assert result["code"] == "VALIDATION_ERROR"
        assert "out of range" in result["error"]

    def test_no_tables_in_document(self):
        service = MagicMock()
        service.get_document_body_content.return_value = [
            {"paragraph": {"elements": []}, "startIndex": 1, "endIndex": 5}
        ]
        rows = json.dumps([["a"]])
        result = json.loads(_insert_table_rows(service, "doc1234567890", 0, 0, rows))
        assert result["code"] == "NOT_FOUND"
        assert "no tables" in result["error"]

    def test_after_row_out_of_range(self):
        service = MagicMock()
        service.get_document_body_content.return_value = _make_table_content(2, 2)
        rows = json.dumps([["a", "b"]])
        result = json.loads(_insert_table_rows(service, "doc1234567890", 0, 5, rows))
        assert result["code"] == "VALIDATION_ERROR"
        assert "after_row" in result["error"]

    def test_wrong_column_count(self):
        service = MagicMock()
        service.get_document_body_content.return_value = _make_table_content(2, 3)
        rows = json.dumps([["a", "b"]])
        result = json.loads(_insert_table_rows(service, "doc1234567890", 0, 0, rows))
        assert result["code"] == "VALIDATION_ERROR"
        assert "cells" in result["error"]
        assert "expected 3" in result["error"]

    def test_invalid_document_id(self):
        service = MagicMock()
        rows = json.dumps([["a"]])
        result = json.loads(_insert_table_rows(service, "short", 0, 0, rows))
        assert result["code"] == "VALIDATION_ERROR"

    def test_api_error(self):
        service = MagicMock()
        service.get_document_body_content.side_effect = Exception("API failure")
        rows = json.dumps([["a"]])
        result = json.loads(_insert_table_rows(service, "doc1234567890", 0, 0, rows))
        assert result["code"] == "API_ERROR"
