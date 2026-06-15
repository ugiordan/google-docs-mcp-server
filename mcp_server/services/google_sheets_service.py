"""Google Sheets service layer for API interactions."""

from googleapiclient.discovery import build

from mcp_server.utils.retry import retry_on_429
from mcp_server.validation import sanitize_query


class GoogleSheetsService:
    """Service layer for Google Sheets and Drive API operations."""

    def __init__(self, credentials):
        self.sheets_service = build("sheets", "v4", credentials=credentials)
        self.drive_service = build("drive", "v3", credentials=credentials)

    def list_spreadsheets(self, query=None, max_results=10):
        def _list():
            q_parts = [
                "mimeType='application/vnd.google-apps.spreadsheet'",
                "trashed=false",
            ]
            if query:
                sanitized = sanitize_query(query)
                q_parts.append(f"name contains '{sanitized}'")

            response = (
                self.drive_service.files()
                .list(
                    q=" and ".join(q_parts),
                    pageSize=max_results,
                    fields="files(id, name, createdTime, modifiedTime)",
                    orderBy="modifiedTime desc",
                )
                .execute()
            )

            return [
                {
                    "id": f["id"],
                    "name": f["name"],
                    "url": f"https://docs.google.com/spreadsheets/d/{f['id']}/edit",
                    "createdTime": f.get("createdTime"),
                    "modifiedTime": f.get("modifiedTime"),
                }
                for f in response.get("files", [])
            ]

        return retry_on_429(_list)

    def read_spreadsheet(self, spreadsheet_id, range_=None):
        def _read():
            meta = (
                self.sheets_service.spreadsheets()
                .get(spreadsheetId=spreadsheet_id)
                .execute()
            )

            title = meta.get("properties", {}).get("title", "")
            sheets = []
            for sheet in meta.get("sheets", []):
                props = sheet.get("properties", {})
                sheets.append(
                    {
                        "sheet_id": props.get("sheetId"),
                        "title": props.get("title", ""),
                        "row_count": props.get("gridProperties", {}).get("rowCount", 0),
                        "column_count": props.get("gridProperties", {}).get(
                            "columnCount", 0
                        ),
                    }
                )

            if range_:
                values_resp = (
                    self.sheets_service.spreadsheets()
                    .values()
                    .get(spreadsheetId=spreadsheet_id, range=range_)
                    .execute()
                )
                values = values_resp.get("values", [])
            else:
                sheet_names = [s["title"] for s in sheets]
                if not sheet_names:
                    values = []
                else:
                    ranges = [f"'{name}'!A:ZZ" for name in sheet_names]
                    batch_resp = (
                        self.sheets_service.spreadsheets()
                        .values()
                        .batchGet(spreadsheetId=spreadsheet_id, ranges=ranges)
                        .execute()
                    )
                    values = {}
                    for vr in batch_resp.get("valueRanges", []):
                        sheet_range = vr.get("range", "")
                        sheet_name = sheet_range.split("!")[0].strip("'")
                        values[sheet_name] = vr.get("values", [])

            return {
                "id": spreadsheet_id,
                "title": title,
                "sheet_count": len(sheets),
                "sheets": sheets,
                "values": values,
            }

        return retry_on_429(_read)

    def create_spreadsheet(self, title, folder_id=None):
        def _create():
            body = {
                "name": title,
                "mimeType": "application/vnd.google-apps.spreadsheet",
            }
            if folder_id:
                body["parents"] = [folder_id]

            result = (
                self.drive_service.files().create(body=body, fields="id,name").execute()
            )
            return {
                "id": result["id"],
                "name": result["name"],
                "url": f"https://docs.google.com/spreadsheets/d/{result['id']}/edit",
            }

        return retry_on_429(_create)

    def update_cells(self, spreadsheet_id, range_, values):
        def _update():
            response = (
                self.sheets_service.spreadsheets()
                .values()
                .update(
                    spreadsheetId=spreadsheet_id,
                    range=range_,
                    valueInputOption="USER_ENTERED",
                    body={"values": values},
                )
                .execute()
            )
            return {
                "spreadsheet_id": spreadsheet_id,
                "updated_range": response.get("updatedRange", range_),
                "updated_rows": response.get("updatedRows", 0),
                "updated_columns": response.get("updatedColumns", 0),
                "updated_cells": response.get("updatedCells", 0),
            }

        return retry_on_429(_update)

    def append_rows(self, spreadsheet_id, range_, rows):
        def _append():
            response = (
                self.sheets_service.spreadsheets()
                .values()
                .append(
                    spreadsheetId=spreadsheet_id,
                    range=range_,
                    valueInputOption="USER_ENTERED",
                    insertDataOption="INSERT_ROWS",
                    body={"values": rows},
                )
                .execute()
            )
            updates = response.get("updates", {})
            return {
                "spreadsheet_id": spreadsheet_id,
                "updated_range": updates.get("updatedRange", range_),
                "updated_rows": updates.get("updatedRows", 0),
                "updated_cells": updates.get("updatedCells", 0),
            }

        return retry_on_429(_append)
