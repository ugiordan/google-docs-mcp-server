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
        assert len(reqs) == 3  # insertText + NORMAL_TEXT + text style reset
        assert reqs[0]["insertText"]["text"] == "Hello\n"
        assert reqs[0]["insertText"]["location"]["index"] == 1

    def test_normal_text_reset(self):
        """All output starts with insertText, NORMAL_TEXT reset, then text style reset."""
        blocks = [{"type": "paragraph", "text": "Hi", "runs": [{"text": "Hi"}]}]
        reqs = blocks_to_batch_requests(blocks)
        # Paragraph style reset
        assert reqs[1]["updateParagraphStyle"]["paragraphStyle"]["namedStyleType"] == "NORMAL_TEXT"
        assert reqs[1]["updateParagraphStyle"]["range"]["startIndex"] == 1
        # Character style reset
        assert reqs[2]["updateTextStyle"]["textStyle"] == {}
        assert "bold" in reqs[2]["updateTextStyle"]["fields"]

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
        assert len(reqs) == 4  # insertText + NORMAL_TEXT + text reset + heading style
        assert (
            reqs[3]["updateParagraphStyle"]["paragraphStyle"]["namedStyleType"]
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
        style_req = reqs[3]["updateParagraphStyle"]
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
        # insertText + NORMAL_TEXT + text reset + updateTextStyle for bold
        assert len(reqs) == 4
        style_req = reqs[3]["updateTextStyle"]
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
        style_req = reqs[3]["updateTextStyle"]
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
        style_req = reqs[3]["updateTextStyle"]
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
        style_req = reqs[3]["updateTextStyle"]
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
        style_req = reqs[3]["updateTextStyle"]
        assert style_req["textStyle"]["link"]["url"] == "https://example.com"

    def test_code_block(self):
        blocks = [{"type": "code_block", "text": "x = 1"}]
        reqs = blocks_to_batch_requests(blocks)
        # insertText + NORMAL_TEXT + text reset + updateTextStyle for monospace
        assert len(reqs) == 4
        style_req = reqs[3]["updateTextStyle"]
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
        para_req = reqs[3]["updateParagraphStyle"]
        assert para_req["paragraphStyle"]["indentStart"]["magnitude"] == 72  # 36 * 2

    def test_blockquote_default_depth(self):
        """Blockquote without explicit depth key defaults to depth=1."""
        blocks = [
            {
                "type": "blockquote",
                "text": "Quote",
                "runs": [{"text": "Quote"}],
            }
        ]
        reqs = blocks_to_batch_requests(blocks)
        para_req = reqs[3]["updateParagraphStyle"]
        assert para_req["paragraphStyle"]["indentStart"]["magnitude"] == 36

    def test_horizontal_rule(self):
        blocks = [{"type": "horizontal_rule"}]
        reqs = blocks_to_batch_requests(blocks)
        assert len(reqs) == 3  # insertText + NORMAL_TEXT + text reset
        assert "\u2500" in reqs[0]["insertText"]["text"]

    # --- List item tests ---

    def test_unordered_list_item(self):
        blocks = [
            {
                "type": "list_item",
                "text": "Item one",
                "runs": [{"text": "Item one"}],
                "ordered": False,
                "nesting_level": 0,
            }
        ]
        reqs = blocks_to_batch_requests(blocks)
        bullet_reqs = [r for r in reqs if "createParagraphBullets" in r]
        assert len(bullet_reqs) == 1
        assert (
            bullet_reqs[0]["createParagraphBullets"]["bulletPreset"]
            == "BULLET_DISC_CIRCLE_SQUARE"
        )

    def test_ordered_list_item(self):
        blocks = [
            {
                "type": "list_item",
                "text": "Step one",
                "runs": [{"text": "Step one"}],
                "ordered": True,
                "nesting_level": 0,
            }
        ]
        reqs = blocks_to_batch_requests(blocks)
        bullet_reqs = [r for r in reqs if "createParagraphBullets" in r]
        assert len(bullet_reqs) == 1
        assert (
            bullet_reqs[0]["createParagraphBullets"]["bulletPreset"]
            == "NUMBERED_DECIMAL_ALPHA_ROMAN"
        )

    def test_nested_list_item(self):
        blocks = [
            {
                "type": "list_item",
                "text": "Nested",
                "runs": [{"text": "Nested"}],
                "ordered": False,
                "nesting_level": 2,
            }
        ]
        reqs = blocks_to_batch_requests(blocks)
        bullet_reqs = [r for r in reqs if "createParagraphBullets" in r]
        assert len(bullet_reqs) == 1
        indent_reqs = [
            r
            for r in reqs
            if "updateParagraphStyle" in r
            and "indentStart" in r["updateParagraphStyle"]["paragraphStyle"]
        ]
        assert len(indent_reqs) == 1
        assert (
            indent_reqs[0]["updateParagraphStyle"]["paragraphStyle"]["indentStart"][
                "magnitude"
            ]
            == 72  # 36 * 2
        )

    def test_list_item_default_ordered(self):
        """List item without explicit ordered key defaults to unordered."""
        blocks = [
            {
                "type": "list_item",
                "text": "Item",
                "runs": [{"text": "Item"}],
            }
        ]
        reqs = blocks_to_batch_requests(blocks)
        bullet_reqs = [r for r in reqs if "createParagraphBullets" in r]
        assert len(bullet_reqs) == 1
        assert (
            bullet_reqs[0]["createParagraphBullets"]["bulletPreset"]
            == "BULLET_DISC_CIRCLE_SQUARE"
        )

    def test_list_item_with_bold_run(self):
        blocks = [
            {
                "type": "list_item",
                "text": "bold item",
                "runs": [{"text": "bold item", "bold": True}],
                "ordered": False,
                "nesting_level": 0,
            }
        ]
        reqs = blocks_to_batch_requests(blocks)
        bullet_reqs = [r for r in reqs if "createParagraphBullets" in r]
        bold_reqs = [
            r
            for r in reqs
            if "updateTextStyle" in r and r["updateTextStyle"]["textStyle"].get("bold")
        ]
        assert len(bullet_reqs) == 1
        assert len(bold_reqs) == 1

    # --- Table tests (text-formatted) ---

    def test_table_with_header(self):
        blocks = [
            {"type": "table", "rows": [["A", "B"], ["1", "2"]], "has_header": True}
        ]
        reqs = blocks_to_batch_requests(blocks)
        text = reqs[0]["insertText"]["text"]
        assert "A" in text
        assert "B" in text
        assert "1" in text
        assert "2" in text
        assert "\u2500" in text  # separator line under header
        # Should have monospace + bold header styles
        monospace_reqs = [
            r
            for r in reqs
            if "updateTextStyle" in r
            and r["updateTextStyle"].get("textStyle", {}).get("weightedFontFamily")
        ]
        assert len(monospace_reqs) >= 1  # monospace for whole table
        bold_reqs = [
            r
            for r in reqs
            if "updateTextStyle" in r
            and r["updateTextStyle"].get("textStyle", {}).get("bold")
            and r["updateTextStyle"].get("fields") == "bold"
        ]
        assert len(bold_reqs) == 1  # bold header row

    def test_table_no_header(self):
        blocks = [{"type": "table", "rows": [["x", "y"]], "has_header": False}]
        reqs = blocks_to_batch_requests(blocks)
        text = reqs[0]["insertText"]["text"]
        assert "x" in text
        assert "y" in text
        assert "\u2500" not in text  # no separator
        # Should have monospace but no bold
        bold_reqs = [
            r
            for r in reqs
            if "updateTextStyle" in r
            and r["updateTextStyle"].get("textStyle", {}).get("bold")
            and r["updateTextStyle"].get("fields") == "bold"
        ]
        assert len(bold_reqs) == 0

    def test_empty_table(self):
        blocks = [{"type": "table", "rows": [], "has_header": False}]
        reqs = blocks_to_batch_requests(blocks)
        assert reqs == []

    def test_table_column_alignment(self):
        """Columns should be padded to equal width."""
        blocks = [
            {
                "type": "table",
                "rows": [["Short", "X"], ["LongerValue", "Y"]],
                "has_header": False,
            }
        ]
        reqs = blocks_to_batch_requests(blocks)
        text = reqs[0]["insertText"]["text"]
        lines = text.strip().split("\n")
        # Both rows should have the same length due to padding
        assert len(lines[0]) == len(lines[1])

    def test_table_jagged_rows(self):
        """Rows with fewer columns than max should be padded."""
        blocks = [
            {
                "type": "table",
                "rows": [["A", "B", "C"], ["1"]],
                "has_header": False,
            }
        ]
        reqs = blocks_to_batch_requests(blocks)
        text = reqs[0]["insertText"]["text"]
        assert "A" in text
        assert "1" in text

    def test_table_single_column(self):
        blocks = [{"type": "table", "rows": [["X"], ["Y"]], "has_header": False}]
        reqs = blocks_to_batch_requests(blocks)
        text = reqs[0]["insertText"]["text"]
        assert "X" in text
        assert "Y" in text
        # Single column, just values on each line

    def test_table_with_text_before_and_after(self):
        """Table between headings should all be in one insertText."""
        blocks = [
            {
                "type": "heading",
                "level": 1,
                "text": "Before",
                "runs": [{"text": "Before"}],
            },
            {"type": "table", "rows": [["A", "B"]], "has_header": False},
            {
                "type": "paragraph",
                "text": "After",
                "runs": [{"text": "After"}],
            },
        ]
        reqs = blocks_to_batch_requests(blocks)
        # All content in a single insertText
        text = reqs[0]["insertText"]["text"]
        assert "Before" in text
        assert "A" in text
        assert "After" in text

    # --- Tab ID scoping tests ---

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
        # reqs[1] = NORMAL_TEXT, reqs[2] = text reset, reqs[3] = heading style
        style_req = reqs[3]["updateParagraphStyle"]
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
        # reqs[1] = NORMAL_TEXT, reqs[2] = text reset, reqs[3] = bold style
        style_req = reqs[3]["updateTextStyle"]
        assert style_req["range"]["tabId"] == "t1"

    def test_no_tab_id_omitted(self):
        blocks = [{"type": "paragraph", "text": "Hi", "runs": [{"text": "Hi"}]}]
        reqs = blocks_to_batch_requests(blocks)
        assert "tabId" not in reqs[0]["insertText"]["location"]

    def test_tab_id_on_list_item_bullet(self):
        blocks = [
            {
                "type": "list_item",
                "text": "Item",
                "runs": [{"text": "Item"}],
                "ordered": False,
                "nesting_level": 0,
            }
        ]
        reqs = blocks_to_batch_requests(blocks, tab_id="t1")
        bullet_req = [r for r in reqs if "createParagraphBullets" in r][0]
        assert bullet_req["createParagraphBullets"]["range"]["tabId"] == "t1"

    # --- Mixed content tests ---

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
        # insertText + NORMAL_TEXT + text reset + 2 heading styles
        assert len(reqs) == 5
        h1 = reqs[3]["updateParagraphStyle"]
        h2 = reqs[4]["updateParagraphStyle"]
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
        heading_reqs = [
            r
            for r in reqs
            if "updateParagraphStyle" in r
            and r["updateParagraphStyle"]["paragraphStyle"]["namedStyleType"]
            != "NORMAL_TEXT"
        ]
        assert len(heading_reqs) == 6
        for i, req in enumerate(heading_reqs, 1):
            assert (
                req["updateParagraphStyle"]["paragraphStyle"]["namedStyleType"]
                == f"HEADING_{i}"
            )

    def test_empty_runs_list(self):
        """Block with empty runs list still produces a newline paragraph."""
        blocks = [{"type": "paragraph", "text": "fallback", "runs": []}]
        reqs = blocks_to_batch_requests(blocks)
        assert len(reqs) == 3  # insertText + NORMAL_TEXT + text reset
        assert reqs[0]["insertText"]["text"] == "\n"

    def test_run_with_empty_text(self):
        """Runs with empty text strings should be skipped."""
        blocks = [
            {
                "type": "paragraph",
                "text": "hello",
                "runs": [{"text": ""}, {"text": "hello"}, {"text": ""}],
            }
        ]
        reqs = blocks_to_batch_requests(blocks)
        assert reqs[0]["insertText"]["text"] == "hello\n"
