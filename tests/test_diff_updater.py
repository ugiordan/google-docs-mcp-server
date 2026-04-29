"""Tests for the diff-based document tab updater."""

from mcp_server.services.batch_style_writer import _utf16_len
from mcp_server.services.diff_updater import (
    block_elements,
    compute_diff_requests,
    doc_elements,
)


def _make_doc_response(paragraphs, tab_id="t.abc"):
    """Build a minimal doc API response from paragraph texts."""
    content = [{"sectionBreak": {}, "startIndex": 0, "endIndex": 1}]
    idx = 1
    for text in paragraphs:
        end = idx + _utf16_len(text)
        content.append(
            {
                "paragraph": {
                    "elements": [
                        {
                            "textRun": {"content": text},
                            "startIndex": idx,
                            "endIndex": end,
                        }
                    ]
                },
                "startIndex": idx,
                "endIndex": end,
            }
        )
        idx = end
    return {
        "tabs": [
            {
                "tabProperties": {"tabId": tab_id},
                "documentTab": {"body": {"content": content}},
            }
        ]
    }


def _make_blocks(items):
    """Build blocks from (type, text) tuples."""
    blocks = []
    for btype, text in items:
        if btype == "heading":
            blocks.append(
                {"type": "heading", "level": 1, "text": text, "runs": [{"text": text}]}
            )
        elif btype == "paragraph":
            blocks.append({"type": "paragraph", "text": text, "runs": [{"text": text}]})
        elif btype == "code_block":
            blocks.append({"type": "code_block", "text": text})
        elif btype == "table":
            blocks.append({"type": "table", "rows": text, "has_header": True})
    return blocks


class TestDocElements:
    def test_extracts_paragraphs(self):
        doc = _make_doc_response(["Hello\n", "World\n"])
        body = doc["tabs"][0]["documentTab"]["body"]["content"]
        elems = doc_elements(body)
        assert len(elems) == 2
        assert elems[0]["text"] == "Hello\n"
        assert elems[0]["start"] == 1
        assert elems[0]["end"] == 7
        assert elems[1]["text"] == "World\n"
        assert elems[1]["start"] == 7

    def test_skips_section_break(self):
        doc = _make_doc_response(["Text\n"])
        body = doc["tabs"][0]["documentTab"]["body"]["content"]
        elems = doc_elements(body)
        assert len(elems) == 1
        assert elems[0]["text"] == "Text\n"

    def test_empty_doc(self):
        body = [{"sectionBreak": {}, "startIndex": 0, "endIndex": 1}]
        elems = doc_elements(body)
        assert elems == []


class TestBlockElements:
    def test_paragraph_block(self):
        blocks = _make_blocks([("paragraph", "Hello")])
        elems = block_elements(blocks)
        assert len(elems) == 1
        assert elems[0]["text"] == "Hello\n"
        assert elems[0]["block_idx"] == 0
        assert elems[0]["is_spacer"] is False

    def test_heading_block(self):
        blocks = _make_blocks([("heading", "Title")])
        elems = block_elements(blocks)
        assert len(elems) == 1
        assert elems[0]["text"] == "Title\n"

    def test_code_block_produces_spacer(self):
        blocks = _make_blocks([("code_block", "x = 1")])
        elems = block_elements(blocks)
        assert len(elems) == 2
        assert elems[0]["text"] == "x = 1\n"
        assert elems[0]["is_spacer"] is False
        assert elems[1]["text"] == "\n"
        assert elems[1]["is_spacer"] is True

    def test_multiple_blocks(self):
        blocks = _make_blocks(
            [
                ("heading", "Title"),
                ("paragraph", "Body text"),
            ]
        )
        elems = block_elements(blocks)
        assert len(elems) == 2
        assert elems[0]["block_idx"] == 0
        assert elems[1]["block_idx"] == 1


class TestComputeDiffRequests:
    def test_identical_content_returns_empty(self):
        doc = _make_doc_response(["Hello\n", "World\n"])
        blocks = _make_blocks([("paragraph", "Hello"), ("paragraph", "World")])
        result = compute_diff_requests(doc, "t.abc", blocks)
        assert result == []

    def test_completely_different_returns_none(self):
        doc = _make_doc_response(["AAA\n", "BBB\n"])
        blocks = _make_blocks([("paragraph", "XXX"), ("paragraph", "YYY")])
        result = compute_diff_requests(doc, "t.abc", blocks)
        assert result is None

    def test_partial_change_generates_targeted_requests(self):
        doc = _make_doc_response(["Keep this\n", "Change this\n", "Keep too\n"])
        blocks = _make_blocks(
            [
                ("paragraph", "Keep this"),
                ("paragraph", "New content"),
                ("paragraph", "Keep too"),
            ]
        )
        result = compute_diff_requests(doc, "t.abc", blocks)
        assert result is not None
        assert len(result) > 0

        has_delete = any("deleteContentRange" in r for r in result)
        has_insert = any("insertText" in r for r in result)
        assert has_delete
        assert has_insert

    def test_append_generates_insert_only(self):
        doc = _make_doc_response(["Existing\n"])
        blocks = _make_blocks(
            [
                ("paragraph", "Existing"),
                ("paragraph", "New paragraph"),
            ]
        )
        result = compute_diff_requests(doc, "t.abc", blocks)
        assert result is not None
        has_delete = any("deleteContentRange" in r for r in result)
        has_insert = any("insertText" in r for r in result)
        assert not has_delete
        assert has_insert

    def test_delete_generates_delete_only(self):
        doc = _make_doc_response(["Keep\n", "Remove\n"])
        blocks = _make_blocks([("paragraph", "Keep")])
        result = compute_diff_requests(doc, "t.abc", blocks)
        assert result is not None
        has_delete = any("deleteContentRange" in r for r in result)
        assert has_delete

    def test_empty_to_content_falls_back(self):
        body_content = [{"sectionBreak": {}, "startIndex": 0, "endIndex": 1}]
        doc = {
            "tabs": [
                {
                    "tabProperties": {"tabId": "t.abc"},
                    "documentTab": {"body": {"content": body_content}},
                }
            ]
        }
        blocks = _make_blocks([("paragraph", "New")])
        result = compute_diff_requests(doc, "t.abc", blocks)
        assert result is None

    def test_delete_range_preserves_trailing_newline(self):
        doc = _make_doc_response(["Only para\n"])
        blocks = _make_blocks([("paragraph", "Replaced")])
        result = compute_diff_requests(doc, "t.abc", blocks)
        assert result is None

    def test_tab_not_found_raises(self):
        doc = _make_doc_response(["Text\n"], tab_id="t.other")
        blocks = _make_blocks([("paragraph", "Text")])
        try:
            compute_diff_requests(doc, "t.missing", blocks)
            assert False, "Expected ValueError"
        except ValueError as e:
            assert "not found" in str(e)

    def test_targeted_delete_uses_correct_indices(self):
        doc = _make_doc_response(["AAA\n", "BBB\n", "CCC\n"])
        blocks = _make_blocks([("paragraph", "AAA"), ("paragraph", "CCC")])
        result = compute_diff_requests(doc, "t.abc", blocks)
        assert result is not None
        deletes = [r for r in result if "deleteContentRange" in r]
        assert len(deletes) == 1
        rng = deletes[0]["deleteContentRange"]["range"]
        assert rng["startIndex"] == 5
        assert rng["endIndex"] == 9

    def test_style_requests_included_for_changed_blocks(self):
        doc = _make_doc_response(["Keep\n", "Old heading\n"])
        blocks = _make_blocks(
            [
                ("paragraph", "Keep"),
                ("heading", "New heading"),
            ]
        )
        result = compute_diff_requests(doc, "t.abc", blocks)
        assert result is not None
        has_para_style = any("updateParagraphStyle" in r for r in result)
        assert has_para_style

    def test_utf16_surrogate_pair_indices(self):
        doc = _make_doc_response(["Hello \U0001f600\n", "Keep\n"])
        blocks = _make_blocks(
            [("paragraph", "Hello \U0001f600"), ("paragraph", "Keep")]
        )
        result = compute_diff_requests(doc, "t.abc", blocks)
        assert result == []

    def test_multiple_non_adjacent_replaces(self):
        doc = _make_doc_response(["A\n", "old1\n", "B\n", "old2\n", "C\n"])
        blocks = _make_blocks(
            [
                ("paragraph", "A"),
                ("paragraph", "new1"),
                ("paragraph", "B"),
                ("paragraph", "new2"),
                ("paragraph", "C"),
            ]
        )
        result = compute_diff_requests(doc, "t.abc", blocks)
        assert result is not None
        deletes = [r for r in result if "deleteContentRange" in r]
        inserts = [r for r in result if "insertText" in r]
        assert len(deletes) == 2
        assert len(inserts) == 2

    def test_insert_at_end_of_document(self):
        doc = _make_doc_response(["First\n", "Second\n"])
        blocks = _make_blocks(
            [
                ("paragraph", "First"),
                ("paragraph", "Second"),
                ("paragraph", "Third"),
            ]
        )
        result = compute_diff_requests(doc, "t.abc", blocks)
        assert result is not None
        has_delete = any("deleteContentRange" in r for r in result)
        has_insert = any("insertText" in r for r in result)
        assert not has_delete
        assert has_insert

    def test_code_block_with_spacer_preserved(self):
        doc = _make_doc_response(["code line\n", "\n", "After\n"])
        blocks = _make_blocks([("code_block", "code line"), ("paragraph", "After")])
        result = compute_diff_requests(doc, "t.abc", blocks)
        assert result == []
