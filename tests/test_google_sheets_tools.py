"""Tests for Google Sheets MCP tools."""

import json
from unittest.mock import MagicMock

from mcp_server.tools.google_sheets_tools import (
    _append_rows,
    _create_spreadsheet,
    _list_spreadsheets,
    _read_spreadsheet,
    _update_cells,
)

_SS_ID = "spreadsheet1234"


def _svc():
    return MagicMock()


class TestListSpreadsheets:
    def test_success(self):
        svc = _svc()
        svc.list_spreadsheets.return_value = [
            {
                "id": "s1",
                "name": "Test",
                "url": "...",
                "createdTime": "",
                "modifiedTime": "",
            }
        ]
        result = json.loads(_list_spreadsheets(svc))
        assert len(result) == 1
        assert "untrusted-data" in result[0]["name"]

    def test_invalid_max_results_low(self):
        result = json.loads(_list_spreadsheets(_svc(), max_results=0))
        assert result["code"] == "VALIDATION_ERROR"

    def test_invalid_max_results_high(self):
        result = json.loads(_list_spreadsheets(_svc(), max_results=101))
        assert result["code"] == "VALIDATION_ERROR"

    def test_api_error(self):
        svc = _svc()
        svc.list_spreadsheets.side_effect = Exception("fail")
        result = json.loads(_list_spreadsheets(svc))
        assert result["code"] == "API_ERROR"


class TestReadSpreadsheet:
    def test_success_all_sheets(self):
        svc = _svc()
        svc.read_spreadsheet.return_value = {
            "id": _SS_ID,
            "title": "My Sheet",
            "sheet_count": 1,
            "sheets": [
                {"sheet_id": 0, "title": "Sheet1", "row_count": 10, "column_count": 5}
            ],
            "values": {"Sheet1": [["a", "b"], ["c", "d"]]},
        }
        result = json.loads(_read_spreadsheet(svc, _SS_ID))
        assert result["id"] == _SS_ID
        assert "untrusted-data" in result["title"]
        assert "<spreadsheet-content-" in result["content"]
        assert "a\tb" in result["content"]
        assert "values" not in result

    def test_success_with_range(self):
        svc = _svc()
        svc.read_spreadsheet.return_value = {
            "id": _SS_ID,
            "title": "My Sheet",
            "sheet_count": 1,
            "sheets": [],
            "values": [["x"]],
        }
        result = json.loads(_read_spreadsheet(svc, _SS_ID, range_="Sheet1!A1"))
        assert "x" in result["content"]

    def test_invalid_id(self):
        result = json.loads(_read_spreadsheet(_svc(), "bad"))
        assert result["code"] == "VALIDATION_ERROR"

    def test_api_error(self):
        svc = _svc()
        svc.read_spreadsheet.side_effect = Exception("fail")
        result = json.loads(_read_spreadsheet(svc, _SS_ID))
        assert result["code"] == "API_ERROR"


class TestCreateSpreadsheet:
    def test_success(self):
        svc = _svc()
        svc.create_spreadsheet.return_value = {
            "id": "new1",
            "name": "New Sheet",
            "url": "https://...",
        }
        result = json.loads(_create_spreadsheet(svc, "New Sheet"))
        assert result["id"] == "new1"
        assert "untrusted-data" in result["name"]

    def test_empty_title(self):
        result = json.loads(_create_spreadsheet(_svc(), ""))
        assert result["code"] == "VALIDATION_ERROR"

    def test_api_error(self):
        svc = _svc()
        svc.create_spreadsheet.side_effect = Exception("fail")
        result = json.loads(_create_spreadsheet(svc, "Test"))
        assert result["code"] == "API_ERROR"


class TestUpdateCells:
    def test_success(self):
        svc = _svc()
        svc.update_cells.return_value = {
            "spreadsheet_id": _SS_ID,
            "updated_range": "Sheet1!A1:B2",
            "updated_rows": 2,
            "updated_columns": 2,
            "updated_cells": 4,
        }
        values = json.dumps([["a", "b"], ["c", "d"]])
        result = json.loads(_update_cells(svc, _SS_ID, "Sheet1!A1:B2", values))
        assert result["updated_cells"] == 4

    def test_invalid_id(self):
        result = json.loads(_update_cells(_svc(), "bad", "A1", "[[1]]"))
        assert result["code"] == "VALIDATION_ERROR"

    def test_empty_range(self):
        result = json.loads(_update_cells(_svc(), _SS_ID, "", "[[1]]"))
        assert result["code"] == "VALIDATION_ERROR"

    def test_invalid_json(self):
        result = json.loads(_update_cells(_svc(), _SS_ID, "A1", "not json"))
        assert result["code"] == "VALIDATION_ERROR"

    def test_not_array(self):
        result = json.loads(_update_cells(_svc(), _SS_ID, "A1", '{"a": 1}'))
        assert result["code"] == "VALIDATION_ERROR"

    def test_empty_array(self):
        result = json.loads(_update_cells(_svc(), _SS_ID, "A1", "[]"))
        assert result["code"] == "VALIDATION_ERROR"

    def test_row_not_array(self):
        result = json.loads(_update_cells(_svc(), _SS_ID, "A1", '["not array"]'))
        assert result["code"] == "VALIDATION_ERROR"

    def test_api_error(self):
        svc = _svc()
        svc.update_cells.side_effect = Exception("fail")
        result = json.loads(_update_cells(svc, _SS_ID, "A1", '[["a"]]'))
        assert result["code"] == "API_ERROR"


class TestAppendRows:
    def test_success(self):
        svc = _svc()
        svc.append_rows.return_value = {
            "spreadsheet_id": _SS_ID,
            "updated_range": "Sheet1!A5:B6",
            "updated_rows": 2,
            "updated_cells": 4,
        }
        rows = json.dumps([["e", "f"], ["g", "h"]])
        result = json.loads(_append_rows(svc, _SS_ID, "Sheet1", rows))
        assert result["updated_rows"] == 2

    def test_invalid_id(self):
        result = json.loads(_append_rows(_svc(), "bad", "Sheet1", '[["a"]]'))
        assert result["code"] == "VALIDATION_ERROR"

    def test_empty_range(self):
        result = json.loads(_append_rows(_svc(), _SS_ID, "", '[["a"]]'))
        assert result["code"] == "VALIDATION_ERROR"

    def test_invalid_json(self):
        result = json.loads(_append_rows(_svc(), _SS_ID, "Sheet1", "bad"))
        assert result["code"] == "VALIDATION_ERROR"

    def test_not_array(self):
        result = json.loads(_append_rows(_svc(), _SS_ID, "Sheet1", '{"a": 1}'))
        assert result["code"] == "VALIDATION_ERROR"

    def test_empty_array(self):
        result = json.loads(_append_rows(_svc(), _SS_ID, "Sheet1", "[]"))
        assert result["code"] == "VALIDATION_ERROR"

    def test_too_many_rows(self):
        rows = json.dumps([["a"] for _ in range(1001)])
        result = json.loads(_append_rows(_svc(), _SS_ID, "Sheet1", rows))
        assert result["code"] == "VALIDATION_ERROR"
        assert "1000" in result["error"]

    def test_row_not_array(self):
        result = json.loads(_append_rows(_svc(), _SS_ID, "Sheet1", '["not"]'))
        assert result["code"] == "VALIDATION_ERROR"

    def test_api_error(self):
        svc = _svc()
        svc.append_rows.side_effect = Exception("fail")
        result = json.loads(_append_rows(svc, _SS_ID, "Sheet1", '[["a"]]'))
        assert result["code"] == "API_ERROR"
