"""Tests for Google Docs MCP tools."""

import json
from unittest.mock import MagicMock, patch

from mcp_server.config import Template, TemplateConfig
from mcp_server.nonce import NonceManager
from mcp_server.tools.google_docs_tools import (
    _comment_on_document,
    _convert_markdown_to_doc,
    _create_document,
    _delete_document,
    _error_response,
    _find_folder,
    _list_documents,
    _move_document,
    _read_document,
    _update_document,
    _update_document_markdown,
    _upload_document,
)


class TestErrorResponse:
    def test_error_response_format(self):
        result = _error_response("Something went wrong", "API_ERROR")
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

        result = _read_document(service, document_id="doc1234567890")
        data = json.loads(result)

        assert data["id"] == "doc123"
        assert data["title"] == "Test Doc"
        assert "<document-content>" in data["content"]
        assert "Hello, world!" in data["content"]
        assert "</document-content>" in data["content"]
        assert "untrusted external data" in data["content"]

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
        assert data["name"] == "New Document"
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
            "doc1234567890", "New content", mode="append"
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
            "doc1234567890", "New content", mode="replace"
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

    def test_update_document_validation_error(self):
        service = MagicMock()

        result = _update_document(
            service, document_id="invalid", content="test", mode="append"
        )
        data = json.loads(result)

        assert "error" in data
        assert data["code"] == "VALIDATION_ERROR"


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
        service.create_document.return_value = {
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

        with patch("mcp_server.tools.google_docs_tools.parse_markdown") as mock_parse:
            with patch(
                "mcp_server.tools.google_docs_tools.extract_template_styles"
            ) as mock_extract:
                with patch(
                    "mcp_server.tools.google_docs_tools.build_batch_update_requests"
                ) as mock_build:
                    mock_parse.return_value = [
                        {"type": "heading", "level": 1, "text": "Hello"}
                    ]
                    mock_extract.return_value = {"HEADING_1": {"font_size": 20}}
                    mock_build.return_value = [
                        {"insertText": {"location": {"index": 1}, "text": "Hello\n"}}
                    ]

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
                    service.batch_update.assert_called_once()

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
        service.create_document.return_value = {
            "id": "newdoc123",
            "name": "Test",
            "url": "https://docs.google.com/document/d/newdoc123/edit",
        }

        template_config = TemplateConfig(templates=[])

        with patch("mcp_server.tools.google_docs_tools.parse_markdown") as mock_parse:
            with patch(
                "mcp_server.tools.google_docs_tools.build_batch_update_requests"
            ) as mock_build:
                mock_parse.return_value = [{"type": "paragraph", "text": "Hello"}]
                mock_build.return_value = []

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
        assert data["name"] == "My Document"
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


class TestUpdateDocumentMarkdown:
    def test_update_markdown_without_template(self):
        service = MagicMock()
        service.clear_document.return_value = 50
        service.batch_update.return_value = {"documentId": "doc123"}

        template_config = TemplateConfig(templates=[])

        with patch("mcp_server.tools.google_docs_tools.parse_markdown") as mock_parse:
            with patch(
                "mcp_server.tools.google_docs_tools.build_batch_update_requests"
            ) as mock_build:
                mock_parse.return_value = [{"type": "paragraph", "text": "Hello"}]
                mock_build.return_value = [
                    {"insertText": {"location": {"index": 1}, "text": "Hello\n"}}
                ]

                result = _update_document_markdown(
                    service,
                    template_config,
                    document_id="doc1234567890",
                    markdown_content="Hello",
                    template_name="",
                )
                data = json.loads(result)

                assert data["id"] == "doc1234567890"
                assert data["template_used"] is None
                service.clear_document.assert_called_once_with("doc1234567890")
                service.batch_update.assert_called_once()

    def test_update_markdown_with_template(self):
        service = MagicMock()
        service.clear_document.return_value = 50
        service.batch_update.return_value = {"documentId": "doc123"}
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

        with patch("mcp_server.tools.google_docs_tools.parse_markdown") as mock_parse:
            with patch(
                "mcp_server.tools.google_docs_tools.extract_template_styles"
            ) as mock_extract:
                with patch(
                    "mcp_server.tools.google_docs_tools.build_batch_update_requests"
                ) as mock_build:
                    mock_parse.return_value = [
                        {"type": "heading", "level": 1, "text": "Title"}
                    ]
                    mock_extract.return_value = {"HEADING_1": {"font_size": 20}}
                    mock_build.return_value = [
                        {"insertText": {"location": {"index": 1}, "text": "Title\n"}}
                    ]

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
                    service.clear_document.assert_called_once_with("doc1234567890")
                    mock_extract.assert_called_once()

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
        service.clear_document.side_effect = Exception("API error")
        template_config = TemplateConfig(templates=[])

        with patch("mcp_server.tools.google_docs_tools.parse_markdown") as mock_parse:
            mock_parse.return_value = [{"type": "paragraph", "text": "Hello"}]

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
