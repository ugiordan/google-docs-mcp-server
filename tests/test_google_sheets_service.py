"""Tests for GoogleSheetsService."""

from unittest.mock import MagicMock, patch

from mcp_server.services.google_sheets_service import GoogleSheetsService


def _make_service():
    with patch("mcp_server.services.google_sheets_service.build") as mock_build:
        mock_sheets = MagicMock()
        mock_drive = MagicMock()
        mock_build.side_effect = lambda api, version, credentials=None: (
            mock_sheets if api == "sheets" else mock_drive
        )
        svc = GoogleSheetsService(credentials=MagicMock())
        return svc, mock_sheets, mock_drive


class TestListSpreadsheets:
    def test_returns_spreadsheets(self):
        svc, _, mock_drive = _make_service()
        mock_drive.files().list().execute.return_value = {
            "files": [
                {
                    "id": "ss123",
                    "name": "Test Sheet",
                    "createdTime": "2026-01-01T00:00:00Z",
                    "modifiedTime": "2026-01-02T00:00:00Z",
                }
            ]
        }
        result = svc.list_spreadsheets()
        assert len(result) == 1
        assert result[0]["id"] == "ss123"
        assert "/spreadsheets/d/ss123/edit" in result[0]["url"]

    def test_empty_results(self):
        svc, _, mock_drive = _make_service()
        mock_drive.files().list().execute.return_value = {"files": []}
        result = svc.list_spreadsheets()
        assert result == []

    def test_with_query(self):
        svc, _, mock_drive = _make_service()
        mock_drive.files().list().execute.return_value = {
            "files": [{"id": "s1", "name": "Match", "modifiedTime": ""}]
        }
        result = svc.list_spreadsheets(query="Match")
        assert len(result) == 1


class TestReadSpreadsheet:
    def test_reads_all_sheets(self):
        svc, mock_sheets, _ = _make_service()
        mock_sheets.spreadsheets().get().execute.return_value = {
            "properties": {"title": "My Sheet"},
            "sheets": [
                {
                    "properties": {
                        "sheetId": 0,
                        "title": "Sheet1",
                        "gridProperties": {"rowCount": 100, "columnCount": 26},
                    }
                }
            ],
        }
        mock_sheets.spreadsheets().values().batchGet().execute.return_value = {
            "valueRanges": [
                {"range": "'Sheet1'!A1:Z100", "values": [["a", "b"], ["c", "d"]]}
            ]
        }
        result = svc.read_spreadsheet("ss123")
        assert result["title"] == "My Sheet"
        assert result["sheet_count"] == 1
        assert result["values"]["Sheet1"] == [["a", "b"], ["c", "d"]]

    def test_reads_specific_range(self):
        svc, mock_sheets, _ = _make_service()
        mock_sheets.spreadsheets().get().execute.return_value = {
            "properties": {"title": "My Sheet"},
            "sheets": [],
        }
        mock_sheets.spreadsheets().values().get().execute.return_value = {
            "values": [["x", "y"]]
        }
        result = svc.read_spreadsheet("ss123", range_="Sheet1!A1:B1")
        assert result["values"] == [["x", "y"]]

    def test_empty_spreadsheet(self):
        svc, mock_sheets, _ = _make_service()
        mock_sheets.spreadsheets().get().execute.return_value = {
            "properties": {"title": "Empty"},
            "sheets": [],
        }
        result = svc.read_spreadsheet("ss123")
        assert result["values"] == []
        assert result["sheet_count"] == 0


class TestCreateSpreadsheet:
    def test_creates_spreadsheet(self):
        svc, _, mock_drive = _make_service()
        mock_drive.files().create().execute.return_value = {
            "id": "new123",
            "name": "New Sheet",
        }
        result = svc.create_spreadsheet("New Sheet")
        assert result["id"] == "new123"
        assert "/spreadsheets/d/new123/edit" in result["url"]

    def test_creates_with_folder(self):
        svc, _, mock_drive = _make_service()
        mock_drive.files().create().execute.return_value = {
            "id": "new123",
            "name": "New Sheet",
        }
        svc.create_spreadsheet("New Sheet", folder_id="folder1")
        call_args = mock_drive.files().create.call_args
        body = call_args[1]["body"]
        assert body["parents"] == ["folder1"]


class TestUpdateCells:
    def test_updates_cells(self):
        svc, mock_sheets, _ = _make_service()
        mock_sheets.spreadsheets().values().update().execute.return_value = {
            "updatedRange": "Sheet1!A1:B2",
            "updatedRows": 2,
            "updatedColumns": 2,
            "updatedCells": 4,
        }
        result = svc.update_cells("ss123", "Sheet1!A1:B2", [["a", "b"], ["c", "d"]])
        assert result["updated_cells"] == 4
        assert result["updated_rows"] == 2

    def test_uses_user_entered(self):
        svc, mock_sheets, _ = _make_service()
        mock_sheets.spreadsheets().values().update().execute.return_value = {}
        svc.update_cells("ss123", "Sheet1!A1", [["=SUM(B1:B10)"]])
        call_args = mock_sheets.spreadsheets().values().update.call_args
        assert call_args[1]["valueInputOption"] == "USER_ENTERED"


class TestAppendRows:
    def test_appends_rows(self):
        svc, mock_sheets, _ = _make_service()
        mock_sheets.spreadsheets().values().append().execute.return_value = {
            "updates": {
                "updatedRange": "Sheet1!A5:B6",
                "updatedRows": 2,
                "updatedCells": 4,
            }
        }
        result = svc.append_rows("ss123", "Sheet1", [["e", "f"], ["g", "h"]])
        assert result["updated_rows"] == 2
        assert result["updated_cells"] == 4

    def test_uses_insert_rows(self):
        svc, mock_sheets, _ = _make_service()
        mock_sheets.spreadsheets().values().append().execute.return_value = {
            "updates": {}
        }
        svc.append_rows("ss123", "Sheet1", [["a"]])
        call_args = mock_sheets.spreadsheets().values().append.call_args
        assert call_args[1]["insertDataOption"] == "INSERT_ROWS"
