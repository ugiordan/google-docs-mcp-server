from mcp_server.services.markdown_converter import (
    build_batch_update_requests,
    extract_template_styles,
    parse_markdown,
)


class TestParseMarkdown:
    def test_parses_heading(self):
        blocks = parse_markdown("# Hello World")
        assert len(blocks) >= 1
        assert blocks[0]["type"] == "heading"
        assert blocks[0]["level"] == 1
        assert blocks[0]["text"] == "Hello World"

    def test_parses_paragraph(self):
        blocks = parse_markdown("Just some text.")
        assert len(blocks) >= 1
        assert blocks[0]["type"] == "paragraph"
        assert blocks[0]["text"] == "Just some text."

    def test_parses_multiple_headings(self):
        md = "# H1\n\n## H2\n\n### H3"
        blocks = parse_markdown(md)
        headings = [b for b in blocks if b["type"] == "heading"]
        assert len(headings) == 3
        assert headings[0]["level"] == 1
        assert headings[1]["level"] == 2
        assert headings[2]["level"] == 3

    def test_parses_unordered_list(self):
        md = "- item one\n- item two\n- item three"
        blocks = parse_markdown(md)
        list_items = [b for b in blocks if b["type"] == "list_item"]
        assert len(list_items) == 3

    def test_parses_ordered_list(self):
        md = "1. first\n2. second\n3. third"
        blocks = parse_markdown(md)
        list_items = [b for b in blocks if b["type"] == "list_item"]
        assert len(list_items) == 3

    def test_parses_code_block(self):
        md = "```python\nprint('hello')\n```"
        blocks = parse_markdown(md)
        code_blocks = [b for b in blocks if b["type"] == "code_block"]
        assert len(code_blocks) == 1
        assert "print('hello')" in code_blocks[0]["text"]

    def test_strips_html(self):
        """HTML extension is disabled — raw HTML should be treated as text."""
        blocks = parse_markdown("<script>alert('xss')</script>")
        # Should not parse as HTML - should be plain text or stripped
        for block in blocks:
            assert "<script>" not in block.get("text", "")

    def test_parses_bold_and_italic(self):
        blocks = parse_markdown("**bold** and *italic* text")
        assert len(blocks) >= 1
        # Should have inline formatting info
        paragraph = blocks[0]
        assert paragraph["type"] == "paragraph"


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
                        "paragraphStyle": {
                            "lineSpacing": 115,
                        },
                    },
                    {
                        "namedStyleType": "NORMAL_TEXT",
                        "textStyle": {
                            "fontSize": {"magnitude": 11, "unit": "PT"},
                            "weightedFontFamily": {"fontFamily": "Arial"},
                        },
                        "paragraphStyle": {
                            "lineSpacing": 115,
                        },
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
        styles = extract_template_styles({})
        assert styles == {}


class TestBuildBatchUpdateRequests:
    def test_generates_insert_text_requests(self):
        blocks = [
            {"type": "paragraph", "text": "Hello world"},
        ]
        requests = build_batch_update_requests(blocks)
        assert len(requests) > 0
        # Should have insertText request
        insert_reqs = [r for r in requests if "insertText" in r]
        assert len(insert_reqs) >= 1

    def test_generates_heading_style_requests(self):
        blocks = [
            {"type": "heading", "level": 1, "text": "Title"},
        ]
        styles = {
            "HEADING_1": {
                "font_family": "Arial",
                "font_size": 20,
                "line_spacing": 115,
            }
        }
        requests = build_batch_update_requests(blocks, styles)
        # Should have both insertText and updateParagraphStyle requests
        assert len(requests) > 1

    def test_empty_blocks_returns_empty_requests(self):
        requests = build_batch_update_requests([])
        assert requests == []
