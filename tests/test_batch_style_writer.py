"""Tests for mcp_server.services.batch_style_writer."""

from mcp_server.services.batch_style_writer import (
    _utf16_len,
    blocks_to_batch_requests,
)


class TestUtf16Len:
    def test_ascii(self):
        assert _utf16_len("hello") == 5

    def test_empty(self):
        assert _utf16_len("") == 0

    def test_emoji(self):
        # Emoji like 🎉 takes 2 UTF-16 code units
        assert _utf16_len("\U0001f389") == 2

    def test_mixed(self):
        assert _utf16_len("hi\U0001f389") == 4


class TestBlocksToBatchRequests:
    def test_empty_blocks(self):
        assert blocks_to_batch_requests([]) == []

    def test_single_paragraph(self):
        blocks = [{"type": "paragraph", "text": "Hello", "runs": [{"text": "Hello"}]}]
        reqs = blocks_to_batch_requests(blocks)
        assert len(reqs) == 1  # insertText only
        assert reqs[0]["insertText"]["text"] == "Hello\n"
        assert reqs[0]["insertText"]["location"]["index"] == 1

    def test_heading(self):
        blocks = [
            {
                "type": "heading",
                "level": 2,
                "text": "Title",
                "runs": [{"text": "Title"}],
            }
        ]
        reqs = blocks_to_batch_requests(blocks)
        assert len(reqs) == 2  # insertText + updateParagraphStyle
        assert (
            reqs[1]["updateParagraphStyle"]["paragraphStyle"]["namedStyleType"]
            == "HEADING_2"
        )

    def test_heading_range(self):
        blocks = [
            {
                "type": "heading",
                "level": 1,
                "text": "Hi",
                "runs": [{"text": "Hi"}],
            }
        ]
        reqs = blocks_to_batch_requests(blocks)
        style_req = reqs[1]["updateParagraphStyle"]
        assert style_req["range"]["startIndex"] == 1
        assert style_req["range"]["endIndex"] == 4  # "Hi\n"

    def test_bold_run(self):
        blocks = [
            {
                "type": "paragraph",
                "text": "normal bold",
                "runs": [{"text": "normal "}, {"text": "bold", "bold": True}],
            }
        ]
        reqs = blocks_to_batch_requests(blocks)
        # insertText + updateTextStyle for bold
        assert len(reqs) == 2
        style_req = reqs[1]["updateTextStyle"]
        assert style_req["textStyle"]["bold"] is True
        assert style_req["range"]["startIndex"] == 8  # after "normal "
        assert style_req["range"]["endIndex"] == 12  # "bold"

    def test_italic_run(self):
        blocks = [
            {
                "type": "paragraph",
                "text": "em",
                "runs": [{"text": "em", "italic": True}],
            }
        ]
        reqs = blocks_to_batch_requests(blocks)
        style_req = reqs[1]["updateTextStyle"]
        assert style_req["textStyle"]["italic"] is True

    def test_code_run(self):
        blocks = [
            {
                "type": "paragraph",
                "text": "fn()",
                "runs": [{"text": "fn()", "code": True}],
            }
        ]
        reqs = blocks_to_batch_requests(blocks)
        style_req = reqs[1]["updateTextStyle"]
        assert (
            style_req["textStyle"]["weightedFontFamily"]["fontFamily"] == "Courier New"
        )

    def test_strikethrough_run(self):
        blocks = [
            {
                "type": "paragraph",
                "text": "del",
                "runs": [{"text": "del", "strikethrough": True}],
            }
        ]
        reqs = blocks_to_batch_requests(blocks)
        style_req = reqs[1]["updateTextStyle"]
        assert style_req["textStyle"]["strikethrough"] is True

    def test_link_run(self):
        blocks = [
            {
                "type": "paragraph",
                "text": "click",
                "runs": [{"text": "click", "link": "https://example.com"}],
            }
        ]
        reqs = blocks_to_batch_requests(blocks)
        style_req = reqs[1]["updateTextStyle"]
        assert style_req["textStyle"]["link"]["url"] == "https://example.com"

    def test_code_block(self):
        blocks = [{"type": "code_block", "text": "x = 1"}]
        reqs = blocks_to_batch_requests(blocks)
        # insertText + updateTextStyle for monospace
        assert len(reqs) == 2
        style_req = reqs[1]["updateTextStyle"]
        assert (
            style_req["textStyle"]["weightedFontFamily"]["fontFamily"] == "Courier New"
        )

    def test_blockquote(self):
        blocks = [
            {
                "type": "blockquote",
                "text": "Quote",
                "depth": 2,
                "runs": [{"text": "Quote"}],
            }
        ]
        reqs = blocks_to_batch_requests(blocks)
        para_req = reqs[1]["updateParagraphStyle"]
        assert para_req["paragraphStyle"]["indentStart"]["magnitude"] == 72  # 36 * 2

    def test_horizontal_rule(self):
        blocks = [{"type": "horizontal_rule"}]
        reqs = blocks_to_batch_requests(blocks)
        assert len(reqs) == 1  # insertText only
        assert "\u2500" in reqs[0]["insertText"]["text"]

    def test_table(self):
        blocks = [
            {"type": "table", "rows": [["A", "B"], ["1", "2"]], "has_header": True}
        ]
        reqs = blocks_to_batch_requests(blocks)
        assert len(reqs) >= 1
        text = reqs[0]["insertText"]["text"]
        assert "A" in text
        assert "B" in text
        assert "1" in text
        assert "\u2500" in text  # separator line

    def test_table_no_header(self):
        blocks = [{"type": "table", "rows": [["x", "y"]], "has_header": False}]
        reqs = blocks_to_batch_requests(blocks)
        text = reqs[0]["insertText"]["text"]
        assert "x" in text
        assert "\u2500" not in text  # no separator

    def test_empty_table(self):
        blocks = [{"type": "table", "rows": [], "has_header": False}]
        reqs = blocks_to_batch_requests(blocks)
        assert reqs == []

    def test_tab_id_scoping(self):
        blocks = [{"type": "paragraph", "text": "Hi", "runs": [{"text": "Hi"}]}]
        reqs = blocks_to_batch_requests(blocks, tab_id="tab123")
        assert reqs[0]["insertText"]["location"]["tabId"] == "tab123"

    def test_tab_id_on_paragraph_style(self):
        blocks = [
            {
                "type": "heading",
                "level": 1,
                "text": "H",
                "runs": [{"text": "H"}],
            }
        ]
        reqs = blocks_to_batch_requests(blocks, tab_id="t1")
        style_req = reqs[1]["updateParagraphStyle"]
        assert style_req["range"]["tabId"] == "t1"

    def test_tab_id_on_text_style(self):
        blocks = [
            {
                "type": "paragraph",
                "text": "b",
                "runs": [{"text": "b", "bold": True}],
            }
        ]
        reqs = blocks_to_batch_requests(blocks, tab_id="t1")
        style_req = reqs[1]["updateTextStyle"]
        assert style_req["range"]["tabId"] == "t1"

    def test_no_tab_id_omitted(self):
        blocks = [{"type": "paragraph", "text": "Hi", "runs": [{"text": "Hi"}]}]
        reqs = blocks_to_batch_requests(blocks)
        assert "tabId" not in reqs[0]["insertText"]["location"]

    def test_mixed_content(self):
        blocks = [
            {
                "type": "heading",
                "level": 1,
                "text": "Title",
                "runs": [{"text": "Title"}],
            },
            {
                "type": "paragraph",
                "text": "Hello bold",
                "runs": [{"text": "Hello "}, {"text": "bold", "bold": True}],
            },
            {"type": "code_block", "text": "x = 1"},
            {"type": "horizontal_rule"},
        ]
        reqs = blocks_to_batch_requests(blocks)
        # insertText + heading style + bold style + code style
        assert len(reqs) >= 4
        text = reqs[0]["insertText"]["text"]
        assert "Title" in text
        assert "Hello " in text
        assert "x = 1" in text

    def test_multiple_headings_correct_indices(self):
        blocks = [
            {
                "type": "heading",
                "level": 1,
                "text": "A",
                "runs": [{"text": "A"}],
            },
            {
                "type": "heading",
                "level": 2,
                "text": "B",
                "runs": [{"text": "B"}],
            },
        ]
        reqs = blocks_to_batch_requests(blocks)
        # insertText + 2 heading styles
        assert len(reqs) == 3
        h1 = reqs[1]["updateParagraphStyle"]
        h2 = reqs[2]["updateParagraphStyle"]
        # "A\n" = indices 1-3, "B\n" = indices 3-5
        assert h1["range"]["startIndex"] == 1
        assert h1["range"]["endIndex"] == 3
        assert h2["range"]["startIndex"] == 3
        assert h2["range"]["endIndex"] == 5

    def test_blocks_without_runs_key(self):
        blocks = [{"type": "paragraph", "text": "No runs"}]
        reqs = blocks_to_batch_requests(blocks)
        assert reqs[0]["insertText"]["text"] == "No runs\n"

    def test_all_heading_levels(self):
        blocks = [
            {
                "type": "heading",
                "level": i,
                "text": f"H{i}",
                "runs": [{"text": f"H{i}"}],
            }
            for i in range(1, 7)
        ]
        reqs = blocks_to_batch_requests(blocks)
        heading_reqs = [r for r in reqs if "updateParagraphStyle" in r]
        assert len(heading_reqs) == 6
        for i, req in enumerate(heading_reqs, 1):
            assert (
                req["updateParagraphStyle"]["paragraphStyle"]["namedStyleType"]
                == f"HEADING_{i}"
            )
