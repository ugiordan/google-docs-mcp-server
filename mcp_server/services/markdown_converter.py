"""
Markdown to Google Docs converter.

This module provides functions to:
- Parse markdown content into structured blocks
- Extract template styles from existing Google Docs
- Build batch update requests for the Google Docs API
"""

import re
from html.parser import HTMLParser

import markdown


class _MarkdownHTMLParser(HTMLParser):
    """
    Custom HTML parser to extract structured blocks from markdown-generated HTML.
    """

    def __init__(self):
        super().__init__()
        self.blocks = []
        self.current_tag = None
        self.current_text = []
        self.current_attrs = {}
        self.list_type = None  # 'ul' or 'ol'
        self.in_code_block = False
        self.code_block_text = []

    def handle_starttag(self, tag, attrs):
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self.current_tag = tag
            self.current_text = []
        elif tag == "p":
            self.current_tag = "p"
            self.current_text = []
        elif tag in ("ul", "ol"):
            self.list_type = tag
        elif tag == "li":
            self.current_tag = "li"
            self.current_text = []
        elif tag == "pre":
            self.in_code_block = True
            self.code_block_text = []
        elif tag == "code" and not self.in_code_block:
            # Inline code - just continue collecting text
            pass
        elif tag in ("strong", "b", "em", "i"):
            # Track inline formatting but continue collecting text
            pass
        # Ignore other tags (like script, style, etc.)

    def handle_endtag(self, tag):
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            level = int(tag[1])
            text = "".join(self.current_text).strip()
            if text:
                self.blocks.append(
                    {
                        "type": "heading",
                        "level": level,
                        "text": text,
                    }
                )
            self.current_tag = None
            self.current_text = []
        elif tag == "p":
            text = "".join(self.current_text).strip()
            if text:
                self.blocks.append(
                    {
                        "type": "paragraph",
                        "text": text,
                    }
                )
            self.current_tag = None
            self.current_text = []
        elif tag == "li":
            text = "".join(self.current_text).strip()
            if text:
                self.blocks.append(
                    {
                        "type": "list_item",
                        "text": text,
                        "ordered": self.list_type == "ol",
                    }
                )
            self.current_tag = None
            self.current_text = []
        elif tag in ("ul", "ol"):
            self.list_type = None
        elif tag == "pre":
            text = "".join(self.code_block_text).strip()
            if text:
                self.blocks.append(
                    {
                        "type": "code_block",
                        "text": text,
                    }
                )
            self.in_code_block = False
            self.code_block_text = []

    def handle_data(self, data):
        if self.in_code_block:
            self.code_block_text.append(data)
        elif self.current_tag:
            self.current_text.append(data)


def parse_markdown(content: str) -> list[dict]:
    """
    Parse markdown content into structured blocks.

    Args:
        content: Markdown text to parse

    Returns:
        List of block dicts with type, text, and optional metadata (level, ordered)
    """
    # Initialize markdown parser with safe extensions, raw HTML stripped
    md = markdown.Markdown(
        extensions=["tables", "fenced_code", "toc", "nl2br"],
        output_format="html",
    )
    # Strip any raw HTML tags from input before conversion
    content = re.sub(r"<[^>]+>", "", content)

    # Convert markdown to HTML
    html = md.convert(content)

    # Parse HTML into structured blocks
    parser = _MarkdownHTMLParser()
    parser.feed(html)

    return parser.blocks


def extract_template_styles(doc_response: dict) -> dict:
    """
    Extract style information from a Google Doc template.

    Args:
        doc_response: Google Docs API response containing namedStyles

    Returns:
        Dict mapping style type names to style properties
    """
    if "namedStyles" not in doc_response:
        return {}

    styles = {}
    named_styles = doc_response.get("namedStyles", {}).get("styles", [])

    for style in named_styles:
        style_type = style.get("namedStyleType")
        if not style_type:
            continue

        text_style = style.get("textStyle", {})
        paragraph_style = style.get("paragraphStyle", {})

        style_props = {}

        # Extract font family
        weighted_font = text_style.get("weightedFontFamily", {})
        if "fontFamily" in weighted_font:
            style_props["font_family"] = weighted_font["fontFamily"]

        # Extract font size
        font_size = text_style.get("fontSize", {})
        if "magnitude" in font_size:
            style_props["font_size"] = font_size["magnitude"]

        # Extract line spacing
        if "lineSpacing" in paragraph_style:
            style_props["line_spacing"] = paragraph_style["lineSpacing"]

        # Extract foreground color
        fg_color = text_style.get("foregroundColor", {})
        if "color" in fg_color:
            style_props["foreground_color"] = fg_color["color"]

        if style_props:
            styles[style_type] = style_props

    return styles


def build_batch_update_requests(
    blocks: list[dict], styles: dict | None = None
) -> list[dict]:
    """
    Build Google Docs API batchUpdate requests from parsed blocks.

    Args:
        blocks: List of parsed markdown blocks
        styles: Optional template styles to apply

    Returns:
        List of request dicts for documents.batchUpdate
    """
    if not blocks:
        return []

    requests = []
    current_index = 1  # Start at index 1 (after the implicit newline at doc start)

    # Map heading levels to named style types
    level_to_style = {
        1: "HEADING_1",
        2: "HEADING_2",
        3: "HEADING_3",
        4: "HEADING_4",
        5: "HEADING_5",
        6: "HEADING_6",
    }

    # Insert all text first (in order)
    for block in blocks:
        text = block.get("text", "")
        if not text:
            continue

        # Insert text with newline
        requests.append(
            {
                "insertText": {
                    "location": {"index": current_index},
                    "text": text + "\n",
                }
            }
        )

        # Track the text length for style application
        block["_start_index"] = current_index
        block["_end_index"] = current_index + len(text)
        current_index += len(text) + 1  # +1 for newline

    # Apply styles if provided
    if styles:
        for block in blocks:
            if "_start_index" not in block:
                continue

            start_index = block["_start_index"]
            end_index = block["_end_index"]

            # Determine the named style type
            if block["type"] == "heading":
                level = block.get("level", 1)
                style_type = level_to_style.get(level, "HEADING_1")
            elif block["type"] == "paragraph":
                style_type = "NORMAL_TEXT"
            else:
                # For list items and code blocks, use normal text for now
                style_type = "NORMAL_TEXT"

            # Apply paragraph style if available
            if style_type in styles:
                style_props = styles[style_type]

                # Build text style update
                text_style = {}
                if "font_family" in style_props:
                    text_style["weightedFontFamily"] = {
                        "fontFamily": style_props["font_family"]
                    }
                if "font_size" in style_props:
                    text_style["fontSize"] = {
                        "magnitude": style_props["font_size"],
                        "unit": "PT",
                    }
                if "foreground_color" in style_props:
                    text_style["foregroundColor"] = {
                        "color": style_props["foreground_color"]
                    }

                if text_style:
                    requests.append(
                        {
                            "updateTextStyle": {
                                "range": {
                                    "startIndex": start_index,
                                    "endIndex": end_index,
                                },
                                "textStyle": text_style,
                                "fields": ",".join(text_style.keys()),
                            }
                        }
                    )

                # Build paragraph style update
                paragraph_style = {}
                if "line_spacing" in style_props:
                    paragraph_style["lineSpacing"] = style_props["line_spacing"]

                if paragraph_style:
                    requests.append(
                        {
                            "updateParagraphStyle": {
                                "range": {
                                    "startIndex": start_index,
                                    "endIndex": end_index,
                                },
                                "paragraphStyle": paragraph_style,
                                "fields": ",".join(paragraph_style.keys()),
                            }
                        }
                    )

    return requests
