import pytest

from mcp_server.validation import (
    sanitize_query,
    validate_comment,
    validate_comment_id,
    validate_content_size,
    validate_document_id,
    validate_folder_id,
    validate_mime_type,
    validate_presentation_id,
    validate_shape_id,
    validate_slide_id,
    validate_tab_id,
    validate_template_name,
    validate_title,
)


class TestValidateDocumentId:
    def test_valid_id(self):
        assert validate_document_id("1aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789ABC") is True

    def test_rejects_empty(self):
        with pytest.raises(ValueError, match="Document ID cannot be empty"):
            validate_document_id("")

    def test_rejects_special_chars(self):
        with pytest.raises(ValueError, match="Invalid document ID format"):
            validate_document_id("../../../etc/passwd")

    def test_rejects_too_long(self):
        with pytest.raises(ValueError, match="Invalid document ID format"):
            validate_document_id("a" * 200)


class TestValidateFolderId:
    def test_valid_id(self):
        assert validate_folder_id("1aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789ABC") is True

    def test_rejects_empty(self):
        with pytest.raises(ValueError, match="Folder ID cannot be empty"):
            validate_folder_id("")

    def test_rejects_special_chars(self):
        with pytest.raises(ValueError, match="Invalid folder ID format"):
            validate_folder_id("../../../etc/passwd")


class TestSanitizeQuery:
    def test_escapes_single_quotes(self):
        assert sanitize_query("test's") == "test\\'s"

    def test_escapes_backslashes(self):
        assert sanitize_query("test\\path") == "test\\\\path"

    def test_passes_normal_query(self):
        assert sanitize_query("my document") == "my document"


class TestValidateTitle:
    def test_valid_title(self):
        assert validate_title("My Document") is True

    def test_rejects_empty(self):
        with pytest.raises(ValueError, match="Title cannot be empty"):
            validate_title("")

    def test_rejects_too_long(self):
        with pytest.raises(ValueError, match="Title exceeds 255 characters"):
            validate_title("a" * 256)


class TestValidateContentSize:
    def test_valid_content(self):
        assert validate_content_size("hello", max_bytes=1_048_576) is True

    def test_rejects_oversized(self):
        with pytest.raises(ValueError, match="Content exceeds"):
            validate_content_size("a" * 1_048_577, max_bytes=1_048_576)


class TestValidateComment:
    def test_valid_comment(self):
        assert validate_comment("looks good") is True

    def test_rejects_too_long(self):
        with pytest.raises(ValueError, match="Comment exceeds 2048 characters"):
            validate_comment("a" * 2049)


class TestValidateCommentId:
    def test_valid_comment_id(self):
        assert validate_comment_id("comment123") is True

    def test_valid_comment_id_with_hyphens(self):
        assert validate_comment_id("abc-def-123") is True

    def test_rejects_empty(self):
        with pytest.raises(ValueError, match="Comment ID cannot be empty"):
            validate_comment_id("")

    def test_rejects_spaces(self):
        with pytest.raises(ValueError, match="Invalid comment ID"):
            validate_comment_id("bad id")

    def test_rejects_special_chars(self):
        with pytest.raises(ValueError, match="Invalid comment ID"):
            validate_comment_id("id!@#$")


class TestValidateTemplateName:
    def test_valid_name(self):
        assert validate_template_name("standard", ["standard", "report"]) is True

    def test_rejects_unknown(self):
        with pytest.raises(ValueError, match="Unknown template"):
            validate_template_name("hacked", ["standard", "report"])


class TestValidateTabId:
    def test_valid_tab_id(self):
        assert validate_tab_id("t.0") is True

    def test_valid_tab_id_long(self):
        assert validate_tab_id("t.abc123def") is True

    def test_rejects_empty(self):
        with pytest.raises(ValueError, match="Tab ID cannot be empty"):
            validate_tab_id("")

    def test_rejects_spaces(self):
        with pytest.raises(ValueError, match="Invalid tab ID format"):
            validate_tab_id("t 0")

    def test_rejects_special_chars(self):
        with pytest.raises(ValueError, match="Invalid tab ID format"):
            validate_tab_id("t.0; DROP TABLE")


class TestValidateMimeType:
    def test_valid_docx_mime_type(self):
        assert (
            validate_mime_type(
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )
            is True
        )

    def test_valid_pdf_mime_type(self):
        assert validate_mime_type("application/pdf") is True

    def test_valid_html_mime_type(self):
        assert validate_mime_type("text/html") is True

    def test_valid_rtf_mime_type(self):
        assert validate_mime_type("application/rtf") is True

    def test_rejects_unsupported_mime_type(self):
        with pytest.raises(ValueError, match="Unsupported MIME type"):
            validate_mime_type("application/zip")

    def test_rejects_empty_mime_type(self):
        with pytest.raises(ValueError, match="MIME type cannot be empty"):
            validate_mime_type("")


class TestValidatePresentationId:
    def test_valid_id(self):
        assert (
            validate_presentation_id("1aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789ABC") is True
        )

    def test_rejects_empty(self):
        with pytest.raises(ValueError, match="Presentation ID cannot be empty"):
            validate_presentation_id("")

    def test_rejects_short_id(self):
        with pytest.raises(ValueError, match="Invalid presentation ID"):
            validate_presentation_id("abc")

    def test_min_length_boundary(self):
        assert validate_presentation_id("a" * 10) is True

    def test_below_min_length(self):
        with pytest.raises(ValueError, match="Invalid presentation ID"):
            validate_presentation_id("a" * 9)

    def test_max_length_boundary(self):
        assert validate_presentation_id("a" * 100) is True

    def test_above_max_length(self):
        with pytest.raises(ValueError, match="Invalid presentation ID"):
            validate_presentation_id("a" * 101)

    def test_rejects_dots(self):
        with pytest.raises(ValueError, match="Invalid presentation ID"):
            validate_presentation_id("a.bcdef1234")


class TestValidateSlideId:
    def test_valid_short_id(self):
        assert validate_slide_id("p") is True

    def test_valid_long_id(self):
        assert validate_slide_id("gcbd9fbfbdf_1_0") is True

    def test_valid_id_with_dots(self):
        assert validate_slide_id("p.g35f80012e0_0_0") is True

    def test_rejects_empty(self):
        with pytest.raises(ValueError, match="Slide ID cannot be empty"):
            validate_slide_id("")

    def test_max_length_boundary(self):
        assert validate_slide_id("a" * 100) is True

    def test_above_max_length(self):
        with pytest.raises(ValueError, match="Invalid slide ID"):
            validate_slide_id("a" * 101)

    def test_rejects_spaces(self):
        with pytest.raises(ValueError, match="Invalid slide ID"):
            validate_slide_id("slide 1")

    def test_rejects_special_chars(self):
        with pytest.raises(ValueError, match="Invalid slide ID"):
            validate_slide_id("s1;DROP")


class TestValidateShapeId:
    def test_valid_id(self):
        assert validate_shape_id("shape123") is True

    def test_valid_id_with_dots(self):
        assert validate_shape_id("p.shape.1") is True

    def test_rejects_empty(self):
        with pytest.raises(ValueError, match="Shape ID cannot be empty"):
            validate_shape_id("")

    def test_max_length_boundary(self):
        assert validate_shape_id("s" * 100) is True

    def test_above_max_length(self):
        with pytest.raises(ValueError, match="Invalid shape ID"):
            validate_shape_id("s" * 101)

    def test_rejects_special_chars(self):
        with pytest.raises(ValueError, match="Invalid shape ID"):
            validate_shape_id("shape!@#")
