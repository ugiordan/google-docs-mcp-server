# Google OAuth Setup

## 1. Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click the project dropdown at the top and select **New Project**
3. Enter a project name (e.g., "Google Docs MCP") and click **Create**
4. Make sure the new project is selected in the dropdown

## 2. Enable APIs

1. Navigate to **APIs & Services > Library**
2. Search for and enable each of these APIs:
    - **Google Docs API**: provides document content read/write
    - **Google Drive API**: provides file listing, metadata, move, trash, and comment operations
    - **Google Slides API**: provides presentation content read/write

## 3. Configure OAuth Consent Screen

1. Navigate to **APIs & Services > OAuth consent screen**
2. Select **External** user type (or **Internal** if using Google Workspace) and click **Create**
3. Fill in the required fields: app name, user support email, developer contact email
4. On the **Scopes** page, click **Add or Remove Scopes** and add:
    - `https://www.googleapis.com/auth/drive`
    - `https://www.googleapis.com/auth/drive.metadata.readonly`
    - `https://www.googleapis.com/auth/documents`
5. On the **Test users** page, add your Google account email
6. Click **Save and Continue** through the remaining steps

!!! note
    While the app is in "Testing" status, only test users you explicitly added can authenticate. This is fine for personal use. Publishing the app removes that restriction but requires Google verification.

## 4. Create OAuth 2.0 Client ID

1. Navigate to **APIs & Services > Credentials**
2. Click **Create Credentials > OAuth 2.0 Client ID**
3. Select **Desktop app** as the application type
4. Give it a name (e.g., "google-docs-mcp")
5. Click **Create**
6. Click **Download JSON** on the confirmation dialog
7. Save the file as `~/.config/google-docs-mcp/credentials.json`

## OAuth Scopes

The server requests three scopes during authentication:

| Scope | Access Granted |
|-------|---------------|
| `drive` | Full read/write/delete access to Google Drive files. Required for comment, move, and delete operations on any document. |
| `drive.metadata.readonly` | Read-only access to file metadata (names, IDs, timestamps, folder structure). Cannot read file content through this scope. |
| `documents` | Read and write access to Google Docs document content and formatting. |

!!! warning
    The `drive` scope grants access to all files in the user's Drive. Container hardening (read-only filesystem, dropped capabilities, non-root, memory limits) provides defense in depth. See [Security](../security.md) for the full threat model.
