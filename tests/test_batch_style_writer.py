"""Tests for mcp_server.services.batch_style_writer."""

from mcp_server.services.batch_style_writer import (
    _cell_index,
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


class TestCellIndex:
    def test_first_cell(self):
        # table_start + 3 + 0 + 0 = table_start + 3
        assert _cell_index(2, 0, 0, 2) == 5

    def test_second_col(self):
        # table_start + 3 + 0 + 2 = table_start + 5
        assert _cell_index(2, 0, 1, 2) == 7

    def test_second_row_first_col(self):
        # table_start + 3 + 1*(1+4) + 0 = table_start + 8
        assert _cell_index(2, 1, 0, 2) == 10

    def test_second_row_second_col(self):
        # table_start + 3 + 1*(1+4) + 2 = table_start + 10
        assert _cell_index(2, 1, 1, 2) == 12

    def test_single_column(self):
        # table_start + 3 + row*(1+2) + 0
        assert _cell_index(2, 0, 0, 1) == 5
        assert _cell_index(2, 1, 0, 1) == 8

    def test_three_columns(self):
        # table_start + 3 + 0 + 2*col
        assert _cell_index(2, 0, 0, 3) == 5
        assert _cell_index(2, 0, 1, 3) == 7
        assert _cell_index(2, 0, 2, 3) == 9


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

    # --- Native table tests ---

    def test_table_insert_table_request(self):
        """Table block produces an insertTable request."""
        blocks = [
            {"type": "table", "rows": [["A", "B"], ["1", "2"]], "has_header": False}
        ]
        reqs = blocks_to_batch_requests(blocks)
        insert_table = reqs[0]
        assert "insertTable" in insert_table
        assert insert_table["insertTable"]["rows"] == 2
        assert insert_table["insertTable"]["columns"] == 2
        assert insert_table["insertTable"]["location"]["index"] == 1

    def test_table_cell_inserts_reverse_order(self):
        """Cells are filled in reverse order (last cell first)."""
        blocks = [
            {"type": "table", "rows": [["A", "B"], ["1", "2"]], "has_header": False}
        ]
        reqs = blocks_to_batch_requests(blocks)
        # reqs[0] = insertTable, reqs[1..4] = cell inserts in reverse
        cell_inserts = [r for r in reqs if "insertText" in r]
        assert len(cell_inserts) == 4
        # Reverse order: (1,1), (1,0), (0,1), (0,0)
        # table_start = 2, cell indices: (0,0)=5, (0,1)=7, (1,0)=10, (1,1)=12
        assert cell_inserts[0]["insertText"]["location"]["index"] == 12  # (1,1)
        assert cell_inserts[0]["insertText"]["text"] == "2"
        assert cell_inserts[1]["insertText"]["location"]["index"] == 10  # (1,0)
        assert cell_inserts[1]["insertText"]["text"] == "1"
        assert cell_inserts[2]["insertText"]["location"]["index"] == 7  # (0,1)
        assert cell_inserts[2]["insertText"]["text"] == "B"
        assert cell_inserts[3]["insertText"]["location"]["index"] == 5  # (0,0)
        assert cell_inserts[3]["insertText"]["text"] == "A"

    def test_table_with_header_bold(self):
        """Header row cells get bold styling."""
        blocks = [
            {"type": "table", "rows": [["A", "B"], ["1", "2"]], "has_header": True}
        ]
        reqs = blocks_to_batch_requests(blocks)
        bold_reqs = [
            r
            for r in reqs
            if "updateTextStyle" in r
            and r["updateTextStyle"].get("textStyle", {}).get("bold")
        ]
        # Header has 2 cells, so 2 bold requests
        assert len(bold_reqs) == 2

    def test_table_no_header_no_bold(self):
        """No header means no bold styling."""
        blocks = [{"type": "table", "rows": [["x", "y"]], "has_header": False}]
        reqs = blocks_to_batch_requests(blocks)
        bold_reqs = [
            r
            for r in reqs
            if "updateTextStyle" in r
            and r["updateTextStyle"].get("textStyle", {}).get("bold")
        ]
        assert len(bold_reqs) == 0

    def test_empty_table(self):
        blocks = [{"type": "table", "rows": [], "has_header": False}]
        reqs = blocks_to_batch_requests(blocks)
        assert reqs == []

    def test_table_jagged_rows(self):
        """Rows with fewer columns than max skip empty cells."""
        blocks = [
            {
                "type": "table",
                "rows": [["A", "B", "C"], ["1"]],
                "has_header": False,
            }
        ]
        reqs = blocks_to_batch_requests(blocks)
        assert reqs[0]["insertTable"]["columns"] == 3
        cell_inserts = [r for r in reqs if "insertText" in r]
        # Row 0 has 3 cells, row 1 has 1 cell = 4 inserts
        assert len(cell_inserts) == 4
        # Row 1 cols 1,2 are empty strings so skipped
        texts = [r["insertText"]["text"] for r in cell_inserts]
        assert "A" in texts
        assert "1" in texts

    def test_table_single_column(self):
        blocks = [{"type": "table", "rows": [["X"], ["Y"]], "has_header": False}]
        reqs = blocks_to_batch_requests(blocks)
        assert reqs[0]["insertTable"]["columns"] == 1
        cell_inserts = [r for r in reqs if "insertText" in r]
        assert len(cell_inserts) == 2
        texts = [r["insertText"]["text"] for r in cell_inserts]
        assert "X" in texts
        assert "Y" in texts

    def test_table_with_text_before_and_after(self):
        """Table between text blocks: segments processed in reverse."""
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
        # 3 segments processed in reverse:
        # 1. paragraph "After" text segment (insertText + NORMAL_TEXT + text reset)
        # 2. table segment (insertTable + cell inserts)
        # 3. heading "Before" text segment (insertText + NORMAL_TEXT + text reset + heading style)
        # Paragraph segment first (reverse order)
        assert reqs[0]["insertText"]["text"] == "After\n"
        # Table segment
        table_reqs = [r for r in reqs if "insertTable" in r]
        assert len(table_reqs) == 1
        # Heading segment last
        heading_inserts = [
            r for r in reqs if "insertText" in r and r["insertText"]["text"] == "Before\n"
        ]
        assert len(heading_inserts) == 1

    def test_table_header_bold_indices(self):
        """Bold header styling has correct index range."""
        blocks = [
            {"type": "table", "rows": [["Hi", "World"], ["a", "b"]], "has_header": True}
        ]
        reqs = blocks_to_batch_requests(blocks)
        bold_reqs = [
            r
            for r in reqs
            if "updateTextStyle" in r
            and r["updateTextStyle"].get("textStyle", {}).get("bold")
        ]
        assert len(bold_reqs) == 2
        # Cell (0,1) processed before (0,0) in reverse
        # cell(0,1) at index 7, "World" = 5 chars -> range [7, 12)
        # cell(0,0) at index 5, "Hi" = 2 chars -> range [5, 7)
        ranges = [(r["updateTextStyle"]["range"]["startIndex"],
                    r["updateTextStyle"]["range"]["endIndex"]) for r in bold_reqs]
        assert (7, 12) in ranges  # "World"
        assert (5, 7) in ranges   # "Hi"

    def test_table_empty_cells_skipped(self):
        """Empty string cells don't produce insertText requests."""
        blocks = [
            {"type": "table", "rows": [["A", ""], ["", "D"]], "has_header": False}
        ]
        reqs = blocks_to_batch_requests(blocks)
        cell_inserts = [r for r in reqs if "insertText" in r]
        assert len(cell_inserts) == 2
        texts = {r["insertText"]["text"] for r in cell_inserts}
        assert texts == {"A", "D"}

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

    def test_tab_id_on_table(self):
        """Table insertTable and cell inserts include tabId."""
        blocks = [
            {"type": "table", "rows": [["X"]], "has_header": False}
        ]
        reqs = blocks_to_batch_requests(blocks, tab_id="t1")
        assert reqs[0]["insertTable"]["location"]["tabId"] == "t1"
        cell_insert = [r for r in reqs if "insertText" in r][0]
        assert cell_insert["insertText"]["location"]["tabId"] == "t1"

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

    def test_mixed_text_and_table(self):
        """Text-table-text produces three segments in correct reverse order."""
        blocks = [
            {"type": "paragraph", "text": "Top", "runs": [{"text": "Top"}]},
            {"type": "table", "rows": [["A"]], "has_header": False},
            {"type": "paragraph", "text": "Bottom", "runs": [{"text": "Bottom"}]},
        ]
        reqs = blocks_to_batch_requests(blocks)
        # Reverse order: Bottom text segment, table, Top text segment
        # Bottom segment first
        assert reqs[0]["insertText"]["text"] == "Bottom\n"
        # Table somewhere in the middle
        table_reqs = [r for r in reqs if "insertTable" in r]
        assert len(table_reqs) == 1
        # Top segment last
        top_inserts = [
            r for r in reqs if "insertText" in r and r["insertText"]["text"] == "Top\n"
        ]
        assert len(top_inserts) == 1

    def test_consecutive_tables(self):
        """Multiple tables each get their own insertTable."""
        blocks = [
            {"type": "table", "rows": [["A"]], "has_header": False},
            {"type": "table", "rows": [["B"]], "has_header": False},
        ]
        reqs = blocks_to_batch_requests(blocks)
        table_reqs = [r for r in reqs if "insertTable" in r]
        assert len(table_reqs) == 2

    def test_table_cells_get_style_resets(self):
        """Table cells get NORMAL_TEXT and character style resets."""
        blocks = [
            {"type": "table", "rows": [["X"]], "has_header": False}
        ]
        reqs = blocks_to_batch_requests(blocks)
        # 1 cell = 1 NORMAL_TEXT reset + 1 character reset
        normal_text_reqs = [
            r for r in reqs
            if "updateParagraphStyle" in r
            and r["updateParagraphStyle"]["paragraphStyle"].get("namedStyleType") == "NORMAL_TEXT"
        ]
        assert len(normal_text_reqs) == 1
        char_resets = [
            r for r in reqs
            if "updateTextStyle" in r
            and r["updateTextStyle"]["textStyle"] == {}
        ]
        assert len(char_resets) == 1

    def test_table_multi_cell_resets(self):
        """Each cell in the table gets its own style reset."""
        blocks = [
            {"type": "table", "rows": [["A", "B"], ["C", "D"]], "has_header": False}
        ]
        reqs = blocks_to_batch_requests(blocks)
        # 4 cells = 4 NORMAL_TEXT resets + 4 character resets
        normal_text_reqs = [
            r for r in reqs
            if "updateParagraphStyle" in r
            and r["updateParagraphStyle"]["paragraphStyle"].get("namedStyleType") == "NORMAL_TEXT"
        ]
        assert len(normal_text_reqs) == 4

    def test_table_emoji_in_cells(self):
        """Emoji in table cells should use correct UTF-16 length for ranges."""
        blocks = [
            {"type": "table", "rows": [["\U0001f389"]], "has_header": True}
        ]
        reqs = blocks_to_batch_requests(blocks)
        bold_reqs = [
            r for r in reqs
            if "updateTextStyle" in r
            and r["updateTextStyle"].get("textStyle", {}).get("bold")
        ]
        assert len(bold_reqs) == 1
        # Emoji is 2 UTF-16 code units
        r = bold_reqs[0]["updateTextStyle"]["range"]
        assert r["endIndex"] - r["startIndex"] == 2

    def test_table_header_with_empty_cell(self):
        """Header row with empty cell skips bold for that cell."""
        blocks = [
            {"type": "table", "rows": [["A", ""], ["1", "2"]], "has_header": True}
        ]
        reqs = blocks_to_batch_requests(blocks)
        bold_reqs = [
            r for r in reqs
            if "updateTextStyle" in r
            and r["updateTextStyle"].get("textStyle", {}).get("bold")
        ]
        # Only "A" gets bold, empty cell skipped
        assert len(bold_reqs) == 1

    def test_custom_start_index(self):
        """Non-default start_index offsets all indices correctly."""
        blocks = [{"type": "paragraph", "text": "Hi", "runs": [{"text": "Hi"}]}]
        reqs = blocks_to_batch_requests(blocks, start_index=5)
        assert reqs[0]["insertText"]["location"]["index"] == 5
        assert reqs[1]["updateParagraphStyle"]["range"]["startIndex"] == 5

    def test_table_custom_start_index(self):
        """Table with non-default start_index."""
        blocks = [{"type": "table", "rows": [["X"]], "has_header": False}]
        reqs = blocks_to_batch_requests(blocks, start_index=5)
        assert reqs[0]["insertTable"]["location"]["index"] == 5
        cell_insert = [r for r in reqs if "insertText" in r][0]
        # table_start = 6, cell(0,0) = 6 + 3 = 9
        assert cell_insert["insertText"]["location"]["index"] == 9
