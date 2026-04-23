"""Tests for Google Slides MCP tools."""

import json
from unittest.mock import MagicMock

from googleapiclient.errors import HttpError

from mcp_server.config import SlidesTemplate, SlidesTemplateConfig
from mcp_server.nonce import NonceManager
from mcp_server.tools.common import error_response, handle_api_error, tag_untrusted
from mcp_server.tools.google_slides_tools import (
    _add_slide,
    _convert_markdown_to_slides,
    _create_presentation,
    _delete_shape,
    _delete_slide,
    _delete_slides,
    _duplicate_slide,
    _list_presentations,
    _read_presentation,
    _reorder_slides,
    _update_slide_text,
    _update_speaker_notes,
    _update_text_style,
)


def _mock_service():
    return MagicMock()


def _nonce_manager():
    return NonceManager(ttl_seconds=30)


def _empty_slides_config():
    return SlidesTemplateConfig(templates=[])


def _slides_config_with_default():
    return SlidesTemplateConfig(
        templates=[
            SlidesTemplate(
                name="corporate",
                presentation_id="tmpl_pres_id_1234567890",
                default=True,
            ),
            SlidesTemplate(
                name="minimal",
                presentation_id="tmpl_pres_id_0987654321",
            ),
        ]
    )


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

    def test_with_query(self):
        svc = _mock_service()
        svc.list_presentations.return_value = [
            {"id": "p1", "name": "Match", "modified_time": "", "url": "..."}
        ]
        result = json.loads(_list_presentations(svc, query="Match"))
        assert len(result) == 1


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
                    "elements": [
                        {"element_id": "sh1", "type": "TITLE", "text": "Hello"}
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
                    "elements": [],
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


class TestCreatePresentation:
    def test_success(self):
        svc = _mock_service()
        svc.create_presentation.return_value = {
            "id": "new1",
            "name": "My Pres",
            "url": "https://...",
        }
        result = json.loads(
            _create_presentation(svc, _empty_slides_config(), "My Pres")
        )
        assert result["id"] == "new1"
        assert "untrusted-data" in result["name"]

    def test_empty_title(self):
        svc = _mock_service()
        result = json.loads(_create_presentation(svc, _empty_slides_config(), ""))
        assert result["code"] == "VALIDATION_ERROR"

    def test_uses_default_template(self):
        svc = _mock_service()
        svc.create_presentation.return_value = {
            "id": "new1",
            "name": "My Pres",
            "url": "https://...",
        }
        cfg = _slides_config_with_default()
        _create_presentation(svc, cfg, "My Pres")
        svc.create_presentation.assert_called_with(
            "My Pres",
            folder_id=None,
            template_presentation_id="tmpl_pres_id_1234567890",
        )

    def test_uses_named_template(self):
        svc = _mock_service()
        svc.create_presentation.return_value = {
            "id": "new1",
            "name": "My Pres",
            "url": "https://...",
        }
        cfg = _slides_config_with_default()
        _create_presentation(svc, cfg, "My Pres", template_name="minimal")
        svc.create_presentation.assert_called_with(
            "My Pres",
            folder_id=None,
            template_presentation_id="tmpl_pres_id_0987654321",
        )

    def test_unknown_template_rejected(self):
        svc = _mock_service()
        cfg = _slides_config_with_default()
        result = json.loads(
            _create_presentation(svc, cfg, "My Pres", template_name="unknown")
        )
        assert result["code"] == "VALIDATION_ERROR"

    def test_no_template_no_config(self):
        svc = _mock_service()
        svc.create_presentation.return_value = {
            "id": "new1",
            "name": "My Pres",
            "url": "https://...",
        }
        _create_presentation(svc, _empty_slides_config(), "My Pres")
        svc.create_presentation.assert_called_with(
            "My Pres", folder_id=None, template_presentation_id=None
        )


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

    def test_custom_layout_name_passed_through(self):
        svc = _mock_service()
        svc.add_slide.return_value = {
            "presentation_id": "pres1234567",
            "slide_id": "s1",
        }
        result = json.loads(
            _add_slide(svc, "pres1234567", layout="Interior title and two column body")
        )
        assert result["slide_id"] == "s1"
        svc.add_slide.assert_called_with(
            "pres1234567",
            position=None,
            layout="Interior title and two column body",
        )

    def test_predefined_layout_passed_through(self):
        svc = _mock_service()
        svc.add_slide.return_value = {
            "presentation_id": "pres1234567",
            "slide_id": "s1",
        }
        result = json.loads(_add_slide(svc, "pres1234567", layout="BLANK"))
        assert result["slide_id"] == "s1"
        svc.add_slide.assert_called_with("pres1234567", position=None, layout="BLANK")

    def test_layout_name_too_long(self):
        svc = _mock_service()
        result = json.loads(_add_slide(svc, "pres1234567", layout="x" * 256))
        assert result["code"] == "VALIDATION_ERROR"

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


class TestDeleteSlide:
    def test_nonce_required(self):
        svc = _mock_service()
        nm = _nonce_manager()
        result = json.loads(_delete_slide(svc, nm, "pres1234567", "s1"))
        assert result["status"] == "confirm_required"
        assert "nonce" in result

    def test_nonce_confirmation(self):
        svc = _mock_service()
        nm = _nonce_manager()
        svc.delete_slide.return_value = {
            "presentation_id": "pres1234567",
            "slide_id": "s1",
            "status": "deleted",
        }
        r1 = json.loads(_delete_slide(svc, nm, "pres1234567", "s1"))
        nonce = r1["nonce"]
        r2 = json.loads(_delete_slide(svc, nm, "pres1234567", "s1", nonce))
        assert r2["status"] == "deleted"

    def test_invalid_nonce(self):
        svc = _mock_service()
        nm = _nonce_manager()
        result = json.loads(_delete_slide(svc, nm, "pres1234567", "s1", "bad_nonce"))
        assert result["code"] == "NONCE_ERROR"

    def test_invalid_presentation_id(self):
        svc = _mock_service()
        nm = _nonce_manager()
        result = json.loads(_delete_slide(svc, nm, "bad", "s1"))
        assert result["code"] == "VALIDATION_ERROR"


class TestDeleteSlides:
    def test_nonce_required(self):
        svc = _mock_service()
        nm = _nonce_manager()
        result = json.loads(_delete_slides(svc, nm, "pres1234567", "s1,s2,s3"))
        assert result["status"] == "confirm_required"
        assert result["slide_count"] == 3
        assert result["slide_ids"] == ["s1", "s2", "s3"]
        assert "nonce" in result

    def test_nonce_confirmation(self):
        svc = _mock_service()
        nm = _nonce_manager()
        svc.delete_slides.return_value = {
            "presentation_id": "pres1234567",
            "slide_ids": ["s1", "s2"],
            "deleted_count": 2,
            "status": "deleted",
        }
        r1 = json.loads(_delete_slides(svc, nm, "pres1234567", "s1,s2"))
        nonce = r1["nonce"]
        r2 = json.loads(_delete_slides(svc, nm, "pres1234567", "s1,s2", nonce))
        assert r2["status"] == "deleted"
        assert r2["deleted_count"] == 2

    def test_invalid_nonce(self):
        svc = _mock_service()
        nm = _nonce_manager()
        result = json.loads(
            _delete_slides(svc, nm, "pres1234567", "s1,s2", "bad_nonce")
        )
        assert result["code"] == "NONCE_ERROR"

    def test_nonce_is_order_independent(self):
        svc = _mock_service()
        nm = _nonce_manager()
        svc.delete_slides.return_value = {
            "presentation_id": "pres1234567",
            "slide_ids": ["s2", "s1"],
            "deleted_count": 2,
            "status": "deleted",
        }
        r1 = json.loads(_delete_slides(svc, nm, "pres1234567", "s2,s1"))
        nonce = r1["nonce"]
        r2 = json.loads(_delete_slides(svc, nm, "pres1234567", "s1,s2", nonce))
        assert r2["status"] == "deleted"

    def test_empty_slide_ids(self):
        svc = _mock_service()
        nm = _nonce_manager()
        result = json.loads(_delete_slides(svc, nm, "pres1234567", ""))
        assert result["code"] == "VALIDATION_ERROR"
        assert "empty" in result["error"]

    def test_too_many_slides(self):
        svc = _mock_service()
        nm = _nonce_manager()
        ids = ",".join(f"s{i}" for i in range(51))
        result = json.loads(_delete_slides(svc, nm, "pres1234567", ids))
        assert result["code"] == "VALIDATION_ERROR"
        assert "50" in result["error"]

    def test_trailing_comma_ignored(self):
        svc = _mock_service()
        nm = _nonce_manager()
        result = json.loads(_delete_slides(svc, nm, "pres1234567", "s1,"))
        assert result["status"] == "confirm_required"
        assert result["slide_ids"] == ["s1"]

    def test_invalid_presentation_id(self):
        svc = _mock_service()
        nm = _nonce_manager()
        result = json.loads(_delete_slides(svc, nm, "bad", "s1,s2"))
        assert result["code"] == "VALIDATION_ERROR"

    def test_single_slide(self):
        svc = _mock_service()
        nm = _nonce_manager()
        result = json.loads(_delete_slides(svc, nm, "pres1234567", "s1"))
        assert result["status"] == "confirm_required"
        assert result["slide_count"] == 1

    def test_api_error(self):
        svc = _mock_service()
        nm = _nonce_manager()
        svc.delete_slides.side_effect = Exception("API failure")
        r1 = json.loads(_delete_slides(svc, nm, "pres1234567", "s1,s2"))
        nonce = r1["nonce"]
        r2 = json.loads(_delete_slides(svc, nm, "pres1234567", "s1,s2", nonce))
        assert r2["code"] == "API_ERROR"

    def test_whitespace_in_ids_stripped(self):
        svc = _mock_service()
        nm = _nonce_manager()
        result = json.loads(_delete_slides(svc, nm, "pres1234567", " s1 , s2 , s3 "))
        assert result["slide_ids"] == ["s1", "s2", "s3"]
        assert result["slide_count"] == 3


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
        result = json.loads(_update_slide_text(svc, "pres1234567", "s1", "", "text"))
        assert result["code"] == "VALIDATION_ERROR"


class TestDeleteShape:
    def test_nonce_required(self):
        svc = _mock_service()
        nm = _nonce_manager()
        result = json.loads(_delete_shape(svc, nm, "pres1234567", "img1"))
        assert result["status"] == "confirm_required"
        assert "nonce" in result

    def test_nonce_confirmation(self):
        svc = _mock_service()
        nm = _nonce_manager()
        svc.delete_shape.return_value = {
            "presentation_id": "pres1234567",
            "shape_id": "img1",
            "status": "deleted",
        }
        r1 = json.loads(_delete_shape(svc, nm, "pres1234567", "img1"))
        nonce = r1["nonce"]
        r2 = json.loads(_delete_shape(svc, nm, "pres1234567", "img1", nonce))
        assert r2["status"] == "deleted"

    def test_invalid_nonce(self):
        svc = _mock_service()
        nm = _nonce_manager()
        result = json.loads(_delete_shape(svc, nm, "pres1234567", "img1", "bad_nonce"))
        assert result["code"] == "NONCE_ERROR"

    def test_invalid_presentation_id(self):
        svc = _mock_service()
        nm = _nonce_manager()
        result = json.loads(_delete_shape(svc, nm, "bad", "img1"))
        assert result["code"] == "VALIDATION_ERROR"

    def test_invalid_shape_id(self):
        svc = _mock_service()
        nm = _nonce_manager()
        result = json.loads(_delete_shape(svc, nm, "pres1234567", ""))
        assert result["code"] == "VALIDATION_ERROR"

    def test_api_error(self):
        svc = _mock_service()
        nm = _nonce_manager()
        r1 = json.loads(_delete_shape(svc, nm, "pres1234567", "img1"))
        nonce = r1["nonce"]
        resp = MagicMock()
        resp.status = 500
        svc.delete_shape.side_effect = HttpError(resp, b"error")
        result = json.loads(_delete_shape(svc, nm, "pres1234567", "img1", nonce))
        assert result["code"] == "API_ERROR"


class TestUpdateSpeakerNotes:
    def test_success(self):
        svc = _mock_service()
        svc.update_speaker_notes.return_value = {
            "presentation_id": "pres1234567",
            "slide_id": "s1",
            "status": "updated",
        }
        result = json.loads(_update_speaker_notes(svc, "pres1234567", "s1", "My notes"))
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

    def test_invalid_slide_id_in_list(self):
        svc = _mock_service()
        result = json.loads(_reorder_slides(svc, "pres1234567", "s1,bad id,s2", 0))
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
        result = json.loads(
            _convert_markdown_to_slides(svc, _empty_slides_config(), md, "My Pres")
        )
        assert result["id"] == "pres1"
        assert result["slide_count"] == 2

    def test_empty_markdown(self):
        svc = _mock_service()
        result = json.loads(
            _convert_markdown_to_slides(svc, _empty_slides_config(), "", "Title")
        )
        assert result["code"] == "VALIDATION_ERROR"

    def test_empty_title(self):
        svc = _mock_service()
        result = json.loads(
            _convert_markdown_to_slides(svc, _empty_slides_config(), "# Content", "")
        )
        assert result["code"] == "VALIDATION_ERROR"

    def test_uses_default_template(self):
        svc = _mock_service()
        svc.convert_markdown_to_slides.return_value = {
            "id": "pres1",
            "name": "My Pres",
            "url": "https://...",
            "slide_count": 1,
        }
        cfg = _slides_config_with_default()
        _convert_markdown_to_slides(svc, cfg, "# Slide\nContent", "My Pres")
        call_kwargs = svc.convert_markdown_to_slides.call_args
        assert call_kwargs[1]["template_presentation_id"] == "tmpl_pres_id_1234567890"

    def test_uses_named_template(self):
        svc = _mock_service()
        svc.convert_markdown_to_slides.return_value = {
            "id": "pres1",
            "name": "My Pres",
            "url": "https://...",
            "slide_count": 1,
        }
        cfg = _slides_config_with_default()
        _convert_markdown_to_slides(
            svc, cfg, "# Slide\nContent", "My Pres", template_name="minimal"
        )
        call_kwargs = svc.convert_markdown_to_slides.call_args
        assert call_kwargs[1]["template_presentation_id"] == "tmpl_pres_id_0987654321"


class TestTagUntrusted:
    def test_wraps_data(self):
        result = tag_untrusted("hello")
        assert "hello" in result
        assert result.startswith("<untrusted-data-")

    def test_different_boundaries(self):
        r1 = tag_untrusted("a")
        r2 = tag_untrusted("a")
        b1 = r1.split(">")[0].split("-")[-1]
        b2 = r2.split(">")[0].split("-")[-1]
        assert b1 != b2

    def test_empty_string(self):
        result = tag_untrusted("")
        assert "<untrusted-data-" in result


class TestErrorResponse:
    def test_format(self):
        result = json.loads(error_response("bad input", "VALIDATION_ERROR"))
        assert result["error"] == "bad input"
        assert result["code"] == "VALIDATION_ERROR"


class TestHandleApiError:
    def test_401_returns_reauth(self):
        resp = MagicMock()
        resp.status = 401
        error = HttpError(resp, b"unauthorized")
        result = json.loads(handle_api_error(error, "test_op"))
        assert result["code"] == "REAUTH_REQUIRED"

    def test_non_401_http_error(self):
        resp = MagicMock()
        resp.status = 500
        error = HttpError(resp, b"server error")
        result = json.loads(handle_api_error(error, "test_op"))
        assert result["code"] == "API_ERROR"

    def test_non_http_error(self):
        error = RuntimeError("something broke")
        result = json.loads(handle_api_error(error, "test_op"))
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
        result = json.loads(
            _create_presentation(svc, _empty_slides_config(), "Test Pres")
        )
        assert result["code"] == "API_ERROR"

    def test_add_slide_api_error(self):
        svc = _mock_service()
        svc.add_slide.side_effect = self._http_error()
        result = json.loads(_add_slide(svc, "pres1234567"))
        assert result["code"] == "API_ERROR"

    def test_delete_slide_api_error(self):
        svc = _mock_service()
        nm = _nonce_manager()
        r1 = json.loads(_delete_slide(svc, nm, "pres1234567", "s1"))
        nonce = r1["nonce"]
        svc.delete_slide.side_effect = self._http_error()
        result = json.loads(_delete_slide(svc, nm, "pres1234567", "s1", nonce))
        assert result["code"] == "API_ERROR"

    def test_update_slide_text_api_error(self):
        svc = _mock_service()
        svc.update_slide_text.side_effect = self._http_error()
        result = json.loads(_update_slide_text(svc, "pres1234567", "s1", "sh1", "text"))
        assert result["code"] == "API_ERROR"

    def test_update_speaker_notes_api_error(self):
        svc = _mock_service()
        svc.update_speaker_notes.side_effect = self._http_error()
        result = json.loads(_update_speaker_notes(svc, "pres1234567", "s1", "notes"))
        assert result["code"] == "API_ERROR"

    def test_update_speaker_notes_value_error(self):
        svc = _mock_service()
        svc.update_speaker_notes.side_effect = ValueError("no notes shape")
        result = json.loads(_update_speaker_notes(svc, "pres1234567", "s1", "notes"))
        assert result["code"] == "VALIDATION_ERROR"

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
            _convert_markdown_to_slides(
                svc, _empty_slides_config(), "# Slide\nContent", "Title"
            )
        )
        assert result["code"] == "API_ERROR"


class TestUpdateTextStyle:
    def test_bold_and_font_size(self):
        svc = _mock_service()
        svc.update_text_style.return_value = {
            "presentation_id": "pres1234567",
            "shape_id": "shape_abc",
            "status": "styled",
        }
        result = json.loads(
            _update_text_style(
                svc, "pres1234567", "shape_abc", bold="true", font_size=14.0
            )
        )
        assert result["status"] == "styled"
        svc.update_text_style.assert_called_once_with(
            "pres1234567", "shape_abc", bold=True, font_size=14.0
        )

    def test_all_properties(self):
        svc = _mock_service()
        svc.update_text_style.return_value = {
            "presentation_id": "pres1234567",
            "shape_id": "shape_abc",
            "status": "styled",
        }
        result = json.loads(
            _update_text_style(
                svc,
                "pres1234567",
                "shape_abc",
                bold="true",
                italic="false",
                underline="true",
                font_family="Arial",
                font_size=18.0,
                foreground_color="#FF0000",
                alignment="CENTER",
            )
        )
        assert result["status"] == "styled"
        svc.update_text_style.assert_called_once_with(
            "pres1234567",
            "shape_abc",
            bold=True,
            italic=False,
            underline=True,
            font_family="Arial",
            font_size=18.0,
            foreground_color_rgb="#FF0000",
            alignment="CENTER",
        )

    def test_no_properties_returns_error(self):
        svc = _mock_service()
        result = json.loads(_update_text_style(svc, "pres1234567", "shape_abc"))
        assert result["code"] == "VALIDATION_ERROR"
        assert "At least one" in result["error"]

    def test_invalid_bold_value(self):
        svc = _mock_service()
        result = json.loads(
            _update_text_style(svc, "pres1234567", "shape_abc", bold="yes")
        )
        assert result["code"] == "VALIDATION_ERROR"
        assert "bold" in result["error"]

    def test_invalid_italic_value(self):
        svc = _mock_service()
        result = json.loads(
            _update_text_style(svc, "pres1234567", "shape_abc", italic="maybe")
        )
        assert result["code"] == "VALIDATION_ERROR"

    def test_invalid_underline_value(self):
        svc = _mock_service()
        result = json.loads(
            _update_text_style(svc, "pres1234567", "shape_abc", underline="1")
        )
        assert result["code"] == "VALIDATION_ERROR"

    def test_invalid_alignment(self):
        svc = _mock_service()
        result = json.loads(
            _update_text_style(svc, "pres1234567", "shape_abc", alignment="LEFT")
        )
        assert result["code"] == "VALIDATION_ERROR"
        assert "alignment" in result["error"]

    def test_valid_alignments(self):
        for align in ("START", "CENTER", "END", "JUSTIFIED"):
            svc = _mock_service()
            svc.update_text_style.return_value = {
                "presentation_id": "pres1234567",
                "shape_id": "s1",
                "status": "styled",
            }
            result = json.loads(
                _update_text_style(svc, "pres1234567", "s1", alignment=align)
            )
            assert result["status"] == "styled"

    def test_alignment_case_insensitive(self):
        svc = _mock_service()
        svc.update_text_style.return_value = {
            "presentation_id": "pres1234567",
            "shape_id": "s1",
            "status": "styled",
        }
        result = json.loads(
            _update_text_style(svc, "pres1234567", "s1", alignment="center")
        )
        assert result["status"] == "styled"
        svc.update_text_style.assert_called_once_with(
            "pres1234567", "s1", alignment="CENTER"
        )

    def test_invalid_color_format(self):
        svc = _mock_service()
        result = json.loads(
            _update_text_style(svc, "pres1234567", "s1", foreground_color="red")
        )
        assert result["code"] == "VALIDATION_ERROR"

    def test_valid_hex_color(self):
        svc = _mock_service()
        svc.update_text_style.return_value = {
            "presentation_id": "pres1234567",
            "shape_id": "s1",
            "status": "styled",
        }
        result = json.loads(
            _update_text_style(svc, "pres1234567", "s1", foreground_color="#00FF00")
        )
        assert result["status"] == "styled"

    def test_font_size_zero_returns_error(self):
        svc = _mock_service()
        result = json.loads(_update_text_style(svc, "pres1234567", "s1", font_size=0.0))
        assert result["code"] == "VALIDATION_ERROR"

    def test_font_size_too_large(self):
        svc = _mock_service()
        result = json.loads(
            _update_text_style(svc, "pres1234567", "s1", font_size=1001.0)
        )
        assert result["code"] == "VALIDATION_ERROR"

    def test_font_family_too_long(self):
        svc = _mock_service()
        result = json.loads(
            _update_text_style(svc, "pres1234567", "s1", font_family="A" * 256)
        )
        assert result["code"] == "VALIDATION_ERROR"

    def test_invalid_presentation_id(self):
        svc = _mock_service()
        result = json.loads(_update_text_style(svc, "bad!", "s1", bold="true"))
        assert result["code"] == "VALIDATION_ERROR"

    def test_invalid_shape_id(self):
        svc = _mock_service()
        result = json.loads(_update_text_style(svc, "pres1234567", "", bold="true"))
        assert result["code"] == "VALIDATION_ERROR"

    def test_api_error(self):
        svc = _mock_service()
        svc.update_text_style.side_effect = Exception("API failure")
        result = json.loads(_update_text_style(svc, "pres1234567", "s1", bold="true"))
        assert result["code"] == "API_ERROR"
