"""Tests for GoogleSlidesService."""

from unittest.mock import MagicMock, patch

import pytest

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
                {
                    "id": "abc123",
                    "name": "Test Pres",
                    "modifiedTime": "2026-01-01T00:00:00Z",
                }
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

    def test_with_query(self):
        svc, _, mock_drive = _make_service()
        mock_drive.files().list().execute.return_value = {
            "files": [{"id": "p1", "name": "Match", "modifiedTime": ""}]
        }
        result = svc.list_presentations(query="Match")
        assert len(result) == 1


class TestReadPresentation:
    def test_reads_slides(self):
        svc, mock_slides, _ = _make_service()
        mock_slides.presentations().get().execute.return_value = {
            "presentationId": "pres123",
            "title": "My Presentation",
            "layouts": [
                {
                    "objectId": "layout1",
                    "layoutProperties": {"displayName": "Title Slide"},
                }
            ],
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
                                                {
                                                    "textRun": {
                                                        "content": "Speaker note text"
                                                    }
                                                }
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
        assert slide["layout"] == "Title Slide"
        assert slide["elements"][0]["type"] == "TITLE"
        assert slide["elements"][0]["text"] == "Slide Title"
        assert slide["speaker_notes"] == "Speaker note text"

    def test_surfaces_non_shape_elements(self):
        svc, mock_slides, _ = _make_service()
        mock_slides.presentations().get().execute.return_value = {
            "presentationId": "pres123",
            "title": "Mixed",
            "slides": [
                {
                    "objectId": "s1",
                    "slideProperties": {},
                    "pageElements": [
                        {
                            "objectId": "img1",
                            "image": {"sourceUrl": "https://x.com/i.png"},
                        },
                        {
                            "objectId": "tbl1",
                            "table": {"rows": 3, "columns": 2},
                        },
                        {"objectId": "line1", "line": {}},
                    ],
                }
            ],
        }
        result = svc.read_presentation("pres123")
        elements = result["slides"][0]["elements"]
        assert len(elements) == 3
        assert elements[0]["type"] == "IMAGE"
        assert elements[1]["type"] == "TABLE"
        assert elements[1]["text"] == "3x2 table"
        assert elements[2]["type"] == "LINE"


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
        mock_slides.presentations().get().execute.return_value = {
            "slides": [
                {
                    "objectId": "slide1",
                    "pageElements": [
                        {
                            "objectId": "shape1",
                            "shape": {
                                "text": {
                                    "textElements": [
                                        {
                                            "textRun": {
                                                "content": "Old text",
                                                "style": {
                                                    "fontFamily": "Arial",
                                                    "fontSize": {
                                                        "magnitude": 18,
                                                        "unit": "PT",
                                                    },
                                                },
                                            }
                                        }
                                    ]
                                }
                            },
                        }
                    ],
                }
            ]
        }
        mock_slides.presentations().batchUpdate().execute.return_value = {}
        result = svc.update_slide_text("pres123", "slide1", "shape1", "New text")
        assert result["status"] == "updated"
        assert result["shape_id"] == "shape1"

    def test_preserves_style(self):
        svc, mock_slides, _ = _make_service()
        mock_slides.presentations().get().execute.return_value = {
            "slides": [
                {
                    "objectId": "s1",
                    "pageElements": [
                        {
                            "objectId": "sh1",
                            "shape": {
                                "text": {
                                    "textElements": [
                                        {
                                            "textRun": {
                                                "content": "Styled",
                                                "style": {
                                                    "fontFamily": "Roboto",
                                                    "fontSize": {
                                                        "magnitude": 24,
                                                        "unit": "PT",
                                                    },
                                                    "bold": True,
                                                    "foregroundColor": {
                                                        "opaqueColor": {
                                                            "rgbColor": {"red": 1.0}
                                                        }
                                                    },
                                                },
                                            }
                                        }
                                    ]
                                }
                            },
                        }
                    ],
                }
            ]
        }
        mock_slides.presentations().batchUpdate().execute.return_value = {}
        svc.update_slide_text("pres123", "s1", "sh1", "New")

        call_args = mock_slides.presentations().batchUpdate.call_args
        requests = call_args[1]["body"]["requests"]
        assert len(requests) == 3
        style_req = requests[2]["updateTextStyle"]
        assert style_req["style"]["fontFamily"] == "Roboto"
        assert style_req["style"]["bold"] is True
        assert "fontSize" in style_req["fields"]

    def test_no_style_skips_update_text_style(self):
        svc, mock_slides, _ = _make_service()
        mock_slides.presentations().get().execute.return_value = {
            "slides": [
                {
                    "objectId": "s1",
                    "pageElements": [
                        {
                            "objectId": "sh1",
                            "shape": {"text": {"textElements": []}},
                        }
                    ],
                }
            ]
        }
        mock_slides.presentations().batchUpdate().execute.return_value = {}
        svc.update_slide_text("pres123", "s1", "sh1", "Text")

        call_args = mock_slides.presentations().batchUpdate.call_args
        requests = call_args[1]["body"]["requests"]
        assert len(requests) == 2


class TestDeleteShape:
    def test_deletes_shape(self):
        svc, mock_slides, _ = _make_service()
        mock_slides.presentations().batchUpdate().execute.return_value = {}
        result = svc.delete_shape("pres123", "img1")
        assert result["status"] == "deleted"
        assert result["shape_id"] == "img1"

    def test_returns_presentation_id(self):
        svc, mock_slides, _ = _make_service()
        mock_slides.presentations().batchUpdate().execute.return_value = {}
        result = svc.delete_shape("pres123", "shape1")
        assert result["presentation_id"] == "pres123"


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
        with pytest.raises(ValueError, match="speaker notes"):
            svc.update_speaker_notes("pres123", "slide1", "Notes")


class TestUpdateSpeakerNotesEdgeCases:
    def test_slide_not_found(self):
        svc, mock_slides, _ = _make_service()
        mock_slides.presentations().get().execute.return_value = {
            "slides": [
                {
                    "objectId": "other_slide",
                    "slideProperties": {
                        "notesPage": {"notesProperties": {"speakerNotesObjectId": "n1"}}
                    },
                }
            ]
        }
        with pytest.raises(ValueError, match="nonexistent_slide"):
            svc.update_speaker_notes("pres123", "nonexistent_slide", "Notes")

    def test_empty_slides_list(self):
        svc, mock_slides, _ = _make_service()
        mock_slides.presentations().get().execute.return_value = {"slides": []}
        with pytest.raises(ValueError, match="speaker notes"):
            svc.update_speaker_notes("pres123", "slide1", "Notes")


class TestDuplicateSlide:
    def test_duplicates_slide(self):
        svc, mock_slides, _ = _make_service()
        mock_slides.presentations().batchUpdate().execute.return_value = {
            "replies": [{"duplicateObject": {"objectId": "slide1_copy"}}]
        }
        result = svc.duplicate_slide("pres123", "slide1")
        assert result["new_slide_id"] == "slide1_copy"
        assert result["original_slide_id"] == "slide1"

    def test_duplicates_with_position(self):
        svc, mock_slides, _ = _make_service()
        mock_slides.presentations().batchUpdate().execute.side_effect = [
            {"replies": [{"duplicateObject": {"objectId": "s1_copy"}}]},
            {},
        ]
        result = svc.duplicate_slide("pres123", "s1", position=0)
        assert result["new_slide_id"] == "s1_copy"


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

    def test_failure_after_creation_includes_id(self):
        svc, mock_slides, mock_drive = _make_service()

        mock_drive.files().create().execute.return_value = {
            "id": "orphan_id",
            "name": "Orphan",
        }

        mock_slides.presentations().get().execute.side_effect = Exception("API down")

        with pytest.raises(ValueError, match="orphan_id"):
            svc.convert_markdown_to_slides(
                "Orphan", [{"title": "X", "body_text": "Y", "speaker_notes": ""}]
            )


class TestReadShapeStyle:
    def test_extracts_style_from_first_text_run(self):
        svc, mock_slides, _ = _make_service()
        mock_slides.presentations().get().execute.return_value = {
            "slides": [
                {
                    "objectId": "s1",
                    "pageElements": [
                        {
                            "objectId": "sh1",
                            "shape": {
                                "text": {
                                    "textElements": [
                                        {
                                            "textRun": {
                                                "content": "Hello",
                                                "style": {
                                                    "fontFamily": "Roboto",
                                                    "fontSize": {
                                                        "magnitude": 14,
                                                        "unit": "PT",
                                                    },
                                                    "bold": False,
                                                    "link": {
                                                        "url": "https://example.com"
                                                    },
                                                },
                                            }
                                        }
                                    ]
                                }
                            },
                        }
                    ],
                }
            ]
        }
        style = svc._read_shape_style("pres1", "s1", "sh1")
        assert style["fontFamily"] == "Roboto"
        assert style["fontSize"] == {"magnitude": 14, "unit": "PT"}
        assert style["bold"] is False
        assert "link" not in style

    def test_returns_empty_for_missing_shape(self):
        svc, mock_slides, _ = _make_service()
        mock_slides.presentations().get().execute.return_value = {
            "slides": [
                {
                    "objectId": "s1",
                    "pageElements": [],
                }
            ]
        }
        assert svc._read_shape_style("pres1", "s1", "missing") == {}

    def test_returns_empty_for_no_text_runs(self):
        svc, mock_slides, _ = _make_service()
        mock_slides.presentations().get().execute.return_value = {
            "slides": [
                {
                    "objectId": "s1",
                    "pageElements": [
                        {
                            "objectId": "sh1",
                            "shape": {
                                "text": {"textElements": [{"paragraphMarker": {}}]}
                            },
                        }
                    ],
                }
            ]
        }
        assert svc._read_shape_style("pres1", "s1", "sh1") == {}

    def test_returns_empty_for_missing_slide(self):
        svc, mock_slides, _ = _make_service()
        mock_slides.presentations().get().execute.return_value = {"slides": []}
        assert svc._read_shape_style("pres1", "missing", "sh1") == {}


class TestExtractText:
    def test_empty_text_obj(self):
        assert GoogleSlidesService._extract_text({}) == ""

    def test_no_text_runs(self):
        assert (
            GoogleSlidesService._extract_text(
                {"textElements": [{"paragraphMarker": {}}]}
            )
            == ""
        )

    def test_multiple_runs(self):
        text_obj = {
            "textElements": [
                {"textRun": {"content": "Hello "}},
                {"textRun": {"content": "World"}},
            ]
        }
        assert GoogleSlidesService._extract_text(text_obj) == "Hello World"

    def test_strips_only_trailing_newline(self):
        text_obj = {
            "textElements": [
                {"textRun": {"content": "Line 1\nLine 2\n"}},
            ]
        }
        assert GoogleSlidesService._extract_text(text_obj) == "Line 1\nLine 2"

    def test_preserves_internal_whitespace(self):
        text_obj = {
            "textElements": [
                {"textRun": {"content": "  spaced  "}},
            ]
        }
        assert GoogleSlidesService._extract_text(text_obj) == "  spaced  "


class TestGetElementType:
    def test_shape(self):
        assert GoogleSlidesService._get_element_type({"shape": {}}) == "SHAPE"

    def test_image(self):
        assert GoogleSlidesService._get_element_type({"image": {}}) == "IMAGE"

    def test_table(self):
        assert GoogleSlidesService._get_element_type({"table": {}}) == "TABLE"

    def test_line(self):
        assert GoogleSlidesService._get_element_type({"line": {}}) == "LINE"

    def test_video(self):
        assert GoogleSlidesService._get_element_type({"video": {}}) == "VIDEO"

    def test_unknown(self):
        assert GoogleSlidesService._get_element_type({}) == "UNKNOWN"


class TestGetLayoutName:
    def test_no_slide_properties(self):
        assert GoogleSlidesService._get_layout_name({}) == ""

    def test_with_layout_map(self):
        slide = {"slideProperties": {"layoutObjectId": "layout_abc"}}
        layout_map = {"layout_abc": "Title Slide"}
        assert GoogleSlidesService._get_layout_name(slide, layout_map) == "Title Slide"

    def test_fallback_to_id_without_map(self):
        slide = {"slideProperties": {"layoutObjectId": "layout_abc"}}
        assert GoogleSlidesService._get_layout_name(slide) == "layout_abc"


class TestReorderSlides:
    def test_reorders_slides(self):
        svc, mock_slides, _ = _make_service()
        mock_slides.presentations().batchUpdate().execute.return_value = {}
        result = svc.reorder_slides("pres123", ["slide2", "slide1"], 0)
        assert result["status"] == "reordered"
        assert result["new_position"] == 0
