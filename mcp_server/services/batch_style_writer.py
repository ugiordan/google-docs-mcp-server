"""Convert parsed markdown blocks to Google Docs batchUpdate requests.

Translates block/run structures from the markdown parser into insertText,
updateParagraphStyle, updateTextStyle, createParagraphBullets, and insertTable
requests. This allows styled content to be written to individual tabs without
replacing the entire document (which is what .docx upload does).

Content is split into text segments (headings, paragraphs, code blocks, etc.)
and table segments. Segments are processed in reverse document order, each
inserting at start_index, so they push earlier-inserted content forward.
This avoids cross-segment index dependencies.
"""


def _utf16_len(text):
    """Calculate length in UTF-16 code units (Google Docs API offset unit)."""
    return len(text.encode("utf-16-le")) // 2


_HEADING_STYLE_MAP = {
    1: "HEADING_1",
    2: "HEADING_2",
    3: "HEADING_3",
    4: "HEADING_4",
    5: "HEADING_5",
    6: "HEADING_6",
}


def _build_range(start, end, tab_id=None):
    """Build a range dict, optionally scoped to a tab."""
    r = {"startIndex": start, "endIndex": end}
    if tab_id:
        r["tabId"] = tab_id
    return r


def _location(index, tab_id=None):
    """Build a location dict, optionally scoped to a tab."""
    loc = {"index": index}
    if tab_id:
        loc["tabId"] = tab_id
    return loc


def _cell_index(table_start, row, col, num_cols):
    """Paragraph index of cell (row, col) in an empty table.

    Table structure per row: ROW_START + (CELL_START + PARAGRAPH) * num_cols.
    First cell paragraph is at table_start + 3 (TABLE + ROW + CELL + PARAGRAPH
    where PARAGRAPH is the target index).
    """
    return table_start + 3 + row * (1 + 2 * num_cols) + 2 * col


def _build_text_segment_requests(blocks, start_index, tab_id):
    """Build requests for a consecutive run of non-table blocks.

    Produces a single insertText with all text, then style resets, then
    paragraph and character style requests.
    """
    text_parts = []
    block_ranges = []
    run_ranges = []
    idx = start_index

    for block in blocks:
        btype = block["type"]

        if btype in ("heading", "paragraph", "list_item", "blockquote"):
            runs = block.get("runs", [{"text": block.get("text", "")}])
            block_start = idx

            for run_data in runs:
                text = run_data.get("text", "")
                if not text:
                    continue
                run_start = idx
                text_parts.append(text)
                idx += _utf16_len(text)
                run_ranges.append((run_start, idx, run_data))

            text_parts.append("\n")
            idx += 1
            block_ranges.append((block_start, idx, btype, block))

        elif btype == "code_block":
            text = block.get("text", "")
            block_start = idx
            text_parts.append(text)
            idx += _utf16_len(text)
            text_parts.append("\n")
            idx += 1
            block_ranges.append((block_start, idx, btype, block))

        elif btype == "horizontal_rule":
            separator = "\u2500" * 40 + "\n"
            block_start = idx
            text_parts.append(separator)
            idx += _utf16_len(separator)
            block_ranges.append((block_start, idx, btype, block))

    full_text = "".join(text_parts)
    if not full_text:
        return []

    requests = []

    # 1. Insert all text at once
    requests.append(
        {"insertText": {"location": _location(start_index, tab_id), "text": full_text}}
    )

    # 2. Reset paragraph styles to NORMAL_TEXT
    requests.append(
        {
            "updateParagraphStyle": {
                "range": _build_range(start_index, idx, tab_id),
                "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
                "fields": "namedStyleType",
            }
        }
    )
    # 3. Clear direct character formatting
    text_end = idx - 1 if idx > start_index + 1 else idx
    requests.append(
        {
            "updateTextStyle": {
                "range": _build_range(start_index, text_end, tab_id),
                "textStyle": {},
                "fields": "bold,italic,strikethrough,underline,fontSize,"
                "weightedFontFamily,foregroundColor,link",
            }
        }
    )

    # 4. Apply paragraph styles
    for start, end, btype, block in block_ranges:
        if btype == "heading":
            level = block.get("level", 1)
            named_style = _HEADING_STYLE_MAP.get(level, "HEADING_1")
            requests.append(
                {
                    "updateParagraphStyle": {
                        "range": _build_range(start, end, tab_id),
                        "paragraphStyle": {"namedStyleType": named_style},
                        "fields": "namedStyleType",
                    }
                }
            )

        elif btype == "code_block":
            if end - 1 > start:
                requests.append(
                    {
                        "updateTextStyle": {
                            "range": _build_range(start, end - 1, tab_id),
                            "textStyle": {
                                "weightedFontFamily": {"fontFamily": "Courier New"},
                                "fontSize": {"magnitude": 9, "unit": "PT"},
                            },
                            "fields": "weightedFontFamily,fontSize",
                        }
                    }
                )

        elif btype == "list_item":
            ordered = block.get("ordered", False)
            nesting_level = block.get("nesting_level", 0)
            bullet_preset = (
                "NUMBERED_DECIMAL_ALPHA_ROMAN"
                if ordered
                else "BULLET_DISC_CIRCLE_SQUARE"
            )
            requests.append(
                {
                    "createParagraphBullets": {
                        "range": _build_range(start, end, tab_id),
                        "bulletPreset": bullet_preset,
                    }
                }
            )
            if nesting_level > 0:
                indent_pt = 36 * nesting_level
                requests.append(
                    {
                        "updateParagraphStyle": {
                            "range": _build_range(start, end, tab_id),
                            "paragraphStyle": {
                                "indentStart": {
                                    "magnitude": indent_pt,
                                    "unit": "PT",
                                },
                            },
                            "fields": "indentStart",
                        }
                    }
                )

        elif btype == "blockquote":
            depth = block.get("depth", 1)
            indent_pt = 36 * depth
            requests.append(
                {
                    "updateParagraphStyle": {
                        "range": _build_range(start, end, tab_id),
                        "paragraphStyle": {
                            "indentStart": {"magnitude": indent_pt, "unit": "PT"},
                        },
                        "fields": "indentStart",
                    }
                }
            )

    # 5. Apply text styles (bold, italic, code, strikethrough, links)
    for start, end, run_data in run_ranges:
        if start >= end:
            continue

        style_fields = []
        text_style = {}

        if run_data.get("bold"):
            text_style["bold"] = True
            style_fields.append("bold")
        if run_data.get("italic"):
            text_style["italic"] = True
            style_fields.append("italic")
        if run_data.get("strikethrough"):
            text_style["strikethrough"] = True
            style_fields.append("strikethrough")
        if run_data.get("code"):
            text_style["weightedFontFamily"] = {"fontFamily": "Courier New"}
            text_style["fontSize"] = {"magnitude": 9, "unit": "PT"}
            style_fields.extend(["weightedFontFamily", "fontSize"])
        if run_data.get("link"):
            text_style["link"] = {"url": run_data["link"]}
            style_fields.append("link")

        if style_fields:
            requests.append(
                {
                    "updateTextStyle": {
                        "range": _build_range(start, end, tab_id),
                        "textStyle": text_style,
                        "fields": ",".join(style_fields),
                    }
                }
            )

    return requests


def _build_table_requests(block, start_index, tab_id):
    """Build requests for a native Google Doc table.

    Uses insertTable to create the table structure, then fills cells with
    insertText in reverse order (last cell first) so each insertion doesn't
    shift indices of cells we haven't processed yet. Header cells get bold
    styling applied immediately after their text insertion.
    """
    rows = block.get("rows", [])
    if not rows:
        return []

    num_rows = len(rows)
    num_cols = max((len(r) for r in rows), default=0)
    if num_cols == 0:
        return []

    requests = []

    # 1. Insert empty table
    requests.append(
        {
            "insertTable": {
                "rows": num_rows,
                "columns": num_cols,
                "location": _location(start_index, tab_id),
            }
        }
    )

    # insertTable at index N creates the TABLE element at N+1
    table_start = start_index + 1

    # 2. Fill cells in reverse order (last row/col first) and style headers
    has_header = block.get("has_header", False)
    for r in range(num_rows - 1, -1, -1):
        for c in range(num_cols - 1, -1, -1):
            cell_text = rows[r][c] if c < len(rows[r]) else ""
            if not cell_text:
                continue
            ci = _cell_index(table_start, r, c, num_cols)
            requests.append(
                {
                    "insertText": {
                        "location": _location(ci, tab_id),
                        "text": cell_text,
                    }
                }
            )
            if r == 0 and has_header:
                requests.append(
                    {
                        "updateTextStyle": {
                            "range": _build_range(
                                ci, ci + _utf16_len(cell_text), tab_id
                            ),
                            "textStyle": {"bold": True},
                            "fields": "bold",
                        }
                    }
                )

    return requests


def blocks_to_batch_requests(blocks, tab_id=None, start_index=1):
    """Convert parsed markdown blocks to Google Docs batchUpdate requests.

    Splits blocks into text segments (headings, paragraphs, code blocks, etc.)
    and table segments. Segments are processed in reverse document order, each
    inserting at start_index. This means each segment's internal index
    calculations are independent: no segment needs to know another's size.

    Args:
        blocks: List of parsed markdown blocks from parse_markdown()
        tab_id: Optional tab ID to scope all requests to a specific tab
        start_index: Document index to start inserting at (default: 1)

    Returns:
        List of batchUpdate request dicts ready for the API.
    """
    if not blocks:
        return []

    # Split into text and table segments
    segments = []
    current_text_blocks = []
    for block in blocks:
        if block["type"] == "table":
            if current_text_blocks:
                segments.append(("text", current_text_blocks))
                current_text_blocks = []
            segments.append(("table", block))
        else:
            current_text_blocks.append(block)
    if current_text_blocks:
        segments.append(("text", current_text_blocks))

    # Process in reverse document order so each segment inserts at start_index
    # and pushes previously-inserted content forward
    requests = []
    for seg_type, seg_data in reversed(segments):
        if seg_type == "text":
            requests.extend(
                _build_text_segment_requests(seg_data, start_index, tab_id)
            )
        else:
            requests.extend(_build_table_requests(seg_data, start_index, tab_id))

    return requests
