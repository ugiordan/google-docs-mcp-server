"""Markdown parser and template style extractor.

Parses markdown into structured blocks with inline formatting (bold, italic,
code, links, strikethrough). Used by docx_converter to generate .docx files
for upload to Google Drive.
"""

import re
from html.parser import HTMLParser

import markdown


def _strip_runs(runs):
    """Strip leading/trailing whitespace from a run list."""
    if not runs:
        return []
    result = [dict(r) for r in runs]
    # Strip leading whitespace
    while result:
        text = result[0]["text"].lstrip()
        if text:
            result[0] = {**result[0], "text": text}
            break
        result.pop(0)
    else:
        return []
    # Strip trailing whitespace
    while result:
        text = result[-1]["text"].rstrip()
        if text:
            result[-1] = {**result[-1], "text": text}
            break
        result.pop()
    else:
        return []
    return result


_HEADING_TAGS = frozenset(("h1", "h2", "h3", "h4", "h5", "h6"))
_BOLD_TAGS = frozenset(("strong", "b"))
_ITALIC_TAGS = frozenset(("em", "i"))
_STRIKE_TAGS = frozenset(("del", "s"))


class _MarkdownHTMLParser(HTMLParser):
    """Parse markdown-generated HTML into structured blocks with formatting.

    Produces blocks of these types:
    - heading: {type, level, text, runs}
    - paragraph: {type, text, runs}
    - list_item: {type, ordered, nesting_level, text, runs}
    - code_block: {type, text}
    - table: {type, rows (list of list of str), has_header}
    - blockquote: {type, depth, text, runs}
    - horizontal_rule: {type}

    Runs track inline formatting: bold, italic, code, strikethrough, link.
    """

    def __init__(self):
        super().__init__()
        self.blocks = []

        # Inline formatting state
        self.bold = False
        self.italic = False
        self.inline_code = False
        self.strikethrough = False
        self.link_url = None

        # Current block accumulator
        self.current_runs = []
        self.block_type = None
        self.block_meta = {}

        # List nesting
        self.list_stack = []

        # Table state
        self.in_table = False
        self.table_rows = []
        self.current_row = []
        self.in_cell = False
        self.cell_text_parts = []
        self.table_has_header = False

        # Code block
        self.in_code_block = False
        self.code_text = []

        # Blockquote
        self.blockquote_depth = 0

    def _reset_inline_state(self):
        """Reset inline formatting and start fresh runs for a new block."""
        self.bold = False
        self.italic = False
        self.inline_code = False
        self.strikethrough = False
        self.link_url = None
        self.current_runs = []

    def _make_run(self, text):
        """Create a formatting run with current inline state."""
        if not text:
            return None
        run = {"text": text}
        if self.bold:
            run["bold"] = True
        if self.italic:
            run["italic"] = True
        if self.inline_code:
            run["code"] = True
        if self.strikethrough:
            run["strikethrough"] = True
        if self.link_url:
            run["link"] = self.link_url
        return run

    def _flush_block(self, block_type=None, **extra_meta):
        """Emit the current runs as a block."""
        bt = block_type or self.block_type
        if not bt:
            return
        runs = _strip_runs(self.current_runs)
        self.current_runs = []
        if not runs:
            return
        text = "".join(r["text"] for r in runs)
        block = {"type": bt, "text": text, "runs": runs}
        block.update(self.block_meta)
        block.update(extra_meta)
        self.blocks.append(block)

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)

        # Code block
        if tag == "pre":
            self.in_code_block = True
            self.code_text = []
            return
        if self.in_code_block:
            return

        # Table handling
        if tag == "table":
            self.in_table = True
            self.table_rows = []
            self.table_has_header = False
            return
        if self.in_table:
            if tag == "tr":
                self.current_row = []
            elif tag in ("td", "th"):
                self.in_cell = True
                self.cell_text_parts = []
                if tag == "th":
                    self.table_has_header = True
            # thead, tbody: no special handling needed
            return

        # Block-level elements
        if tag in _HEADING_TAGS:
            self.block_type = "heading"
            self.block_meta = {"level": int(tag[1])}
            self._reset_inline_state()
        elif tag == "p":
            if self.blockquote_depth > 0:
                self.block_type = "blockquote"
                self.block_meta = {"depth": self.blockquote_depth}
            else:
                self.block_type = "paragraph"
                self.block_meta = {}
            self._reset_inline_state()
        elif tag in ("ul", "ol"):
            self.list_stack.append(tag)
        elif tag == "li":
            # Flush any in-progress list item (handles nested lists)
            if self.block_type == "list_item" and self.current_runs:
                self._flush_block()
            self.block_type = "list_item"
            self.block_meta = {
                "ordered": self.list_stack[-1] == "ol" if self.list_stack else False,
                "nesting_level": max(0, len(self.list_stack) - 1),
            }
            self._reset_inline_state()
        elif tag == "blockquote":
            self.blockquote_depth += 1
        elif tag == "hr":
            self.blocks.append({"type": "horizontal_rule"})

        # Inline formatting
        elif tag in _BOLD_TAGS:
            self.bold = True
        elif tag in _ITALIC_TAGS:
            self.italic = True
        elif tag == "code":
            self.inline_code = True
        elif tag in _STRIKE_TAGS:
            self.strikethrough = True
        elif tag == "a":
            self.link_url = attrs_dict.get("href")
        elif tag == "img":
            alt = attrs_dict.get("alt", "")
            if alt and self.block_type:
                run = self._make_run(f"[Image: {alt}]")
                if run:
                    self.current_runs.append(run)
        elif tag == "br":
            if self.in_table and self.in_cell:
                self.cell_text_parts.append(" ")
            elif self.block_type:
                # Use vertical tab (\v) for soft line break within a paragraph.
                # Google Docs renders \v as a line break without paragraph spacing,
                # unlike \n which creates a new paragraph.
                run = self._make_run("\v")
                if run:
                    self.current_runs.append(run)

    def handle_endtag(self, tag):
        # Code block
        if tag == "pre":
            text = "".join(self.code_text).strip()
            if text:
                self.blocks.append({"type": "code_block", "text": text})
            self.in_code_block = False
            self.code_text = []
            return
        if self.in_code_block:
            return

        # Table handling
        if self.in_table:
            if tag in ("td", "th"):
                cell_text = "".join(self.cell_text_parts).strip()
                self.current_row.append(cell_text)
                self.in_cell = False
                self.cell_text_parts = []
            elif tag == "tr":
                if self.current_row:
                    self.table_rows.append(self.current_row)
                self.current_row = []
            elif tag == "table":
                if self.table_rows:
                    max_cols = max(len(r) for r in self.table_rows)
                    normalized = [
                        row + [""] * (max_cols - len(row)) for row in self.table_rows
                    ]
                    self.blocks.append(
                        {
                            "type": "table",
                            "rows": normalized,
                            "has_header": self.table_has_header,
                        }
                    )
                self.in_table = False
                self.table_rows = []
            # thead, tbody: no special handling
            return

        # Block-level end tags
        if tag in _HEADING_TAGS:
            self._flush_block("heading")
            self.block_type = None
            self.block_meta = {}
        elif tag == "p":
            bt = "blockquote" if self.blockquote_depth > 0 else "paragraph"
            self._flush_block(bt)
            self.block_type = None
            self.block_meta = {}
        elif tag == "li":
            self._flush_block("list_item")
            self.block_type = None
            self.block_meta = {}
        elif tag in ("ul", "ol"):
            if self.list_stack:
                self.list_stack.pop()
        elif tag == "blockquote":
            self.blockquote_depth = max(0, self.blockquote_depth - 1)

        # Inline formatting
        elif tag in _BOLD_TAGS:
            self.bold = False
        elif tag in _ITALIC_TAGS:
            self.italic = False
        elif tag == "code":
            self.inline_code = False
        elif tag in _STRIKE_TAGS:
            self.strikethrough = False
        elif tag == "a":
            self.link_url = None

    def handle_data(self, data):
        if self.in_code_block:
            self.code_text.append(data)
            return
        if self.in_table and self.in_cell:
            self.cell_text_parts.append(data)
            return
        if self.block_type:
            # nl2br produces "<br />\n" in HTML. The <br> handler already
            # emits a \v soft break, so strip the trailing \n from data
            # to avoid a double line break (one soft + one paragraph).
            data = data.replace("\n", "")
            run = self._make_run(data)
            if run:
                self.current_runs.append(run)


def parse_markdown(content: str) -> list[dict]:
    """Parse markdown content into structured blocks.

    Args:
        content: Markdown text to parse

    Returns:
        List of block dicts with type, text/runs, and optional metadata
    """
    md = markdown.Markdown(
        extensions=["tables", "fenced_code", "toc", "nl2br"],
        output_format="html",
    )
    # Strip raw HTML tags from input, but preserve <br> for line breaks
    content = re.sub(r"<(?!br\s*/?\s*>)[^>]+>", "", content)
    # Strip trailing backslashes used as markdown line breaks.
    # With nl2br enabled, every newline already becomes <br>, so the
    # backslash is redundant and would render as a literal "\" character.
    content = re.sub(r"\\\n", "\n", content)
    html = md.convert(content)

    parser = _MarkdownHTMLParser()
    parser.feed(html)
    return parser.blocks


def extract_template_styles(doc_response: dict) -> dict:
    """Extract style information from a Google Doc template.

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
