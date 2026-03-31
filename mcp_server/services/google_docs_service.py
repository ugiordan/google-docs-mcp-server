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
        """Read the content of a Google Doc.

        Args:
            doc_id: The document ID

        Returns:
            Dictionary with id, title, and content

        Raises:
            Exception: On access denied or not found errors
        """

        def _read():
            try:
                response = (
                    self.docs_service.documents().get(documentId=doc_id).execute()
                )
            except HttpError as e:
                # Let 429 errors propagate to _retry_on_429
                if e.resp.status == 429:
                    raise
                # Map other errors to user-friendly messages
                if e.resp.status == 403:
                    raise Exception("Access denied") from e
                elif e.resp.status == 404:
                    raise Exception("Document not found") from e
                else:
                    raise Exception(f"Error reading document: {e.resp.status}") from e

            # Extract text content
            content_parts = []
            for item in response.get("body", {}).get("content", []):
                if "paragraph" in item:
                    for element in item["paragraph"].get("elements", []):
                        if "textRun" in element:
                            content_parts.append(element["textRun"].get("content", ""))

            return {
                "id": response["documentId"],
                "title": response.get("title", ""),
                "content": "".join(content_parts),
            }

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

    def update_document(self, doc_id, content, mode="append"):
        """Update a Google Doc with new content.

        Args:
            doc_id: The document ID
            content: Content to add or replace
            mode: Update mode - 'append' or 'replace' (default: 'append')

        Returns:
            Dictionary with id, name, url, and updatedTime
        """
        if mode == "replace":
            self.clear_document(doc_id)

        def _update():
            if mode == "append":
                # Get current document to find endIndex
                doc = self.docs_service.documents().get(documentId=doc_id).execute()
                end_index = 1
                for item in doc.get("body", {}).get("content", []):
                    if "endIndex" in item:
                        end_index = item["endIndex"]

                requests = [
                    {
                        "insertText": {
                            "location": {"index": end_index - 1},
                            "text": content,
                        }
                    }
                ]
            else:  # replace (already cleared)
                requests = [{"insertText": {"location": {"index": 1}, "text": content}}]

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

    def clear_document(self, doc_id):
        """Clear all content from a document.

        Args:
            doc_id: The document ID

        Returns:
            The original endIndex before clearing
        """

        def _clear():
            doc = self.docs_service.documents().get(documentId=doc_id).execute()

            end_index = 1
            for item in doc.get("body", {}).get("content", []):
                if "endIndex" in item:
                    end_index = item["endIndex"]

            if end_index > 1:
                requests = [
                    {
                        "deleteContentRange": {
                            "range": {"startIndex": 1, "endIndex": end_index - 1}
                        }
                    }
                ]
                self.docs_service.documents().batchUpdate(
                    documentId=doc_id, body={"requests": requests}
                ).execute()

            return end_index

        return self._retry_on_429(_clear)

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

            media = MediaInMemoryUpload(file_bytes, mimetype=mime_type, resumable=True)

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
            # Verify target folder is accessible (owned by authenticated user)
            try:
                self.drive_service.files().get(
                    fileId=folder_id, fields="id,name"
                ).execute()
            except HttpError as e:
                if e.resp.status == 429:
                    raise
                if e.resp.status == 404:
                    raise Exception("Target folder not found") from e
                elif e.resp.status == 403:
                    raise Exception("Access denied to target folder") from e
                else:
                    raise Exception(f"Error accessing folder: {e.resp.status}") from e

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
