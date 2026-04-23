"""Tests for GoogleSlidesService."""

from unittest.mock import MagicMock, patch

from mcp_server.services.google_slides_service import GoogleSlidesService


def _make_service():
    with patch("mcp_server.services.google_slides_service.build") as mock_build:
        mock_slides = MagicMock()
        mock_drive = MagicMock()
        mock_build.side_effect = lambda api, version, credentials=None: (
            mock_slides if api == "slides" else mock_drive
        )
        svc = GoogleSlidesService(credentials=MagicMock())
        return svc, mock_slides, mock_drive


class TestListPresentations:
    def test_returns_presentations(self):
        svc, _, mock_drive = _make_service()
        mock_drive.files().list().execute.return_value = {
            "files": [
                {"id": "abc123", "name": "Test Pres", "modifiedTime": "2026-01-01T00:00:00Z"}
            ]
        }
        result = svc.list_presentations()
        assert len(result) == 1
        assert result[0]["id"] == "abc123"
        assert result[0]["name"] == "Test Pres"
        assert "/presentation/d/abc123/edit" in result[0]["url"]

    def test_empty_results(self):
        svc, _, mock_drive = _make_service()
        mock_drive.files().list().execute.return_value = {"files": []}
        result = svc.list_presentations()
        assert result == []


class TestReadPresentation:
    def test_reads_slides(self):
        svc, mock_slides, _ = _make_service()
        mock_slides.presentations().get().execute.return_value = {
            "presentationId": "pres123",
            "title": "My Presentation",
            "slides": [
                {
                    "objectId": "slide1",
                    "slideProperties": {
                        "layoutObjectId": "layout1",
                        "notesPage": {
                            "notesProperties": {"speakerNotesObjectId": "notes1"},
                            "pageElements": [
                                {
                                    "objectId": "notes1",
                                    "shape": {
                                        "text": {
                                            "textElements": [
                                                {"textRun": {"content": "Speaker note text"}}
                                            ]
                                        }
                                    },
                                }
                            ],
                        },
                    },
                    "pageElements": [
                        {
                            "objectId": "shape1",
                            "shape": {
                                "placeholder": {"type": "TITLE"},
                                "text": {
                                    "textElements": [
                                        {"textRun": {"content": "Slide Title"}}
                                    ]
                                },
                            },
                        }
                    ],
                }
            ],
        }
        result = svc.read_presentation("pres123")
        assert result["id"] == "pres123"
        assert result["title"] == "My Presentation"
        assert result["slide_count"] == 1
        slide = result["slides"][0]
        assert slide["slide_id"] == "slide1"
        assert slide["shapes"][0]["type"] == "TITLE"
        assert slide["shapes"][0]["text"] == "Slide Title"
        assert slide["speaker_notes"] == "Speaker note text"


class TestCreatePresentation:
    def test_creates_presentation(self):
        svc, _, mock_drive = _make_service()
        mock_drive.files().create().execute.return_value = {
            "id": "new123",
            "name": "New Pres",
        }
        result = svc.create_presentation("New Pres")
        assert result["id"] == "new123"
        assert "/presentation/d/new123/edit" in result["url"]

    def test_creates_with_folder(self):
        svc, _, mock_drive = _make_service()
        mock_drive.files().create().execute.return_value = {
            "id": "new123",
            "name": "New Pres",
        }
        svc.create_presentation("New Pres", folder_id="folder1")
        mock_drive.files().create.assert_called()


class TestAddSlide:
    def test_adds_slide(self):
        svc, mock_slides, _ = _make_service()
        mock_slides.presentations().batchUpdate().execute.return_value = {
            "replies": [{"createSlide": {"objectId": "newslide1"}}]
        }
        result = svc.add_slide("pres123")
        assert result["slide_id"] == "newslide1"
        assert result["presentation_id"] == "pres123"


class TestDeleteSlide:
    def test_deletes_slide(self):
        svc, mock_slides, _ = _make_service()
        mock_slides.presentations().batchUpdate().execute.return_value = {}
        result = svc.delete_slide("pres123", "slide1")
        assert result["status"] == "deleted"
        assert result["slide_id"] == "slide1"


class TestUpdateSlideText:
    def test_updates_text(self):
        svc, mock_slides, _ = _make_service()
        mock_slides.presentations().batchUpdate().execute.return_value = {}
        result = svc.update_slide_text("pres123", "slide1", "shape1", "New text")
        assert result["status"] == "updated"
        assert result["shape_id"] == "shape1"


class TestUpdateSpeakerNotes:
    def test_updates_notes(self):
        svc, mock_slides, _ = _make_service()
        mock_slides.presentations().get().execute.return_value = {
            "slides": [
                {
                    "objectId": "slide1",
                    "slideProperties": {
                        "notesPage": {
                            "notesProperties": {"speakerNotesObjectId": "notes1"}
                        }
                    },
                }
            ]
        }
        mock_slides.presentations().batchUpdate().execute.return_value = {}
        result = svc.update_speaker_notes("pres123", "slide1", "My notes")
        assert result["status"] == "updated"

    def test_raises_on_missing_notes_shape(self):
        svc, mock_slides, _ = _make_service()
        mock_slides.presentations().get().execute.return_value = {
            "slides": [
                {
                    "objectId": "slide1",
                    "slideProperties": {},
                }
            ]
        }
        try:
            svc.update_speaker_notes("pres123", "slide1", "Notes")
            assert False, "Should have raised"
        except ValueError as e:
            assert "speaker notes" in str(e).lower()


class TestDuplicateSlide:
    def test_duplicates_slide(self):
        svc, mock_slides, _ = _make_service()
        mock_slides.presentations().batchUpdate().execute.return_value = {
            "replies": [{"duplicateObject": {"objectId": "slide1_copy"}}]
        }
        result = svc.duplicate_slide("pres123", "slide1")
        assert result["new_slide_id"] == "slide1_copy"
        assert result["original_slide_id"] == "slide1"


class TestReadPresentationEdgeCases:
    def test_zero_slides(self):
        svc, mock_slides, _ = _make_service()
        mock_slides.presentations().get().execute.return_value = {
            "presentationId": "pres123",
            "title": "Empty Pres",
            "slides": [],
        }
        result = svc.read_presentation("pres123")
        assert result["slide_count"] == 0
        assert result["slides"] == []

    def test_non_shape_elements_skipped(self):
        svc, mock_slides, _ = _make_service()
        mock_slides.presentations().get().execute.return_value = {
            "presentationId": "pres123",
            "title": "Mixed Elements",
            "slides": [
                {
                    "objectId": "s1",
                    "slideProperties": {},
                    "pageElements": [
                        {"objectId": "img1", "image": {"sourceUrl": "https://example.com/img.png"}},
                        {"objectId": "tbl1", "table": {"rows": 2, "columns": 2}},
                    ],
                }
            ],
        }
        result = svc.read_presentation("pres123")
        assert len(result["slides"]) == 1
        assert result["slides"][0]["shapes"] == []

    def test_slide_without_speaker_notes_page(self):
        svc, mock_slides, _ = _make_service()
        mock_slides.presentations().get().execute.return_value = {
            "presentationId": "pres123",
            "title": "No Notes",
            "slides": [
                {
                    "objectId": "s1",
                    "slideProperties": {},
                    "pageElements": [],
                }
            ],
        }
        result = svc.read_presentation("pres123")
        assert result["slides"][0]["speaker_notes"] == ""

    def test_no_slides_key_in_response(self):
        svc, mock_slides, _ = _make_service()
        mock_slides.presentations().get().execute.return_value = {
            "presentationId": "pres123",
            "title": "Weird",
        }
        result = svc.read_presentation("pres123")
        assert result["slide_count"] == 0
        assert result["slides"] == []


class TestUpdateSpeakerNotesEdgeCases:
    def test_slide_not_found(self):
        svc, mock_slides, _ = _make_service()
        mock_slides.presentations().get().execute.return_value = {
            "slides": [
                {
                    "objectId": "other_slide",
                    "slideProperties": {
                        "notesPage": {
                            "notesProperties": {"speakerNotesObjectId": "n1"}
                        }
                    },
                }
            ]
        }
        try:
            svc.update_speaker_notes("pres123", "nonexistent_slide", "Notes")
            assert False, "Should have raised"
        except ValueError as e:
            assert "nonexistent_slide" in str(e)

    def test_empty_slides_list(self):
        svc, mock_slides, _ = _make_service()
        mock_slides.presentations().get().execute.return_value = {"slides": []}
        try:
            svc.update_speaker_notes("pres123", "slide1", "Notes")
            assert False, "Should have raised"
        except ValueError as e:
            assert "speaker notes" in str(e).lower()


class TestConvertMarkdownToSlides:
    def test_creates_presentation_with_slides(self):
        svc, mock_slides, mock_drive = _make_service()

        mock_drive.files().create().execute.return_value = {
            "id": "new_pres",
            "name": "Test Pres",
        }

        mock_slides.presentations().get().execute.side_effect = [
            {"slides": [{"objectId": "default_slide"}]},
            {
                "slides": [
                    {
                        "objectId": "slide_0",
                        "slideProperties": {
                            "notesPage": {
                                "notesProperties": {"speakerNotesObjectId": "notes_0"}
                            }
                        },
                        "pageElements": [
                            {
                                "objectId": "title_0",
                                "shape": {
                                    "placeholder": {"type": "TITLE"},
                                    "text": {"textElements": []},
                                },
                            },
                            {
                                "objectId": "body_0",
                                "shape": {
                                    "placeholder": {"type": "BODY"},
                                    "text": {"textElements": []},
                                },
                            },
                        ],
                    }
                ]
            },
        ]

        mock_slides.presentations().batchUpdate().execute.return_value = {
            "replies": [{"createSlide": {"objectId": "slide_0"}}]
        }

        slide_dicts = [
            {"title": "Hello", "body_text": "World", "speaker_notes": "Say hello"}
        ]
        result = svc.convert_markdown_to_slides("Test Pres", slide_dicts)

        assert result["id"] == "new_pres"
        assert result["slide_count"] == 1
        assert result["name"] == "Test Pres"
        assert "/presentation/d/new_pres/edit" in result["url"]

    def test_empty_slide_dicts(self):
        svc, mock_slides, mock_drive = _make_service()

        mock_drive.files().create().execute.return_value = {
            "id": "new_pres",
            "name": "Empty Pres",
        }

        mock_slides.presentations().get().execute.return_value = {
            "slides": [{"objectId": "default_slide"}]
        }

        mock_slides.presentations().batchUpdate().execute.return_value = {}

        result = svc.convert_markdown_to_slides("Empty Pres", [])
        assert result["slide_count"] == 0

    def test_slide_with_no_body(self):
        svc, mock_slides, mock_drive = _make_service()

        mock_drive.files().create().execute.return_value = {
            "id": "p1",
            "name": "Title Only",
        }

        mock_slides.presentations().get().execute.side_effect = [
            {"slides": []},
            {
                "slides": [
                    {
                        "objectId": "s0",
                        "slideProperties": {},
                        "pageElements": [
                            {
                                "objectId": "t0",
                                "shape": {
                                    "placeholder": {"type": "TITLE"},
                                    "text": {"textElements": []},
                                },
                            }
                        ],
                    }
                ]
            },
        ]

        mock_slides.presentations().batchUpdate().execute.return_value = {
            "replies": [{"createSlide": {"objectId": "s0"}}]
        }

        slide_dicts = [{"title": "Only Title", "body_text": "", "speaker_notes": ""}]
        result = svc.convert_markdown_to_slides("Title Only", slide_dicts)
        assert result["slide_count"] == 1

    def test_with_folder_id(self):
        svc, mock_slides, mock_drive = _make_service()

        mock_drive.files().create().execute.return_value = {
            "id": "p1",
            "name": "In Folder",
        }

        mock_slides.presentations().get().execute.side_effect = [
            {"slides": []},
            {"slides": []},
        ]

        mock_slides.presentations().batchUpdate().execute.return_value = {
            "replies": []
        }

        result = svc.convert_markdown_to_slides(
            "In Folder", [{"title": "S1", "body_text": "B", "speaker_notes": ""}],
            folder_id="folder123"
        )
        assert result["id"] == "p1"


class TestExtractText:
    def test_empty_text_obj(self):
        assert GoogleSlidesService._extract_text({}) == ""

    def test_no_text_runs(self):
        assert GoogleSlidesService._extract_text({"textElements": [{"paragraphMarker": {}}]}) == ""

    def test_multiple_runs(self):
        text_obj = {
            "textElements": [
                {"textRun": {"content": "Hello "}},
                {"textRun": {"content": "World"}},
            ]
        }
        assert GoogleSlidesService._extract_text(text_obj) == "Hello World"


class TestGetLayoutName:
    def test_no_slide_properties(self):
        assert GoogleSlidesService._get_layout_name({}) == ""

    def test_with_layout(self):
        slide = {"slideProperties": {"layoutObjectId": "layout_abc"}}
        assert GoogleSlidesService._get_layout_name(slide) == "layout_abc"


class TestReorderSlides:
    def test_reorders_slides(self):
        svc, mock_slides, _ = _make_service()
        mock_slides.presentations().batchUpdate().execute.return_value = {}
        result = svc.reorder_slides("pres123", ["slide2", "slide1"], 0)
        assert result["status"] == "reordered"
        assert result["new_position"] == 0
