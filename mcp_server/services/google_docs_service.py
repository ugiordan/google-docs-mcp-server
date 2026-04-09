"""Google Docs service layer for API interactions."""

import time

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaInMemoryUpload

from mcp_server.validation import sanitize_query


class GoogleDocsService:
    """Service layer for Google Docs and Drive API operations."""

    def __init__(self, credentials):
        """Initialize the service with Google credentials.

        Args:
            credentials: Google OAuth2 credentials object
        """
        self.drive_service = build("drive", "v3", credentials=credentials)
        self.docs_service = build("docs", "v1", credentials=credentials)

    @staticmethod
    def _extract_body_content(body):
        """Extract text content from a document body.

        Args:
            body: Document body dict from the API response

        Returns:
            Concatenated text content string
        """
        content_parts = []
        for item in body.get("content", []):
            if "paragraph" in item:
                for element in item["paragraph"].get("elements", []):
                    if "textRun" in element:
                        content_parts.append(element["textRun"].get("content", ""))
        return "".join(content_parts)

    @staticmethod
    def _flatten_tabs(tabs):
        """Flatten nested tab structure into a list.

        Args:
            tabs: List of tab objects from the API response

        Returns:
            Flat list of tab dicts with tab_id, title, and content
        """
        result = []
        for tab in tabs:
            tab_props = tab.get("tabProperties", {})
            doc_tab = tab.get("documentTab", {})
            body = doc_tab.get("body", {})
            content = GoogleDocsService._extract_body_content(body)
            tab_info = {
                "tab_id": tab_props.get("tabId", ""),
                "title": tab_props.get("title", ""),
                "content": content,
            }
            parent_id = tab_props.get("parentTabId")
            if parent_id:
                tab_info["parent_tab_id"] = parent_id
            result.append(tab_info)
            result.extend(GoogleDocsService._flatten_tabs(tab.get("childTabs", [])))
        return result

    @staticmethod
    def _find_tab_recursive(tab, tab_id):
        """Find a tab by ID, searching recursively through child tabs."""
        if tab.get("tabProperties", {}).get("tabId") == tab_id:
            return tab
        for child in tab.get("childTabs", []):
            found = GoogleDocsService._find_tab_recursive(child, tab_id)
            if found:
                return found
        return None

    @staticmethod
    def _get_tab_end_index(doc_response, tab_id):
        """Find the end index of a specific tab's content."""
        for tab in doc_response.get("tabs", []):
            found = GoogleDocsService._find_tab_recursive(tab, tab_id)
            if found:
                body = found.get("documentTab", {}).get("body", {})
                end_index = 1
                for item in body.get("content", []):
                    if "endIndex" in item:
                        end_index = item["endIndex"]
                return end_index
        raise ValueError(f"Tab '{tab_id}' not found in document")

    def _retry_on_429(self, fn, max_retries=3):
        """Execute function with retry logic for 429 rate limit errors.

        Args:
            fn: Function to execute
            max_retries: Maximum number of retries (default: 3)

        Returns:
            Result of the function call

        Raises:
            HttpError: If max retries exceeded or non-429 error occurs
        """
        retries = 0
        backoff = 1  # Start with 1 second

        while True:
            try:
                return fn()
            except HttpError as e:
                if e.resp.status == 429 and retries < max_retries:
                    time.sleep(backoff)
                    retries += 1
                    backoff *= 2  # Exponential backoff
                else:
                    raise

    def list_documents(self, query=None, max_results=10):
        """List Google Docs documents.

        Args:
            query: Optional search query string
            max_results: Maximum number of results to return (default: 10)

        Returns:
            List of document dictionaries with id, name, url, createdTime, modifiedTime
        """

        def _list():
            # Build the query
            q_parts = ["mimeType='application/vnd.google-apps.document'"]
            if query:
                sanitized = sanitize_query(query)
                q_parts.append(f"name contains '{sanitized}'")

            q = " and ".join(q_parts)

            response = (
                self.drive_service.files()
                .list(
                    q=q,
                    pageSize=max_results,
                    fields="files(id,name,createdTime,modifiedTime)",
                )
                .execute()
            )

            files = response.get("files", [])
            return [
                {
                    "id": f["id"],
                    "name": f["name"],
                    "url": f"https://docs.google.com/document/d/{f['id']}/edit",
                    "createdTime": f.get("createdTime"),
                    "modifiedTime": f.get("modifiedTime"),
                }
                for f in files
            ]

        return self._retry_on_429(_list)

    def read_document(self, doc_id):
        """Read the content of a Google Doc, including all tabs.

        Args:
            doc_id: The document ID

        Returns:
            Dictionary with id, title, content (first tab), and tabs
            (list of tab dicts when multiple tabs exist)

        Raises:
            Exception: On access denied or not found errors
        """

        def _read():
            response = (
                self.docs_service.documents()
                .get(documentId=doc_id, includeTabsContent=True)
                .execute()
            )

            tabs = self._flatten_tabs(response.get("tabs", []))

            if tabs:
                content = tabs[0]["content"]
            else:
                # Fallback for docs without tabs info
                content = self._extract_body_content(response.get("body", {}))

            result = {
                "id": response["documentId"],
                "title": response.get("title", ""),
                "content": content,
            }

            if len(tabs) > 1:
                result["tabs"] = tabs

            return result

        return self._retry_on_429(_read)

    def create_document(self, title, content=None, folder_id=None):
        """Create a new Google Doc.

        Args:
            title: Title of the new document
            content: Optional initial content
            folder_id: Optional folder ID to create document in

        Returns:
            Dictionary with id, name, and url
        """

        def _create():
            # Create the file
            body = {"name": title, "mimeType": "application/vnd.google-apps.document"}

            if folder_id:
                body["parents"] = [folder_id]

            file_metadata = (
                self.drive_service.files().create(body=body, fields="id,name").execute()
            )

            doc_id = file_metadata["id"]

            # Insert content if provided
            if content:
                requests = [{"insertText": {"location": {"index": 1}, "text": content}}]

                self.docs_service.documents().batchUpdate(
                    documentId=doc_id, body={"requests": requests}
                ).execute()

            return {
                "id": doc_id,
                "name": file_metadata["name"],
                "url": f"https://docs.google.com/document/d/{doc_id}/edit",
            }

        return self._retry_on_429(_create)

    def update_document(self, doc_id, content, mode="append", tab_id=None):
        """Update a Google Doc with new content.

        Args:
            doc_id: The document ID
            content: Content to add or replace
            mode: Update mode - 'append' or 'replace' (default: 'append')
            tab_id: Optional tab ID to target a specific tab

        Returns:
            Dictionary with id, name, url, and updatedTime
        """
        if mode == "replace":
            self.clear_document(doc_id, tab_id=tab_id)

        def _update():
            if mode == "append":
                if tab_id:
                    doc = (
                        self.docs_service.documents()
                        .get(documentId=doc_id, includeTabsContent=True)
                        .execute()
                    )
                    end_index = self._get_tab_end_index(doc, tab_id)
                else:
                    doc = self.docs_service.documents().get(documentId=doc_id).execute()
                    end_index = 1
                    for item in doc.get("body", {}).get("content", []):
                        if "endIndex" in item:
                            end_index = item["endIndex"]

                location = {"index": end_index - 1}
                if tab_id:
                    location["tabId"] = tab_id
                requests = [{"insertText": {"location": location, "text": content}}]
            else:  # replace (already cleared)
                location = {"index": 1}
                if tab_id:
                    location["tabId"] = tab_id
                requests = [{"insertText": {"location": location, "text": content}}]

            self.docs_service.documents().batchUpdate(
                documentId=doc_id, body={"requests": requests}
            ).execute()

            # Get updated file metadata
            file_metadata = (
                self.drive_service.files()
                .get(fileId=doc_id, fields="id,name,modifiedTime")
                .execute()
            )

            return {
                "id": file_metadata["id"],
                "name": file_metadata["name"],
                "url": f"https://docs.google.com/document/d/{doc_id}/edit",
                "updatedTime": file_metadata.get("modifiedTime"),
            }

        return self._retry_on_429(_update)

    def clear_document(self, doc_id, tab_id=None):
        """Clear all content from a document or a specific tab.

        Args:
            doc_id: The document ID
            tab_id: Optional tab ID to clear a specific tab

        Returns:
            The original endIndex before clearing
        """

        def _clear():
            if tab_id:
                doc = (
                    self.docs_service.documents()
                    .get(documentId=doc_id, includeTabsContent=True)
                    .execute()
                )
                end_index = self._get_tab_end_index(doc, tab_id)
            else:
                doc = self.docs_service.documents().get(documentId=doc_id).execute()
                end_index = 1
                for item in doc.get("body", {}).get("content", []):
                    if "endIndex" in item:
                        end_index = item["endIndex"]

            if end_index > 1:
                range_dict = {"startIndex": 1, "endIndex": end_index - 1}
                if tab_id:
                    range_dict["tabId"] = tab_id
                requests = [{"deleteContentRange": {"range": range_dict}}]
                self.docs_service.documents().batchUpdate(
                    documentId=doc_id, body={"requests": requests}
                ).execute()

            return end_index

        return self._retry_on_429(_clear)

    def add_tab(self, doc_id, title):
        """Add a new tab to a document.

        Args:
            doc_id: The document ID
            title: Title for the new tab

        Returns:
            Dictionary with tab_id and title
        """

        def _add_tab():
            requests = [{"addDocumentTab": {"tabProperties": {"title": title}}}]
            response = (
                self.docs_service.documents()
                .batchUpdate(documentId=doc_id, body={"requests": requests})
                .execute()
            )

            # Extract the new tab ID from the reply
            replies = response.get("replies", [])
            tab_id = ""
            if replies:
                tab_id = (
                    replies[0]
                    .get("addDocumentTab", {})
                    .get("tabProperties", {})
                    .get("tabId", "")
                )

            return {"tab_id": tab_id, "title": title, "document_id": doc_id}

        return self._retry_on_429(_add_tab)

    def delete_tab(self, doc_id, tab_id):
        """Delete a tab from a document.

        Args:
            doc_id: The document ID
            tab_id: The tab ID to delete

        Returns:
            Dictionary with document_id and deleted tab_id
        """

        def _delete_tab():
            requests = [{"deleteTab": {"tabId": tab_id}}]
            self.docs_service.documents().batchUpdate(
                documentId=doc_id, body={"requests": requests}
            ).execute()
            return {"document_id": doc_id, "deleted_tab_id": tab_id}

        return self._retry_on_429(_delete_tab)

    def rename_tab(self, doc_id, tab_id, title):
        """Rename a tab in a document.

        Args:
            doc_id: The document ID
            tab_id: The tab ID to rename
            title: New title for the tab

        Returns:
            Dictionary with document_id, tab_id, and new title
        """

        def _rename_tab():
            requests = [
                {
                    "updateDocumentTabProperties": {
                        "tabProperties": {"tabId": tab_id, "title": title},
                        "fields": "title",
                    }
                }
            ]
            self.docs_service.documents().batchUpdate(
                documentId=doc_id, body={"requests": requests}
            ).execute()
            return {"document_id": doc_id, "tab_id": tab_id, "title": title}

        return self._retry_on_429(_rename_tab)

    def upload_file(self, file_bytes, title, mime_type, folder_id=None):
        """Upload a file and convert it to a Google Doc.

        Args:
            file_bytes: Raw file bytes
            title: Document title
            mime_type: Source file MIME type
            folder_id: Optional target folder ID

        Returns:
            Dictionary with id, name, and url
        """

        def _upload():
            body = {
                "name": title,
                "mimeType": "application/vnd.google-apps.document",
            }

            if folder_id:
                body["parents"] = [folder_id]

            media = MediaInMemoryUpload(file_bytes, mimetype=mime_type, resumable=False)

            file_metadata = (
                self.drive_service.files()
                .create(body=body, media_body=media, fields="id,name")
                .execute()
            )

            return {
                "id": file_metadata["id"],
                "name": file_metadata["name"],
                "url": f"https://docs.google.com/document/d/{file_metadata['id']}/edit",
            }

        return self._retry_on_429(_upload)

    def copy_file_as_doc(self, file_id, title, folder_id=None):
        """Copy a Drive file as a Google Doc, converting format.

        Args:
            file_id: Source file ID in Google Drive
            title: Title for the new document
            folder_id: Optional target folder ID

        Returns:
            Dictionary with id, name, and url
        """

        def _copy():
            body = {
                "name": title,
                "mimeType": "application/vnd.google-apps.document",
            }

            if folder_id:
                body["parents"] = [folder_id]

            file_metadata = (
                self.drive_service.files()
                .copy(fileId=file_id, body=body, fields="id,name")
                .execute()
            )

            return {
                "id": file_metadata["id"],
                "name": file_metadata["name"],
                "url": f"https://docs.google.com/document/d/{file_metadata['id']}/edit",
            }

        return self._retry_on_429(_copy)

    def update_file_content(self, doc_id, file_bytes, mime_type):
        """Replace a Google Doc's content by uploading new file bytes.

        Uses Drive API files().update() with media, which converts the uploaded
        content (e.g. .docx) into the native Google Docs format.

        Args:
            doc_id: The document ID to update
            file_bytes: Raw file bytes (e.g. .docx content)
            mime_type: Source file MIME type

        Returns:
            Dictionary with id, name, and url
        """

        def _update_content():
            media = MediaInMemoryUpload(file_bytes, mimetype=mime_type, resumable=False)

            file_metadata = (
                self.drive_service.files()
                .update(fileId=doc_id, media_body=media, fields="id,name")
                .execute()
            )

            return {
                "id": file_metadata["id"],
                "name": file_metadata["name"],
                "url": f"https://docs.google.com/document/d/{file_metadata['id']}/edit",
            }

        return self._retry_on_429(_update_content)

    def comment_on_document(self, doc_id, comment, quoted_text=None):
        """Add a comment to a Google Doc.

        Args:
            doc_id: The document ID
            comment: Comment text
            quoted_text: Optional text to quote/anchor the comment to

        Returns:
            Dictionary with comment_id, document_id, and content
        """

        def _comment():
            body = {"content": comment}

            if quoted_text:
                body["quotedFileContent"] = {"value": quoted_text}

            response = (
                self.drive_service.comments()
                .create(fileId=doc_id, body=body, fields="id,content")
                .execute()
            )

            return {
                "comment_id": response["id"],
                "document_id": doc_id,
                "content": response["content"],
            }

        return self._retry_on_429(_comment)

    def list_comments(self, doc_id):
        """List all comments on a document.

        Args:
            doc_id: The document ID

        Returns:
            List of comment dicts with id, author, content, quotedText,
            resolved status, and replies
        """

        max_comments = 100

        def _list_comments():
            comments = []
            page_token = None

            while True:
                response = (
                    self.drive_service.comments()
                    .list(
                        fileId=doc_id,
                        fields="comments(id,author/displayName,content,"
                        "quotedFileContent/value,resolved,"
                        "replies(author/displayName,content)),nextPageToken",
                        pageToken=page_token,
                    )
                    .execute()
                )

                for c in response.get("comments", []):
                    comment = {
                        "id": c["id"],
                        "author": c.get("author", {}).get("displayName", ""),
                        "content": c.get("content", ""),
                        "resolved": c.get("resolved", False),
                    }
                    quoted = c.get("quotedFileContent", {}).get("value")
                    if quoted:
                        comment["quoted_text"] = quoted
                    replies = c.get("replies", [])
                    if replies:
                        comment["replies"] = [
                            {
                                "author": r.get("author", {}).get("displayName", ""),
                                "content": r.get("content", ""),
                            }
                            for r in replies
                        ]
                    comments.append(comment)
                    if len(comments) >= max_comments:
                        return comments

                page_token = response.get("nextPageToken")
                if not page_token:
                    break

            return comments

        return self._retry_on_429(_list_comments)

    def find_folder(self, folder_name):
        """Find a folder by name.

        Args:
            folder_name: Name of the folder to find

        Returns:
            Dictionary with found status, and folder_id/name if found
        """

        def _find():
            sanitized = sanitize_query(folder_name)
            q = (
                f"name='{sanitized}' and "
                "mimeType='application/vnd.google-apps.folder' and "
                "trashed=false"
            )

            response = (
                self.drive_service.files()
                .list(q=q, pageSize=1, fields="files(id,name)")
                .execute()
            )

            files = response.get("files", [])

            if files:
                return {
                    "found": True,
                    "folder_id": files[0]["id"],
                    "name": files[0]["name"],
                }
            else:
                return {"found": False}

        return self._retry_on_429(_find)

    def move_document(self, doc_id, folder_id):
        """Move a document to a different folder.

        Args:
            doc_id: The document ID
            folder_id: The target folder ID

        Returns:
            Dictionary with id, name, and new_parent_id

        Raises:
            Exception: If target folder is not accessible
        """

        def _move():
            # Verify target folder is accessible
            self.drive_service.files().get(fileId=folder_id, fields="id,name").execute()

            # Get current parents
            file_metadata = (
                self.drive_service.files()
                .get(fileId=doc_id, fields="parents")
                .execute()
            )

            previous_parents = ",".join(file_metadata.get("parents", []))

            # Move the file
            updated_file = (
                self.drive_service.files()
                .update(
                    fileId=doc_id,
                    addParents=folder_id,
                    removeParents=previous_parents,
                    fields="id,name,parents",
                )
                .execute()
            )

            return {
                "id": updated_file["id"],
                "name": updated_file["name"],
                "new_parent_id": (
                    updated_file["parents"][0] if updated_file.get("parents") else None
                ),
            }

        return self._retry_on_429(_move)

    def trash_document(self, doc_id):
        """Move a document to trash.

        Args:
            doc_id: The document ID

        Returns:
            Dictionary with id, name, and trashed status
        """

        def _trash():
            response = (
                self.drive_service.files()
                .update(fileId=doc_id, body={"trashed": True}, fields="id,name,trashed")
                .execute()
            )

            return {
                "id": response["id"],
                "name": response["name"],
                "trashed": response.get("trashed", False),
            }

        return self._retry_on_429(_trash)

    def get_template_styles(self, doc_id):
        """Get raw document response from a template document.

        Args:
            doc_id: The template document ID

        Returns:
            Raw Google Docs API response containing namedStyles
        """

        def _get_styles():
            return self.docs_service.documents().get(documentId=doc_id).execute()

        return self._retry_on_429(_get_styles)

    def batch_update(self, doc_id, requests):
        """Apply batch updates to a document.

        Args:
            doc_id: The document ID
            requests: List of request dictionaries for batchUpdate

        Returns:
            Response from the batchUpdate API
        """

        def _batch_update():
            return (
                self.docs_service.documents()
                .batchUpdate(documentId=doc_id, body={"requests": requests})
                .execute()
            )

        return self._retry_on_429(_batch_update)
