import json
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

from mcp_server.auth import SCOPES, load_tokens, revoke_tokens, save_tokens


class TestScopes:
    def test_scopes_are_least_privilege(self):
        assert "https://www.googleapis.com/auth/drive" not in SCOPES
        assert "https://www.googleapis.com/auth/drive.file" in SCOPES
        assert "https://www.googleapis.com/auth/drive.metadata.readonly" in SCOPES
        assert "https://www.googleapis.com/auth/documents" in SCOPES
        assert len(SCOPES) == 3


class TestLoadTokens:
    def test_loads_valid_tokens(self, tmp_path):
        token_file = tmp_path / "tokens.json"
        # Create a token that expires in the future
        expiry = datetime.now(UTC) + timedelta(hours=1)
        token_file.write_text(
            json.dumps(
                {
                    "token": "access_token_value",
                    "refresh_token": "refresh_token_value",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "client_id": "client_id",
                    "client_secret": "client_secret",
                    "scopes": ["https://www.googleapis.com/auth/drive.file"],
                    "expiry": expiry.isoformat() + "Z",
                }
            )
        )
        creds = load_tokens(str(token_file))
        assert creds is not None

    def test_returns_none_for_missing_file(self):
        creds = load_tokens("/nonexistent/tokens.json")
        assert creds is None


class TestSaveTokens:
    def test_saves_with_secure_permissions(self, tmp_path):
        token_file = tmp_path / "tokens.json"
        mock_creds = MagicMock()
        mock_creds.to_json.return_value = '{"token": "test"}'
        save_tokens(mock_creds, str(token_file))
        assert token_file.exists()
        assert oct(token_file.stat().st_mode)[-3:] == "600"


class TestRevokeTokens:
    @patch("mcp_server.auth.requests.post")
    def test_revoke_calls_google_endpoint(self, mock_post, tmp_path):
        token_file = tmp_path / "tokens.json"
        token_file.write_text(
            json.dumps(
                {
                    "token": "access_token_value",
                    "refresh_token": "refresh_token_value",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "client_id": "id",
                    "client_secret": "secret",
                    "scopes": [],
                }
            )
        )
        mock_post.return_value.status_code = 200
        revoke_tokens(str(token_file))
        mock_post.assert_called_once()
        assert not token_file.exists()
