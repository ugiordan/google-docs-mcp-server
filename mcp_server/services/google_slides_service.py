"""Google Slides service layer for API interactions."""

from googleapiclient.discovery import build

from mcp_server.utils.retry import retry_on_429
from mcp_server.validation import sanitize_query


class GoogleSlidesService:
    """Service layer for Google Slides and Drive API operations."""

    def __init__(self, credentials):
        self.slides_service = build("slides", "v1", credentials=credentials)
        self.drive_service = build("drive", "v3", credentials=credentials)

    def list_presentations(self, query=None, max_results=10):
        def _list():
            q_parts = ["mimeType='application/vnd.google-apps.presentation'"]
            if query:
                sanitized = sanitize_query(query)
                q_parts.append(f"name contains '{sanitized}'")

            response = (
                self.drive_service.files()
                .list(
                    q=" and ".join(q_parts),
                    pageSize=max_results,
                    fields="files(id, name, modifiedTime)",
                    orderBy="modifiedTime desc",
                )
                .execute()
            )

            return [
                {
                    "id": f["id"],
                    "name": f["name"],
                    "modified_time": f.get("modifiedTime", ""),
                    "url": f"https://docs.google.com/presentation/d/{f['id']}/edit",
                }
                for f in response.get("files", [])
            ]

        return retry_on_429(_list)

    def read_presentation(self, presentation_id):
        def _read():
            response = (
                self.slides_service.presentations()
                .get(presentationId=presentation_id)
                .execute()
            )

            layout_map = {}
            for layout in response.get("layouts", []):
                layout_map[layout["objectId"]] = layout.get("layoutProperties", {}).get(
                    "displayName", layout["objectId"]
                )

            slides = []
            for i, slide in enumerate(response.get("slides", [])):
                slide_data = {
                    "slide_number": i + 1,
                    "slide_id": slide["objectId"],
                    "layout": self._get_layout_name(slide, layout_map),
                    "elements": [],
                    "speaker_notes": "",
                }

                for element in slide.get("pageElements", []):
                    el_data = {
                        "element_id": element["objectId"],
                        "type": self._get_element_type(element),
                        "text": "",
                    }
                    if "shape" in element:
                        shape = element["shape"]
                        placeholder = shape.get("placeholder", {}).get("type")
                        if placeholder:
                            el_data["type"] = placeholder
                        el_data["text"] = self._extract_text(shape.get("text", {}))
                    elif "table" in element:
                        table = element["table"]
                        el_data["text"] = (
                            f"{table.get('rows', 0)}x{table.get('columns', 0)} table"
                        )
                    slide_data["elements"].append(el_data)

                notes_id = (
                    slide.get("slideProperties", {})
                    .get("notesPage", {})
                    .get("notesProperties", {})
                    .get("speakerNotesObjectId")
                )
                if notes_id:
                    notes_page = slide.get("slideProperties", {}).get("notesPage", {})
                    for element in notes_page.get("pageElements", []):
                        if element.get("objectId") == notes_id:
                            slide_data["speaker_notes"] = self._extract_text(
                                element.get("shape", {}).get("text", {})
                            )
                            break

                slides.append(slide_data)

            return {
                "id": response["presentationId"],
                "title": response.get("title", ""),
                "slide_count": len(slides),
                "slides": slides,
            }

        return retry_on_429(_read)

    def create_presentation(self, title, folder_id=None):
        def _create():
            body = {
                "name": title,
                "mimeType": "application/vnd.google-apps.presentation",
            }
            if folder_id:
                body["parents"] = [folder_id]

            file_metadata = (
                self.drive_service.files().create(body=body, fields="id,name").execute()
            )

            return {
                "id": file_metadata["id"],
                "name": file_metadata["name"],
                "url": f"https://docs.google.com/presentation/d/{file_metadata['id']}/edit",
            }

        return retry_on_429(_create)

    def add_slide(self, presentation_id, position=None, layout=None):
        def _add():
            request = {"createSlide": {}}
            if position is not None:
                request["createSlide"]["insertionIndex"] = position
            if layout:
                request["createSlide"]["slideLayoutReference"] = {
                    "predefinedLayout": layout
                }

            response = (
                self.slides_service.presentations()
                .batchUpdate(
                    presentationId=presentation_id,
                    body={"requests": [request]},
                )
                .execute()
            )

            slide_id = response["replies"][0]["createSlide"]["objectId"]
            return {
                "presentation_id": presentation_id,
                "slide_id": slide_id,
            }

        return retry_on_429(_add)

    def delete_slide(self, presentation_id, slide_id):
        def _delete():
            request = {"deleteObject": {"objectId": slide_id}}
            self.slides_service.presentations().batchUpdate(
                presentationId=presentation_id, body={"requests": [request]}
            ).execute()
            return {
                "presentation_id": presentation_id,
                "slide_id": slide_id,
                "status": "deleted",
            }

        return retry_on_429(_delete)

    def update_slide_text(self, presentation_id, slide_id, shape_id, content):
        def _update():
            saved_style = self._read_shape_style(presentation_id, slide_id, shape_id)

            requests = [
                {
                    "deleteText": {
                        "objectId": shape_id,
                        "textRange": {"type": "ALL"},
                    }
                },
                {
                    "insertText": {
                        "objectId": shape_id,
                        "insertionIndex": 0,
                        "text": content,
                    }
                },
            ]

            if saved_style:
                fields = ",".join(saved_style.keys())
                requests.append(
                    {
                        "updateTextStyle": {
                            "objectId": shape_id,
                            "textRange": {"type": "ALL"},
                            "style": saved_style,
                            "fields": fields,
                        }
                    }
                )

            self.slides_service.presentations().batchUpdate(
                presentationId=presentation_id, body={"requests": requests}
            ).execute()
            return {
                "presentation_id": presentation_id,
                "slide_id": slide_id,
                "shape_id": shape_id,
                "status": "updated",
            }

        return retry_on_429(_update)

    def delete_shape(self, presentation_id, shape_id):
        def _delete():
            request = {"deleteObject": {"objectId": shape_id}}
            self.slides_service.presentations().batchUpdate(
                presentationId=presentation_id, body={"requests": [request]}
            ).execute()
            return {
                "presentation_id": presentation_id,
                "shape_id": shape_id,
                "status": "deleted",
            }

        return retry_on_429(_delete)

    def update_speaker_notes(self, presentation_id, slide_id, notes):
        def _update():
            _fields = (
                "slides.objectId,"
                "slides.slideProperties.notesPage.notesProperties.speakerNotesObjectId"
            )
            presentation = (
                self.slides_service.presentations()
                .get(presentationId=presentation_id, fields=_fields)
                .execute()
            )

            notes_shape_id = None
            for slide in presentation.get("slides", []):
                if slide["objectId"] == slide_id:
                    notes_shape_id = (
                        slide.get("slideProperties", {})
                        .get("notesPage", {})
                        .get("notesProperties", {})
                        .get("speakerNotesObjectId")
                    )
                    break

            if not notes_shape_id:
                raise ValueError(
                    f"Could not find speaker notes shape for slide '{slide_id}'"
                )

            requests = [
                {
                    "deleteText": {
                        "objectId": notes_shape_id,
                        "textRange": {"type": "ALL"},
                    }
                },
                {
                    "insertText": {
                        "objectId": notes_shape_id,
                        "insertionIndex": 0,
                        "text": notes,
                    }
                },
            ]
            self.slides_service.presentations().batchUpdate(
                presentationId=presentation_id, body={"requests": requests}
            ).execute()
            return {
                "presentation_id": presentation_id,
                "slide_id": slide_id,
                "status": "updated",
            }

        return retry_on_429(_update)

    def duplicate_slide(self, presentation_id, slide_id, position=None):
        def _dup():
            request = {"duplicateObject": {"objectId": slide_id}}
            response = (
                self.slides_service.presentations()
                .batchUpdate(
                    presentationId=presentation_id,
                    body={"requests": [request]},
                )
                .execute()
            )
            return response["replies"][0]["duplicateObject"]["objectId"]

        new_slide_id = retry_on_429(_dup)

        if position is not None:

            def _move():
                move_request = {
                    "updateSlidesPosition": {
                        "slideObjectIds": [new_slide_id],
                        "insertionIndex": position,
                    }
                }
                self.slides_service.presentations().batchUpdate(
                    presentationId=presentation_id,
                    body={"requests": [move_request]},
                ).execute()

            retry_on_429(_move)

        return {
            "presentation_id": presentation_id,
            "original_slide_id": slide_id,
            "new_slide_id": new_slide_id,
        }

    def reorder_slides(self, presentation_id, slide_ids, position):
        def _reorder():
            request = {
                "updateSlidesPosition": {
                    "slideObjectIds": slide_ids,
                    "insertionIndex": position,
                }
            }
            self.slides_service.presentations().batchUpdate(
                presentationId=presentation_id, body={"requests": [request]}
            ).execute()
            return {
                "presentation_id": presentation_id,
                "slide_ids": slide_ids,
                "new_position": position,
                "status": "reordered",
            }

        return retry_on_429(_reorder)

    def convert_markdown_to_slides(self, title, slide_dicts, folder_id=None):
        result = self.create_presentation(title, folder_id)
        presentation_id = result["id"]

        try:
            presentation = retry_on_429(
                lambda: self.slides_service.presentations()
                .get(presentationId=presentation_id)
                .execute()
            )
            default_slide_ids = [s["objectId"] for s in presentation.get("slides", [])]

            requests = []
            for i, slide_data in enumerate(slide_dicts):
                create_req = {
                    "createSlide": {
                        "insertionIndex": i,
                        "slideLayoutReference": {
                            "predefinedLayout": (
                                "TITLE_AND_BODY"
                                if slide_data.get("body_text")
                                else "TITLE_ONLY"
                            )
                        },
                    }
                }
                requests.append(create_req)

            if requests:
                response = retry_on_429(
                    lambda: self.slides_service.presentations()
                    .batchUpdate(
                        presentationId=presentation_id,
                        body={"requests": requests},
                    )
                    .execute()
                )

                new_slide_ids = [
                    r["createSlide"]["objectId"]
                    for r in response.get("replies", [])
                    if "createSlide" in r
                ]

                presentation = retry_on_429(
                    lambda: self.slides_service.presentations()
                    .get(presentationId=presentation_id)
                    .execute()
                )

                text_requests = []
                for idx, sd in enumerate(slide_dicts):
                    if idx >= len(new_slide_ids):
                        break
                    s_id = new_slide_ids[idx]

                    slide = None
                    for s in presentation.get("slides", []):
                        if s["objectId"] == s_id:
                            slide = s
                            break
                    if not slide:
                        continue

                    for element in slide.get("pageElements", []):
                        shape = element.get("shape", {})
                        placeholder_type = shape.get("placeholder", {}).get("type", "")
                        obj_id = element["objectId"]

                        if placeholder_type == "TITLE" and sd.get("title"):
                            text_requests.append(
                                {
                                    "insertText": {
                                        "objectId": obj_id,
                                        "insertionIndex": 0,
                                        "text": sd["title"],
                                    }
                                }
                            )
                        elif placeholder_type == "BODY" and sd.get("body_text"):
                            text_requests.append(
                                {
                                    "insertText": {
                                        "objectId": obj_id,
                                        "insertionIndex": 0,
                                        "text": sd["body_text"],
                                    }
                                }
                            )

                    notes_shape_id = (
                        slide.get("slideProperties", {})
                        .get("notesPage", {})
                        .get("notesProperties", {})
                        .get("speakerNotesObjectId")
                    )
                    if notes_shape_id and sd.get("speaker_notes"):
                        text_requests.append(
                            {
                                "insertText": {
                                    "objectId": notes_shape_id,
                                    "insertionIndex": 0,
                                    "text": sd["speaker_notes"],
                                }
                            }
                        )

                if text_requests:
                    retry_on_429(
                        lambda: self.slides_service.presentations()
                        .batchUpdate(
                            presentationId=presentation_id,
                            body={"requests": text_requests},
                        )
                        .execute()
                    )

            if default_slide_ids:
                delete_requests = [
                    {"deleteObject": {"objectId": sid}} for sid in default_slide_ids
                ]
                retry_on_429(
                    lambda: self.slides_service.presentations()
                    .batchUpdate(
                        presentationId=presentation_id,
                        body={"requests": delete_requests},
                    )
                    .execute()
                )
        except Exception:
            raise ValueError(
                f"Failed to populate presentation. "
                f"Partial presentation created with ID: {presentation_id}"
            ) from None

        return {
            "id": presentation_id,
            "name": title,
            "url": f"https://docs.google.com/presentation/d/{presentation_id}/edit",
            "slide_count": len(slide_dicts),
        }

    _STYLE_FIELDS = [
        "fontFamily",
        "fontSize",
        "foregroundColor",
        "bold",
        "italic",
        "underline",
        "strikethrough",
        "backgroundColor",
    ]

    def _read_shape_style(self, presentation_id, slide_id, shape_id):
        _fields = "slides.objectId,slides.pageElements.objectId,slides.pageElements.shape.text"
        presentation = (
            self.slides_service.presentations()
            .get(presentationId=presentation_id, fields=_fields)
            .execute()
        )
        for slide in presentation.get("slides", []):
            if slide["objectId"] != slide_id:
                continue
            for element in slide.get("pageElements", []):
                if element.get("objectId") != shape_id:
                    continue
                text_elements = (
                    element.get("shape", {}).get("text", {}).get("textElements", [])
                )
                for te in text_elements:
                    style = te.get("textRun", {}).get("style", {})
                    if style:
                        return {
                            k: v
                            for k, v in style.items()
                            if k in self._STYLE_FIELDS and v is not None
                        }
        return {}

    @staticmethod
    def _extract_text(text_obj):
        parts = []
        for element in text_obj.get("textElements", []):
            if "textRun" in element:
                parts.append(element["textRun"].get("content", ""))
        text = "".join(parts)
        if text.endswith("\n"):
            text = text[:-1]
        return text

    @staticmethod
    def _get_element_type(element):
        if "shape" in element:
            return "SHAPE"
        if "image" in element:
            return "IMAGE"
        if "table" in element:
            return "TABLE"
        if "line" in element:
            return "LINE"
        if "video" in element:
            return "VIDEO"
        if "sheetsChart" in element:
            return "CHART"
        if "wordArt" in element:
            return "WORD_ART"
        if "group" in element:
            return "GROUP"
        return "UNKNOWN"

    @staticmethod
    def _get_layout_name(slide, layout_map=None):
        layout_id = slide.get("slideProperties", {}).get("layoutObjectId", "")
        if layout_map and layout_id in layout_map:
            return layout_map[layout_id]
        return layout_id
