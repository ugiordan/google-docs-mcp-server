"""Tests for Google Docs service layer."""

from unittest.mock import MagicMock, patch

import pytest
from googleapiclient.errors import HttpError

from mcp_server.services.google_docs_service import GoogleDocsService


@pytest.fixture
def mock_credentials():
    """Mock credentials object."""
    return MagicMock()


@pytest.fixture
def mock_drive_service():
    """Mock Google Drive service."""
    return MagicMock()


@pytest.fixture
def mock_docs_service():
    """Mock Google Docs service."""
    return MagicMock()


@pytest.fixture
def service(mock_credentials, mock_drive_service, mock_docs_service):
    """Create GoogleDocsService with mocked dependencies."""
    with patch("mcp_server.services.google_docs_service.build") as mock_build:
        # Configure build to return our mocks
        def build_side_effect(service_name, version, credentials):
            if service_name == "drive":
                return mock_drive_service
            elif service_name == "docs":
                return mock_docs_service
            return MagicMock()

        mock_build.side_effect = build_side_effect

        service = GoogleDocsService(mock_credentials)
        service.drive_service = mock_drive_service
        service.docs_service = mock_docs_service
        return service


class TestListDocuments:
    """Tests for list_documents method."""

    def test_list_documents_without_query(self, service, mock_drive_service):
        """Test listing documents without search query."""
        # Mock the API response
        mock_response = {
            "files": [
                {
                    "id": "doc123",
                    "name": "Test Document",
                    "createdTime": "2024-01-01T00:00:00Z",
                    "modifiedTime": "2024-01-02T00:00:00Z",
                },
                {
                    "id": "doc456",
                    "name": "Another Doc",
                    "createdTime": "2024-01-03T00:00:00Z",
                    "modifiedTime": "2024-01-04T00:00:00Z",
                },
            ]
        }

        mock_drive_service.files().list().execute.return_value = mock_response

        # Call the method
        result = service.list_documents(max_results=10)

        # Verify the API call - check the last call with arguments
        list_calls = [c for c in mock_drive_service.files().list.call_args_list if c[1]]
        assert len(list_calls) >= 1
        call_kwargs = list_calls[-1][1]
        assert "mimeType='application/vnd.google-apps.document'" in call_kwargs["q"]
        assert call_kwargs["pageSize"] == 10
        assert call_kwargs["fields"] == "files(id,name,createdTime,modifiedTime)"

        # Verify the result
        assert len(result) == 2
        assert result[0]["id"] == "doc123"
        assert result[0]["name"] == "Test Document"
        assert result[0]["url"] == "https://docs.google.com/document/d/doc123/edit"
        assert result[1]["id"] == "doc456"

    def test_list_documents_with_query(self, service, mock_drive_service):
        """Test listing documents with search query."""
        mock_response = {"files": []}
        mock_drive_service.files().list().execute.return_value = mock_response

        service.list_documents(query="test's doc", max_results=5)

        # Verify sanitization and query construction
        call_kwargs = mock_drive_service.files().list.call_args[1]
        assert "name contains 'test\\'s doc'" in call_kwargs["q"]
        assert call_kwargs["pageSize"] == 5

    def test_list_documents_empty_result(self, service, mock_drive_service):
        """Test listing documents returns empty list when no files found."""
        mock_drive_service.files().list().execute.return_value = {"files": []}

        result = service.list_documents()

        assert result == []


class TestReadDocument:
    """Tests for read_document method."""

    def test_read_document_success(self, service, mock_docs_service):
        """Test reading a single-tab document."""
        mock_response = {
            "documentId": "doc123",
            "title": "Test Document",
            "tabs": [
                {
                    "tabProperties": {"tabId": "t.0", "title": ""},
                    "documentTab": {
                        "body": {
                            "content": [
                                {
                                    "paragraph": {
                                        "elements": [
                                            {"textRun": {"content": "Hello "}},
                                            {"textRun": {"content": "World"}},
                                        ]
                                    }
                                },
                                {
                                    "paragraph": {
                                        "elements": [
                                            {
                                                "textRun": {
                                                    "content": "\nSecond paragraph"
                                                }
                                            }
                                        ]
                                    }
                                },
                            ]
                        }
                    },
                    "childTabs": [],
                }
            ],
        }

        mock_docs_service.documents().get().execute.return_value = mock_response

        result = service.read_document("doc123")

        # Verify API call uses includeTabsContent
        get_calls = [
            c for c in mock_docs_service.documents().get.call_args_list if c[1]
        ]
        assert len(get_calls) >= 1
        assert get_calls[-1][1]["documentId"] == "doc123"
        assert get_calls[-1][1]["includeTabsContent"] is True

        # Verify result
        assert result["id"] == "doc123"
        assert result["title"] == "Test Document"
        assert result["content"] == "Hello World\nSecond paragraph"
        # Single tab: no tabs array in result
        assert "tabs" not in result

    def test_read_document_multi_tab(self, service, mock_docs_service):
        """Test reading a multi-tab document."""
        mock_response = {
            "documentId": "doc123",
            "title": "Multi-Tab Doc",
            "tabs": [
                {
                    "tabProperties": {"tabId": "t.0", "title": "Overview"},
                    "documentTab": {
                        "body": {
                            "content": [
                                {
                                    "paragraph": {
                                        "elements": [
                                            {"textRun": {"content": "First tab"}}
                                        ]
                                    }
                                }
                            ]
                        }
                    },
                    "childTabs": [],
                },
                {
                    "tabProperties": {"tabId": "t.1", "title": "Details"},
                    "documentTab": {
                        "body": {
                            "content": [
                                {
                                    "paragraph": {
                                        "elements": [
                                            {"textRun": {"content": "Second tab"}}
                                        ]
                                    }
                                }
                            ]
                        }
                    },
                    "childTabs": [],
                },
            ],
        }

        mock_docs_service.documents().get().execute.return_value = mock_response

        result = service.read_document("doc123")

        assert result["content"] == "First tab"
        assert len(result["tabs"]) == 2
        assert result["tabs"][0]["tab_id"] == "t.0"
        assert result["tabs"][0]["title"] == "Overview"
        assert result["tabs"][0]["content"] == "First tab"
        assert result["tabs"][1]["tab_id"] == "t.1"
        assert result["tabs"][1]["title"] == "Details"
        assert result["tabs"][1]["content"] == "Second tab"

    def test_read_document_nested_tabs(self, service, mock_docs_service):
        """Test reading a document with nested child tabs."""
        mock_response = {
            "documentId": "doc123",
            "title": "Nested Tabs",
            "tabs": [
                {
                    "tabProperties": {"tabId": "t.0", "title": "Parent"},
                    "documentTab": {
                        "body": {
                            "content": [
                                {
                                    "paragraph": {
                                        "elements": [
                                            {"textRun": {"content": "Parent content"}}
                                        ]
                                    }
                                }
                            ]
                        }
                    },
                    "childTabs": [
                        {
                            "tabProperties": {
                                "tabId": "t.1",
                                "title": "Child",
                                "parentTabId": "t.0",
                            },
                            "documentTab": {
                                "body": {
                                    "content": [
                                        {
                                            "paragraph": {
                                                "elements": [
                                                    {
                                                        "textRun": {
                                                            "content": "Child content"
                                                        }
                                                    }
                                                ]
                                            }
                                        }
                                    ]
                                }
                            },
                            "childTabs": [],
                        }
                    ],
                }
            ],
        }

        mock_docs_service.documents().get().execute.return_value = mock_response

        result = service.read_document("doc123")

        assert len(result["tabs"]) == 2
        assert result["tabs"][0]["tab_id"] == "t.0"
        assert result["tabs"][1]["tab_id"] == "t.1"
        assert result["tabs"][1]["parent_tab_id"] == "t.0"

    def test_read_document_empty_content(self, service, mock_docs_service):
        """Test reading document with no content."""
        mock_response = {
            "documentId": "doc123",
            "title": "Empty Doc",
            "tabs": [
                {
                    "tabProperties": {"tabId": "t.0", "title": ""},
                    "documentTab": {"body": {"content": []}},
                    "childTabs": [],
                }
            ],
        }

        mock_docs_service.documents().get().execute.return_value = mock_response

        result = service.read_document("doc123")

        assert result["content"] == ""

    def test_read_document_no_tabs_fallback(self, service, mock_docs_service):
        """Test reading document when tabs field is absent (legacy)."""
        mock_response = {
            "documentId": "doc123",
            "title": "Legacy Doc",
            "tabs": [],
            "body": {
                "content": [
                    {
                        "paragraph": {
                            "elements": [{"textRun": {"content": "Legacy content"}}]
                        }
                    }
                ]
            },
        }

        mock_docs_service.documents().get().execute.return_value = mock_response

        result = service.read_document("doc123")

        assert result["content"] == "Legacy content"


class TestCreateDocument:
    """Tests for create_document method."""

    def test_create_document_without_content(self, service, mock_drive_service):
        """Test creating a document without initial content."""
        mock_response = {"id": "newdoc123", "name": "New Document"}

        mock_drive_service.files().create().execute.return_value = mock_response

        result = service.create_document(title="New Document")

        # Verify API call - check the last call with arguments
        create_calls = [
            c for c in mock_drive_service.files().create.call_args_list if c[1]
        ]
        assert len(create_calls) >= 1
        call_kwargs = create_calls[-1][1]
        assert call_kwargs["body"]["name"] == "New Document"
        assert call_kwargs["body"]["mimeType"] == "application/vnd.google-apps.document"
        assert (
            "parents" not in call_kwargs["body"] or call_kwargs["body"]["parents"] == []
        )

        # Verify result
        assert result["id"] == "newdoc123"
        assert result["name"] == "New Document"
        assert result["url"] == "https://docs.google.com/document/d/newdoc123/edit"

    def test_create_document_with_content(
        self, service, mock_drive_service, mock_docs_service
    ):
        """Test creating a document with initial content."""
        mock_create_response = {"id": "newdoc123", "name": "New Document"}
        mock_drive_service.files().create().execute.return_value = mock_create_response

        service.create_document(title="New Document", content="Initial content")

        # Verify file creation - check calls with arguments
        create_calls = [
            c for c in mock_drive_service.files().create.call_args_list if c[1]
        ]
        assert len(create_calls) >= 1

        # Verify content insertion - check calls with arguments
        batch_calls = [
            c for c in mock_docs_service.documents().batchUpdate.call_args_list if c[1]
        ]
        assert len(batch_calls) >= 1
        call_kwargs = batch_calls[-1][1]
        assert call_kwargs["documentId"] == "newdoc123"
        requests = call_kwargs["body"]["requests"]
        assert len(requests) == 1
        assert requests[0]["insertText"]["location"]["index"] == 1
        assert requests[0]["insertText"]["text"] == "Initial content"

    def test_create_document_in_folder(self, service, mock_drive_service):
        """Test creating a document in a specific folder."""
        mock_response = {"id": "newdoc123", "name": "New Document"}
        mock_drive_service.files().create().execute.return_value = mock_response

        service.create_document(title="New Document", folder_id="folder123")

        # Verify folder assignment
        call_kwargs = mock_drive_service.files().create.call_args[1]
        assert call_kwargs["body"]["parents"] == ["folder123"]


class TestClearDocument:
    """Tests for clear_document method."""

    def test_clear_document_with_content(self, service, mock_docs_service):
        """Test clearing a document that has content."""
        mock_docs_service.documents().get().execute.return_value = {
            "documentId": "doc123",
            "body": {"content": [{"endIndex": 50}]},
        }

        result = service.clear_document("doc123")

        call_kwargs = mock_docs_service.documents().batchUpdate.call_args[1]
        assert call_kwargs["documentId"] == "doc123"
        requests = call_kwargs["body"]["requests"]
        assert len(requests) == 1
        assert requests[0]["deleteContentRange"]["range"]["startIndex"] == 1
        assert requests[0]["deleteContentRange"]["range"]["endIndex"] == 49

        assert result == 50

    def test_clear_document_empty(self, service, mock_docs_service):
        """Test clearing a document with no content (endIndex == 1)."""
        mock_docs_service.documents().get().execute.return_value = {
            "documentId": "doc123",
            "body": {"content": [{"endIndex": 1}]},
        }

        result = service.clear_document("doc123")
        assert result == 1


class TestUploadFile:
    """Tests for upload_file method."""

    def test_upload_file_docx(self, service, mock_drive_service):
        """Test uploading a .docx file."""
        mock_drive_service.files().create().execute.return_value = {
            "id": "uploaded123",
            "name": "Uploaded Doc",
        }

        file_bytes = b"fake docx content"
        mime_type = (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )

        result = service.upload_file(file_bytes, "Uploaded Doc", mime_type)

        assert result["id"] == "uploaded123"
        assert result["name"] == "Uploaded Doc"
        assert result["url"] == "https://docs.google.com/document/d/uploaded123/edit"

    def test_upload_file_with_folder(self, service, mock_drive_service):
        """Test uploading a file to a specific folder."""
        mock_drive_service.files().create().execute.return_value = {
            "id": "uploaded123",
            "name": "Uploaded Doc",
        }

        file_bytes = b"fake content"
        result = service.upload_file(
            file_bytes, "Uploaded Doc", "application/pdf", folder_id="folder123"
        )

        create_calls = [
            c for c in mock_drive_service.files().create.call_args_list if c[1]
        ]
        assert len(create_calls) >= 1
        call_kwargs = create_calls[-1][1]
        assert call_kwargs["body"]["parents"] == ["folder123"]

        assert result["id"] == "uploaded123"


class TestCopyFileAsDoc:
    """Tests for copy_file_as_doc method."""

    def test_copy_file_as_doc(self, service, mock_drive_service):
        """Test copying a Drive file as a Google Doc."""
        mock_drive_service.files().copy().execute.return_value = {
            "id": "copied123",
            "name": "Copied Doc",
        }

        result = service.copy_file_as_doc("source123", "Copied Doc")

        assert result["id"] == "copied123"
        assert result["name"] == "Copied Doc"
        assert result["url"] == "https://docs.google.com/document/d/copied123/edit"

    def test_copy_file_as_doc_with_folder(self, service, mock_drive_service):
        """Test copying a file into a specific folder."""
        mock_drive_service.files().copy().execute.return_value = {
            "id": "copied123",
            "name": "Copied Doc",
        }

        result = service.copy_file_as_doc(
            "source123", "Copied Doc", folder_id="folder456"
        )

        copy_calls = [c for c in mock_drive_service.files().copy.call_args_list if c[1]]
        assert len(copy_calls) >= 1
        call_kwargs = copy_calls[-1][1]
        assert call_kwargs["body"]["parents"] == ["folder456"]
        assert result["id"] == "copied123"


class TestUpdateDocument:
    """Tests for update_document method."""

    def test_update_document_append_mode(
        self, service, mock_docs_service, mock_drive_service
    ):
        """Test updating document in append mode."""
        # Mock getting document to find endIndex
        mock_get_response = {
            "documentId": "doc123",
            "title": "Test Document",
            "body": {"content": [{"endIndex": 100}]},
        }
        mock_docs_service.documents().get().execute.return_value = mock_get_response

        # Mock drive service for getting file info
        mock_drive_service.files().get().execute.return_value = {
            "id": "doc123",
            "name": "Test Document",
            "modifiedTime": "2024-01-05T00:00:00Z",
        }

        service.update_document("doc123", "Appended text", mode="append")

        # Verify get call to find endIndex
        mock_docs_service.documents().get.assert_called_with(documentId="doc123")

        # Verify batch update
        call_kwargs = mock_docs_service.documents().batchUpdate.call_args[1]
        assert call_kwargs["documentId"] == "doc123"
        requests = call_kwargs["body"]["requests"]
        assert len(requests) == 1
        assert requests[0]["insertText"]["location"]["index"] == 99  # endIndex - 1
        assert requests[0]["insertText"]["text"] == "Appended text"

    def test_update_document_replace_mode(
        self, service, mock_docs_service, mock_drive_service
    ):
        """Test updating document in replace mode."""
        mock_get_response = {
            "documentId": "doc123",
            "title": "Test Document",
            "body": {"content": [{"endIndex": 100}]},
        }
        mock_docs_service.documents().get().execute.return_value = mock_get_response

        mock_drive_service.files().get().execute.return_value = {
            "id": "doc123",
            "name": "Test Document",
            "modifiedTime": "2024-01-05T00:00:00Z",
        }

        service.update_document("doc123", "New content", mode="replace")

        # Verify atomic batch update with delete + insert in single call
        call_kwargs = mock_docs_service.documents().batchUpdate.call_args[1]
        requests = call_kwargs["body"]["requests"]
        assert len(requests) == 2
        # First request: delete existing content
        assert "deleteContentRange" in requests[0]
        assert requests[0]["deleteContentRange"]["range"]["startIndex"] == 1
        assert requests[0]["deleteContentRange"]["range"]["endIndex"] == 99
        # Second request: insert new content at index 1
        assert requests[1]["insertText"]["location"]["index"] == 1
        assert requests[1]["insertText"]["text"] == "New content"


class TestCommentOnDocument:
    """Tests for comment_on_document method."""

    def test_comment_without_quoted_text(self, service, mock_drive_service):
        """Test adding a comment without quoted text."""
        mock_response = {"id": "comment123", "content": "Great work!"}

        mock_drive_service.comments().create().execute.return_value = mock_response

        result = service.comment_on_document("doc123", "Great work!")

        # Verify API call - check calls with arguments
        create_calls = [
            c for c in mock_drive_service.comments().create.call_args_list if c[1]
        ]
        assert len(create_calls) >= 1
        call_kwargs = create_calls[-1][1]
        assert call_kwargs["fileId"] == "doc123"
        assert call_kwargs["body"]["content"] == "Great work!"
        assert (
            "quotedFileContent" not in call_kwargs["body"]
            or call_kwargs["body"]["quotedFileContent"] is None
        )

        # Verify result
        assert result["comment_id"] == "comment123"
        assert result["document_id"] == "doc123"
        assert result["content"] == "Great work!"

    def test_comment_with_quoted_text(self, service, mock_drive_service):
        """Test adding a comment with quoted text."""
        mock_response = {"id": "comment123", "content": "Fix this typo"}

        mock_drive_service.comments().create().execute.return_value = mock_response

        service.comment_on_document("doc123", "Fix this typo", quoted_text="teh")

        # Verify API call includes quoted text
        call_kwargs = mock_drive_service.comments().create.call_args[1]
        assert call_kwargs["body"]["quotedFileContent"]["value"] == "teh"


class TestListComments:
    """Tests for list_comments method."""

    def test_list_comments_success(self, service, mock_drive_service):
        mock_drive_service.comments().list().execute.return_value = {
            "comments": [
                {
                    "id": "c1",
                    "author": {"displayName": "Alice"},
                    "content": "Fix this",
                    "quotedFileContent": {"value": "broken code"},
                    "resolved": False,
                    "replies": [
                        {
                            "author": {"displayName": "Bob"},
                            "content": "Done",
                        }
                    ],
                }
            ],
        }

        result = service.list_comments("doc123")

        assert len(result) == 1
        assert result[0]["id"] == "c1"
        assert result[0]["author"] == "Alice"
        assert result[0]["content"] == "Fix this"
        assert result[0]["quoted_text"] == "broken code"
        assert result[0]["resolved"] is False
        assert len(result[0]["replies"]) == 1
        assert result[0]["replies"][0]["author"] == "Bob"
        assert result[0]["replies"][0]["content"] == "Done"

    def test_list_comments_empty(self, service, mock_drive_service):
        mock_drive_service.comments().list().execute.return_value = {
            "comments": [],
        }

        result = service.list_comments("doc123")
        assert result == []

    def test_list_comments_no_quoted_text(self, service, mock_drive_service):
        mock_drive_service.comments().list().execute.return_value = {
            "comments": [
                {
                    "id": "c1",
                    "author": {"displayName": "Alice"},
                    "content": "General comment",
                    "resolved": True,
                }
            ],
        }

        result = service.list_comments("doc123")
        assert "quoted_text" not in result[0]
        assert result[0]["resolved"] is True

    def test_list_comments_no_replies(self, service, mock_drive_service):
        mock_drive_service.comments().list().execute.return_value = {
            "comments": [
                {
                    "id": "c1",
                    "author": {"displayName": "Alice"},
                    "content": "Note",
                    "replies": [],
                }
            ],
        }

        result = service.list_comments("doc123")
        assert "replies" not in result[0]


class TestFindFolder:
    """Tests for find_folder method."""

    def test_find_folder_success(self, service, mock_drive_service):
        """Test finding a folder successfully."""
        mock_response = {"files": [{"id": "folder123", "name": "My Folder"}]}

        mock_drive_service.files().list().execute.return_value = mock_response

        result = service.find_folder("My Folder")

        # Verify API call
        call_kwargs = mock_drive_service.files().list.call_args[1]
        assert "name='My Folder'" in call_kwargs["q"]
        assert "mimeType='application/vnd.google-apps.folder'" in call_kwargs["q"]
        assert "trashed=false" in call_kwargs["q"]

        # Verify result
        assert result["found"] is True
        assert result["folder_id"] == "folder123"
        assert result["name"] == "My Folder"

    def test_find_folder_not_found(self, service, mock_drive_service):
        """Test finding a folder that doesn't exist."""
        mock_response = {"files": []}

        mock_drive_service.files().list().execute.return_value = mock_response

        result = service.find_folder("Nonexistent Folder")

        assert result["found"] is False
        assert "folder_id" not in result

    def test_find_folder_sanitizes_name(self, service, mock_drive_service):
        """Test that folder name is sanitized."""
        mock_response = {"files": []}
        mock_drive_service.files().list().execute.return_value = mock_response

        service.find_folder("Folder's Name")

        # Verify sanitization
        call_kwargs = mock_drive_service.files().list.call_args[1]
        assert "name='Folder\\'s Name'" in call_kwargs["q"]


class TestMoveDocument:
    """Tests for move_document method."""

    def test_move_document_success(self, service, mock_drive_service):
        """Test moving a document to a new folder."""
        # Mock get to return current parents
        mock_get_response = {"parents": ["oldparent123"]}
        mock_drive_service.files().get().execute.return_value = mock_get_response

        # Mock update response
        mock_update_response = {
            "id": "doc123",
            "name": "Test Document",
            "parents": ["newfolder123"],
        }
        mock_drive_service.files().update().execute.return_value = mock_update_response

        result = service.move_document("doc123", "newfolder123")

        # Verify get call - check calls with arguments
        get_calls = [c for c in mock_drive_service.files().get.call_args_list if c[1]]
        assert len(get_calls) >= 1
        assert get_calls[-1][1]["fileId"] == "doc123"
        assert get_calls[-1][1]["fields"] == "parents"

        # Verify update call - check calls with arguments
        update_calls = [
            c for c in mock_drive_service.files().update.call_args_list if c[1]
        ]
        assert len(update_calls) >= 1
        call_kwargs = update_calls[-1][1]
        assert call_kwargs["fileId"] == "doc123"
        assert call_kwargs["addParents"] == "newfolder123"
        assert call_kwargs["removeParents"] == "oldparent123"

        # Verify result
        assert result["id"] == "doc123"
        assert result["name"] == "Test Document"
        assert result["new_parent_id"] == "newfolder123"


class TestTrashDocument:
    """Tests for trash_document method."""

    def test_trash_document_success(self, service, mock_drive_service):
        """Test trashing a document."""
        mock_response = {"id": "doc123", "name": "Test Document", "trashed": True}

        mock_drive_service.files().update().execute.return_value = mock_response

        result = service.trash_document("doc123")

        # Verify API call
        call_kwargs = mock_drive_service.files().update.call_args[1]
        assert call_kwargs["fileId"] == "doc123"
        assert call_kwargs["body"]["trashed"] is True

        # Verify result
        assert result["id"] == "doc123"
        assert result["name"] == "Test Document"
        assert result["trashed"] is True


class TestAddTab:
    """Tests for add_tab method."""

    def test_add_tab_success(self, service, mock_docs_service):
        mock_docs_service.documents().batchUpdate().execute.return_value = {
            "replies": [
                {
                    "addDocumentTab": {
                        "tabProperties": {"tabId": "t.newid", "title": "New Tab"}
                    }
                }
            ]
        }

        result = service.add_tab("doc123", "New Tab")

        call_kwargs = mock_docs_service.documents().batchUpdate.call_args[1]
        assert call_kwargs["documentId"] == "doc123"
        requests = call_kwargs["body"]["requests"]
        assert requests[0]["addDocumentTab"]["tabProperties"]["title"] == "New Tab"

        assert result["tab_id"] == "t.newid"
        assert result["title"] == "New Tab"
        assert result["document_id"] == "doc123"


class TestDeleteTab:
    """Tests for delete_tab method."""

    def test_delete_tab_success(self, service, mock_docs_service):
        mock_docs_service.documents().batchUpdate().execute.return_value = {}

        result = service.delete_tab("doc123", "t.abc")

        call_kwargs = mock_docs_service.documents().batchUpdate.call_args[1]
        requests = call_kwargs["body"]["requests"]
        assert requests[0]["deleteTab"]["tabId"] == "t.abc"

        assert result["document_id"] == "doc123"
        assert result["deleted_tab_id"] == "t.abc"


class TestRenameTab:
    """Tests for rename_tab method."""

    def test_rename_tab_success(self, service, mock_docs_service):
        mock_docs_service.documents().batchUpdate().execute.return_value = {}

        result = service.rename_tab("doc123", "t.abc", "Renamed")

        call_kwargs = mock_docs_service.documents().batchUpdate.call_args[1]
        requests = call_kwargs["body"]["requests"]
        req = requests[0]["updateDocumentTabProperties"]
        assert req["tabProperties"]["tabId"] == "t.abc"
        assert req["tabProperties"]["title"] == "Renamed"
        assert req["fields"] == "title"

        assert result["tab_id"] == "t.abc"
        assert result["title"] == "Renamed"


class TestUpdateDocumentWithTab:
    """Tests for update_document with tab_id."""

    def test_update_document_append_with_tab(
        self, service, mock_docs_service, mock_drive_service
    ):
        mock_docs_service.documents().get().execute.return_value = {
            "documentId": "doc123",
            "tabs": [
                {
                    "tabProperties": {"tabId": "t.1"},
                    "documentTab": {"body": {"content": [{"endIndex": 50}]}},
                    "childTabs": [],
                }
            ],
        }
        mock_drive_service.files().get().execute.return_value = {
            "id": "doc123",
            "name": "Test",
            "modifiedTime": "2024-01-05T00:00:00Z",
        }

        service.update_document("doc123", "New text", mode="append", tab_id="t.1")

        call_kwargs = mock_docs_service.documents().batchUpdate.call_args[1]
        requests = call_kwargs["body"]["requests"]
        location = requests[0]["insertText"]["location"]
        assert location["index"] == 49
        assert location["tabId"] == "t.1"

    def test_clear_document_with_tab(self, service, mock_docs_service):
        mock_docs_service.documents().get().execute.return_value = {
            "documentId": "doc123",
            "tabs": [
                {
                    "tabProperties": {"tabId": "t.2"},
                    "documentTab": {"body": {"content": [{"endIndex": 30}]}},
                    "childTabs": [],
                }
            ],
        }

        result = service.clear_document("doc123", tab_id="t.2")

        call_kwargs = mock_docs_service.documents().batchUpdate.call_args[1]
        requests = call_kwargs["body"]["requests"]
        range_dict = requests[0]["deleteContentRange"]["range"]
        assert range_dict["startIndex"] == 1
        assert range_dict["endIndex"] == 29
        assert range_dict["tabId"] == "t.2"
        assert result == 30


class TestGetTemplateStyles:
    """Tests for get_template_styles method."""

    def test_get_template_styles_success(self, service, mock_docs_service):
        """Test getting template styles from a document."""
        mock_response = {
            "documentId": "doc123",
            "title": "Template Document",
            "namedStyles": {
                "styles": [
                    {
                        "namedStyleType": "NORMAL_TEXT",
                        "textStyle": {
                            "fontSize": {"magnitude": 11, "unit": "PT"},
                            "fontFamily": "Arial",
                        },
                    },
                    {
                        "namedStyleType": "HEADING_1",
                        "textStyle": {
                            "fontSize": {"magnitude": 20, "unit": "PT"},
                            "fontFamily": "Arial",
                            "bold": True,
                        },
                    },
                ]
            },
        }

        mock_docs_service.documents().get().execute.return_value = mock_response

        result = service.get_template_styles("doc123")

        # Verify API call - check calls with arguments
        get_calls = [
            c for c in mock_docs_service.documents().get.call_args_list if c[1]
        ]
        assert len(get_calls) >= 1
        assert get_calls[-1][1]["documentId"] == "doc123"

        # Verify result is the raw API response
        assert result == mock_response
        assert "namedStyles" in result
        assert "documentId" in result


class TestRetryLogic:
    """Tests for retry on 429 errors."""

    def test_retries_on_429(self, service, mock_drive_service):
        """Test that the service retries on 429 errors."""
        # Mock 429 error followed by success
        error_response = MagicMock()
        error_response.status = 429
        error_response.reason = "Rate Limit Exceeded"

        http_error = HttpError(error_response, b"Rate limit exceeded")

        mock_list = mock_drive_service.files().list()
        mock_list.execute.side_effect = [
            http_error,
            {"files": [{"id": "doc123", "name": "Test"}]},
        ]

        with patch("time.sleep") as mock_sleep:
            service.list_documents()

            # Verify retry happened
            assert mock_list.execute.call_count == 2
            # Verify sleep was called for backoff
            mock_sleep.assert_called_once_with(1)

    def test_gives_up_after_max_retries(self, service, mock_drive_service):
        """Test that the service gives up after max retries."""
        # Mock 4 consecutive 429 errors
        error_response = MagicMock()
        error_response.status = 429
        error_response.reason = "Rate Limit Exceeded"

        http_error = HttpError(error_response, b"Rate limit exceeded")

        mock_list = mock_drive_service.files().list()
        mock_list.execute.side_effect = [http_error] * 4

        with patch("time.sleep"):
            # Should raise after 3 retries (4 total attempts)
            with pytest.raises(HttpError):
                service.list_documents()

            # Verify 4 attempts were made (initial + 3 retries)
            assert mock_list.execute.call_count == 4


class TestBatchUpdate:
    """Tests for batch_update method."""

    def test_batch_update_success(self, service, mock_docs_service):
        """Test batch updating a document."""
        mock_response = {"documentId": "doc123"}
        mock_docs_service.documents().batchUpdate().execute.return_value = mock_response

        requests = [
            {"insertText": {"location": {"index": 1}, "text": "Hello"}},
            {
                "updateTextStyle": {
                    "range": {"startIndex": 1, "endIndex": 6},
                    "textStyle": {"bold": True},
                    "fields": "bold",
                }
            },
        ]

        result = service.batch_update("doc123", requests)

        # Verify API call
        call_kwargs = mock_docs_service.documents().batchUpdate.call_args[1]
        assert call_kwargs["documentId"] == "doc123"
        assert call_kwargs["body"]["requests"] == requests

        # Verify result
        assert result["documentId"] == "doc123"


class TestErrorHandling:
    """Tests for error handling."""

    def test_handles_403_access_denied(self, service, mock_docs_service):
        """Test handling of 403 access denied errors."""
        error_response = MagicMock()
        error_response.status = 403
        error_response.reason = "Forbidden"

        http_error = HttpError(error_response, b"Access denied")
        mock_docs_service.documents().get().execute.side_effect = http_error

        with pytest.raises(Exception) as exc_info:
            service.read_document("doc123")

        assert "Access denied" in str(exc_info.value)

    def test_handles_404_not_found(self, service, mock_docs_service):
        """Test handling of 404 not found errors."""
        error_response = MagicMock()
        error_response.status = 404
        error_response.reason = "Not Found"

        http_error = HttpError(error_response, b"Document not found")
        mock_docs_service.documents().get().execute.side_effect = http_error

        with pytest.raises(Exception) as exc_info:
            service.read_document("doc123")

        assert "Document not found" in str(exc_info.value)

    def test_does_not_expose_credentials(self, service, mock_docs_service):
        """Test that error messages don't expose credentials."""
        error_response = MagicMock()
        error_response.status = 500
        error_response.reason = "Internal Server Error"

        http_error = HttpError(error_response, b"Internal error")
        mock_docs_service.documents().get().execute.side_effect = http_error

        with pytest.raises(Exception) as exc_info:
            service.read_document("doc123")

        # Verify no sensitive data in error message
        error_msg = str(exc_info.value)
        assert "credentials" not in error_msg.lower()
        assert "secret" not in error_msg.lower()
        assert "token" not in error_msg.lower()
