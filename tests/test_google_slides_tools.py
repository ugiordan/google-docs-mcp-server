"""Tests for Google Slides MCP tools."""

import json
from unittest.mock import MagicMock, patch

from googleapiclient.errors import HttpError

from mcp_server.tools.google_slides_tools import (
    _add_slide,
    _convert_markdown_to_slides,
    _create_presentation,
    _delete_slide,
    _duplicate_slide,
    _error_response,
    _handle_api_error,
    _list_presentations,
    _read_presentation,
    _reorder_slides,
    _tag_untrusted,
    _update_slide_text,
    _update_speaker_notes,
)


def _mock_service():
    return MagicMock()


class TestListPresentations:
    def test_success(self):
        svc = _mock_service()
        svc.list_presentations.return_value = [
            {"id": "p1", "name": "Test", "modified_time": "", "url": "..."}
        ]
        result = json.loads(_list_presentations(svc))
        assert len(result) == 1
        assert "untrusted-data" in result[0]["name"]

    def test_invalid_max_results(self):
        svc = _mock_service()
        result = json.loads(_list_presentations(svc, max_results=0))
        assert result["code"] == "VALIDATION_ERROR"

    def test_max_results_too_high(self):
        svc = _mock_service()
        result = json.loads(_list_presentations(svc, max_results=101))
        assert result["code"] == "VALIDATION_ERROR"


class TestReadPresentation:
    def test_success(self):
        svc = _mock_service()
        svc.read_presentation.return_value = {
            "id": "pres1",
            "title": "Test Pres",
            "slide_count": 1,
            "slides": [
                {
                    "slide_number": 1,
                    "slide_id": "s1",
                    "layout": "TITLE",
                    "shapes": [
                        {"shape_id": "sh1", "type": "TITLE", "text": "Hello"}
                    ],
                    "speaker_notes": "My notes",
                }
            ],
        }
        result = json.loads(_read_presentation(svc, "pres1234567"))
        assert result["id"] == "pres1"
        assert "presentation-content" in result["content"]
        assert "slide-content" in result["content"]

    def test_invalid_id(self):
        svc = _mock_service()
        result = json.loads(_read_presentation(svc, "bad"))
        assert result["code"] == "VALIDATION_ERROR"


class TestCreatePresentation:
    def test_success(self):
        svc = _mock_service()
        svc.create_presentation.return_value = {
            "id": "new1",
            "name": "My Pres",
            "url": "https://...",
        }
        result = json.loads(_create_presentation(svc, "My Pres"))
        assert result["id"] == "new1"
        assert "untrusted-data" in result["name"]

    def test_empty_title(self):
        svc = _mock_service()
        result = json.loads(_create_presentation(svc, ""))
        assert result["code"] == "VALIDATION_ERROR"


class TestAddSlide:
    def test_success(self):
        svc = _mock_service()
        svc.add_slide.return_value = {
            "presentation_id": "pres1234567",
            "slide_id": "newslide",
        }
        result = json.loads(_add_slide(svc, "pres1234567"))
        assert result["slide_id"] == "newslide"

    def test_with_position(self):
        svc = _mock_service()
        svc.add_slide.return_value = {
            "presentation_id": "pres1234567",
            "slide_id": "s1",
        }
        result = json.loads(_add_slide(svc, "pres1234567", position=2))
        assert result["slide_id"] == "s1"


class TestDeleteSlide:
    def test_success(self):
        svc = _mock_service()
        svc.delete_slide.return_value = {
            "presentation_id": "pres1234567",
            "slide_id": "s1",
            "status": "deleted",
        }
        result = json.loads(_delete_slide(svc, "pres1234567", "s1"))
        assert result["status"] == "deleted"

    def test_invalid_presentation_id(self):
        svc = _mock_service()
        result = json.loads(_delete_slide(svc, "bad", "s1"))
        assert result["code"] == "VALIDATION_ERROR"


class TestUpdateSlideText:
    def test_success(self):
        svc = _mock_service()
        svc.update_slide_text.return_value = {
            "presentation_id": "pres1234567",
            "slide_id": "s1",
            "shape_id": "sh1",
            "status": "updated",
        }
        result = json.loads(
            _update_slide_text(svc, "pres1234567", "s1", "sh1", "New text")
        )
        assert result["status"] == "updated"

    def test_invalid_shape_id(self):
        svc = _mock_service()
        result = json.loads(
            _update_slide_text(svc, "pres1234567", "s1", "", "text")
        )
        assert result["code"] == "VALIDATION_ERROR"


class TestUpdateSpeakerNotes:
    def test_success(self):
        svc = _mock_service()
        svc.update_speaker_notes.return_value = {
            "presentation_id": "pres1234567",
            "slide_id": "s1",
            "status": "updated",
        }
        result = json.loads(
            _update_speaker_notes(svc, "pres1234567", "s1", "My notes")
        )
        assert result["status"] == "updated"


class TestDuplicateSlide:
    def test_success(self):
        svc = _mock_service()
        svc.duplicate_slide.return_value = {
            "presentation_id": "pres1234567",
            "original_slide_id": "s1",
            "new_slide_id": "s1_copy",
        }
        result = json.loads(_duplicate_slide(svc, "pres1234567", "s1"))
        assert result["new_slide_id"] == "s1_copy"


class TestReorderSlides:
    def test_success(self):
        svc = _mock_service()
        svc.reorder_slides.return_value = {
            "presentation_id": "pres1234567",
            "slide_ids": ["s2", "s1"],
            "new_position": 0,
            "status": "reordered",
        }
        result = json.loads(_reorder_slides(svc, "pres1234567", "s2,s1", 0))
        assert result["status"] == "reordered"

    def test_empty_slide_ids(self):
        svc = _mock_service()
        result = json.loads(_reorder_slides(svc, "pres1234567", "", 0))
        assert result["code"] == "VALIDATION_ERROR"

    def test_negative_position(self):
        svc = _mock_service()
        result = json.loads(_reorder_slides(svc, "pres1234567", "s1", -1))
        assert result["code"] == "VALIDATION_ERROR"


class TestConvertMarkdownToSlides:
    def test_success(self):
        svc = _mock_service()
        svc.convert_markdown_to_slides.return_value = {
            "id": "pres1",
            "name": "My Pres",
            "url": "https://...",
            "slide_count": 2,
        }
        md = "# Slide 1\nContent\n---\n# Slide 2\nMore"
        result = json.loads(_convert_markdown_to_slides(svc, md, "My Pres"))
        assert result["id"] == "pres1"
        assert result["slide_count"] == 2

    def test_empty_markdown(self):
        svc = _mock_service()
        result = json.loads(_convert_markdown_to_slides(svc, "", "Title"))
        assert result["code"] == "VALIDATION_ERROR"

    def test_empty_title(self):
        svc = _mock_service()
        result = json.loads(
            _convert_markdown_to_slides(svc, "# Content", "")
        )
        assert result["code"] == "VALIDATION_ERROR"


class TestTagUntrusted:
    def test_wraps_data(self):
        result = _tag_untrusted("hello")
        assert "hello" in result
        assert result.startswith("<untrusted-data-")
        assert result.endswith(result.split(">")[0].replace("<", "") + ">")

    def test_different_boundaries(self):
        r1 = _tag_untrusted("a")
        r2 = _tag_untrusted("a")
        boundary1 = r1.split("-")[2].split(">")[0]
        boundary2 = r2.split("-")[2].split(">")[0]
        assert boundary1 != boundary2

    def test_empty_string(self):
        result = _tag_untrusted("")
        assert "<untrusted-data-" in result


class TestErrorResponse:
    def test_format(self):
        result = json.loads(_error_response("bad input", "VALIDATION_ERROR"))
        assert result["error"] == "bad input"
        assert result["code"] == "VALIDATION_ERROR"


class TestHandleApiError:
    def test_401_returns_reauth(self):
        resp = MagicMock()
        resp.status = 401
        error = HttpError(resp, b"unauthorized")
        result = json.loads(_handle_api_error(error, "test_op"))
        assert result["code"] == "REAUTH_REQUIRED"

    def test_non_401_http_error(self):
        resp = MagicMock()
        resp.status = 500
        error = HttpError(resp, b"server error")
        result = json.loads(_handle_api_error(error, "test_op"))
        assert result["code"] == "API_ERROR"

    def test_non_http_error(self):
        error = RuntimeError("something broke")
        result = json.loads(_handle_api_error(error, "test_op"))
        assert result["code"] == "API_ERROR"


class TestToolsApiErrorPaths:
    def _http_error(self, status=500):
        resp = MagicMock()
        resp.status = status
        return HttpError(resp, b"error")

    def test_list_presentations_api_error(self):
        svc = _mock_service()
        svc.list_presentations.side_effect = self._http_error()
        result = json.loads(_list_presentations(svc))
        assert result["code"] == "API_ERROR"

    def test_list_presentations_401(self):
        svc = _mock_service()
        svc.list_presentations.side_effect = self._http_error(401)
        result = json.loads(_list_presentations(svc))
        assert result["code"] == "REAUTH_REQUIRED"

    def test_read_presentation_api_error(self):
        svc = _mock_service()
        svc.read_presentation.side_effect = self._http_error()
        result = json.loads(_read_presentation(svc, "pres1234567"))
        assert result["code"] == "API_ERROR"

    def test_create_presentation_api_error(self):
        svc = _mock_service()
        svc.create_presentation.side_effect = self._http_error()
        result = json.loads(_create_presentation(svc, "Test Pres"))
        assert result["code"] == "API_ERROR"

    def test_add_slide_api_error(self):
        svc = _mock_service()
        svc.add_slide.side_effect = self._http_error()
        result = json.loads(_add_slide(svc, "pres1234567"))
        assert result["code"] == "API_ERROR"

    def test_delete_slide_api_error(self):
        svc = _mock_service()
        svc.delete_slide.side_effect = self._http_error()
        result = json.loads(_delete_slide(svc, "pres1234567", "s1"))
        assert result["code"] == "API_ERROR"

    def test_update_slide_text_api_error(self):
        svc = _mock_service()
        svc.update_slide_text.side_effect = self._http_error()
        result = json.loads(
            _update_slide_text(svc, "pres1234567", "s1", "sh1", "text")
        )
        assert result["code"] == "API_ERROR"

    def test_update_speaker_notes_api_error(self):
        svc = _mock_service()
        svc.update_speaker_notes.side_effect = self._http_error()
        result = json.loads(
            _update_speaker_notes(svc, "pres1234567", "s1", "notes")
        )
        assert result["code"] == "API_ERROR"

    def test_duplicate_slide_api_error(self):
        svc = _mock_service()
        svc.duplicate_slide.side_effect = self._http_error()
        result = json.loads(_duplicate_slide(svc, "pres1234567", "s1"))
        assert result["code"] == "API_ERROR"

    def test_reorder_slides_api_error(self):
        svc = _mock_service()
        svc.reorder_slides.side_effect = self._http_error()
        result = json.loads(_reorder_slides(svc, "pres1234567", "s1,s2", 0))
        assert result["code"] == "API_ERROR"

    def test_convert_markdown_api_error(self):
        svc = _mock_service()
        svc.convert_markdown_to_slides.side_effect = self._http_error()
        result = json.loads(
            _convert_markdown_to_slides(svc, "# Slide\nContent", "Title")
        )
        assert result["code"] == "API_ERROR"

    def test_update_speaker_notes_value_error(self):
        svc = _mock_service()
        svc.update_speaker_notes.side_effect = ValueError("no notes shape")
        result = json.loads(
            _update_speaker_notes(svc, "pres1234567", "s1", "notes")
        )
        assert result["code"] == "VALIDATION_ERROR"


class TestReadPresentationWrapping:
    def test_wraps_content_with_boundaries(self):
        svc = _mock_service()
        svc.read_presentation.return_value = {
            "id": "pres1",
            "title": "Test",
            "slide_count": 1,
            "slides": [
                {
                    "slide_number": 1,
                    "slide_id": "s1",
                    "layout": "TITLE",
                    "shapes": [],
                    "speaker_notes": "",
                }
            ],
        }
        result = json.loads(_read_presentation(svc, "pres1234567"))
        assert "presentation-content" in result["content"]
        assert "slide-content" in result["content"]
        assert "slides" not in result

    def test_no_slides_still_wraps(self):
        svc = _mock_service()
        svc.read_presentation.return_value = {
            "id": "pres1",
            "title": "Empty",
            "slide_count": 0,
            "slides": [],
        }
        result = json.loads(_read_presentation(svc, "pres1234567"))
        assert "presentation-content" in result["content"]
        assert "untrusted-data" in result["title"]


class TestAddSlidePositionHandling:
    def test_negative_position_treated_as_none(self):
        svc = _mock_service()
        svc.add_slide.return_value = {
            "presentation_id": "pres1234567",
            "slide_id": "s1",
        }
        _add_slide(svc, "pres1234567", position=-1)
        svc.add_slide.assert_called_with("pres1234567", position=None, layout=None)

    def test_zero_position_passed_through(self):
        svc = _mock_service()
        svc.add_slide.return_value = {
            "presentation_id": "pres1234567",
            "slide_id": "s1",
        }
        _add_slide(svc, "pres1234567", position=0)
        svc.add_slide.assert_called_with("pres1234567", position=0, layout=None)


class TestReorderSlidesEdgeCases:
    def test_whitespace_in_slide_ids(self):
        svc = _mock_service()
        svc.reorder_slides.return_value = {
            "presentation_id": "pres1234567",
            "slide_ids": ["s1", "s2"],
            "new_position": 0,
            "status": "reordered",
        }
        result = json.loads(_reorder_slides(svc, "pres1234567", " s1 , s2 ", 0))
        assert result["status"] == "reordered"

    def test_trailing_comma(self):
        svc = _mock_service()
        svc.reorder_slides.return_value = {
            "presentation_id": "pres1234567",
            "slide_ids": ["s1"],
            "new_position": 0,
            "status": "reordered",
        }
        result = json.loads(_reorder_slides(svc, "pres1234567", "s1,", 0))
        assert result["status"] == "reordered"
