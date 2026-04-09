"""Tests for mcp_server.services.markdown_converter."""

from mcp_server.services.markdown_converter import (
    _strip_runs,
    extract_template_styles,
    parse_markdown,
)

# ---------------------------------------------------------------------------
# Utility tests
# ---------------------------------------------------------------------------


class TestStripRuns:
    def test_strips_leading_whitespace(self):
        result = _strip_runs([{"text": "  hello"}])
        assert result == [{"text": "hello"}]

    def test_strips_trailing_whitespace(self):
        result = _strip_runs([{"text": "hello  "}])
        assert result == [{"text": "hello"}]

    def test_drops_empty_leading_runs(self):
        result = _strip_runs([{"text": "  "}, {"text": "hello"}])
        assert len(result) == 1
        assert result[0]["text"] == "hello"

    def test_preserves_formatting(self):
        result = _strip_runs([{"text": "  bold  ", "bold": True}])
        assert result == [{"text": "bold", "bold": True}]

    def test_empty_input(self):
        assert _strip_runs([]) == []

    def test_all_whitespace(self):
        assert _strip_runs([{"text": "  "}]) == []


# ---------------------------------------------------------------------------
# Parser tests
# ---------------------------------------------------------------------------


class TestParseMarkdown:
    def test_parses_heading(self):
        blocks = parse_markdown("# Hello World")
        assert len(blocks) >= 1
        assert blocks[0]["type"] == "heading"
        assert blocks[0]["level"] == 1
        assert blocks[0]["text"] == "Hello World"

    def test_parses_multiple_headings(self):
        md = "# H1\n\n## H2\n\n### H3"
        blocks = parse_markdown(md)
        headings = [b for b in blocks if b["type"] == "heading"]
        assert len(headings) == 3
        assert headings[0]["level"] == 1
        assert headings[1]["level"] == 2
        assert headings[2]["level"] == 3

    def test_parses_paragraph(self):
        blocks = parse_markdown("Just some text.")
        assert len(blocks) >= 1
        assert blocks[0]["type"] == "paragraph"
        assert blocks[0]["text"] == "Just some text."

    def test_parses_bold_text(self):
        blocks = parse_markdown("This is **bold** text")
        runs = blocks[0]["runs"]
        bold_runs = [r for r in runs if r.get("bold")]
        assert bold_runs[0]["text"] == "bold"

    def test_parses_italic_text(self):
        blocks = parse_markdown("This is *italic* text")
        runs = blocks[0]["runs"]
        italic_runs = [r for r in runs if r.get("italic")]
        assert italic_runs[0]["text"] == "italic"

    def test_parses_bold_italic_combined(self):
        blocks = parse_markdown("This is ***bold italic*** text")
        runs = blocks[0]["runs"]
        combined = [r for r in runs if r.get("bold") and r.get("italic")]
        assert len(combined) == 1
        assert combined[0]["text"] == "bold italic"

    def test_parses_inline_code(self):
        blocks = parse_markdown("Use `print()` here")
        runs = blocks[0]["runs"]
        code_runs = [r for r in runs if r.get("code")]
        assert code_runs[0]["text"] == "print()"

    def test_parses_link(self):
        blocks = parse_markdown("Click [here](https://example.com) now")
        runs = blocks[0]["runs"]
        link_runs = [r for r in runs if r.get("link")]
        assert link_runs[0]["text"] == "here"
        assert link_runs[0]["link"] == "https://example.com"

    def test_parses_code_block(self):
        md = "```python\nprint('hello')\n```"
        blocks = parse_markdown(md)
        code_blocks = [b for b in blocks if b["type"] == "code_block"]
        assert len(code_blocks) == 1
        assert "print('hello')" in code_blocks[0]["text"]

    def test_parses_unordered_list(self):
        md = "- item one\n- item two\n- item three"
        blocks = parse_markdown(md)
        list_items = [b for b in blocks if b["type"] == "list_item"]
        assert len(list_items) == 3
        assert all(not b["ordered"] for b in list_items)

    def test_parses_ordered_list(self):
        md = "1. first\n2. second\n3. third"
        blocks = parse_markdown(md)
        list_items = [b for b in blocks if b["type"] == "list_item"]
        assert len(list_items) == 3
        assert all(b["ordered"] for b in list_items)

    def test_parses_horizontal_rule(self):
        blocks = parse_markdown("Above\n\n---\n\nBelow")
        hr_blocks = [b for b in blocks if b["type"] == "horizontal_rule"]
        assert len(hr_blocks) == 1

    def test_parses_blockquote(self):
        blocks = parse_markdown("> This is a quote")
        assert len(blocks) >= 1
        assert blocks[0]["type"] == "blockquote"
        assert "This is a quote" in blocks[0]["text"]
        assert blocks[0].get("depth", 1) >= 1

    def test_parses_table_basic(self):
        md = "| A | B |\n|---|---|\n| 1 | 2 |"
        blocks = parse_markdown(md)
        tables = [b for b in blocks if b["type"] == "table"]
        assert len(tables) == 1
        table = tables[0]
        assert table["has_header"] is True
        assert len(table["rows"]) == 2
        assert table["rows"][0] == ["A", "B"]
        assert table["rows"][1] == ["1", "2"]

    def test_parses_table_multiple_rows(self):
        md = "| H1 | H2 |\n|---|---|\n| a | b |\n| c | d |"
        blocks = parse_markdown(md)
        table = [b for b in blocks if b["type"] == "table"][0]
        assert len(table["rows"]) == 3

    def test_parses_table_normalizes_columns(self):
        md = "| A | B | C |\n|---|---|---|\n| 1 | 2 |"
        blocks = parse_markdown(md)
        table = [b for b in blocks if b["type"] == "table"][0]
        for row in table["rows"]:
            assert len(row) == 3

    def test_parses_table_empty_cells(self):
        md = "| A | B |\n|---|---|\n|  | x |"
        blocks = parse_markdown(md)
        table = [b for b in blocks if b["type"] == "table"][0]
        data_row = table["rows"][1]
        assert data_row[0] == ""
        assert data_row[1] == "x"

    def test_parses_mixed_content_order(self):
        md = "# Title\n\nParagraph\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\nEnd"
        blocks = parse_markdown(md)
        types = [b["type"] for b in blocks]
        assert types == ["heading", "paragraph", "table", "paragraph"]

    def test_parses_multiple_tables(self):
        md = "| A |\n|---|\n| 1 |\n\nMiddle\n\n| B |\n|---|\n| 2 |"
        blocks = parse_markdown(md)
        tables = [b for b in blocks if b["type"] == "table"]
        assert len(tables) == 2

    def test_strips_html(self):
        blocks = parse_markdown("<script>alert('xss')</script>")
        for block in blocks:
            assert "<script>" not in block.get("text", "")

    def test_parses_bold_and_italic(self):
        blocks = parse_markdown("**bold** and *italic* text")
        assert blocks[0]["type"] == "paragraph"
        runs = blocks[0]["runs"]
        assert any(r.get("bold") for r in runs)
        assert any(r.get("italic") for r in runs)


# ---------------------------------------------------------------------------
# extract_template_styles
# ---------------------------------------------------------------------------


class TestExtractTemplateStyles:
    def test_extracts_heading_styles(self):
        doc_response = {
            "namedStyles": {
                "styles": [
                    {
                        "namedStyleType": "HEADING_1",
                        "textStyle": {
                            "fontSize": {"magnitude": 20, "unit": "PT"},
                            "weightedFontFamily": {"fontFamily": "Arial"},
                            "foregroundColor": {
                                "color": {"rgbColor": {"red": 0, "green": 0, "blue": 0}}
                            },
                        },
                        "paragraphStyle": {"lineSpacing": 115},
                    },
                    {
                        "namedStyleType": "NORMAL_TEXT",
                        "textStyle": {
                            "fontSize": {"magnitude": 11, "unit": "PT"},
                            "weightedFontFamily": {"fontFamily": "Arial"},
                        },
                        "paragraphStyle": {"lineSpacing": 115},
                    },
                ]
            }
        }
        styles = extract_template_styles(doc_response)
        assert "HEADING_1" in styles
        assert "NORMAL_TEXT" in styles
        assert styles["HEADING_1"]["font_family"] == "Arial"
        assert styles["HEADING_1"]["font_size"] == 20

    def test_handles_missing_named_styles(self):
        assert extract_template_styles({}) == {}
