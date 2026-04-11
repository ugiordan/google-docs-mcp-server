"""Convert parsed markdown blocks to Google Docs batchUpdate requests.

Translates block/run structures from the markdown parser into insertText,
updateParagraphStyle, updateTextStyle, and createParagraphBullets requests.
This allows styled content to be written to individual tabs without replacing
the entire document (which is what .docx upload does).

All text (including tables rendered as aligned text) is inserted in a single
insertText call, then paragraph/text/bullet styles are applied by index range.
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


def blocks_to_batch_requests(blocks, tab_id=None, start_index=1):
    """Convert parsed markdown blocks to Google Docs batchUpdate requests.

    Args:
        blocks: List of parsed markdown blocks from parse_markdown()
        tab_id: Optional tab ID to scope all requests to a specific tab
        start_index: Document index to start inserting at (default: 1)

    Returns:
        List of batchUpdate request dicts ready for the API.
    """
    if not blocks:
        return []

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

        elif btype == "table":
            rows = block.get("rows", [])
            if not rows:
                continue
            block_start = idx
            col_widths = []
            for row in rows:
                for j, cell in enumerate(row):
                    width = _utf16_len(cell)
                    if j >= len(col_widths):
                        col_widths.append(width)
                    else:
                        col_widths[j] = max(col_widths[j], width)

            col_gap = 3  # spaces between columns
            for i, row in enumerate(rows):
                cells = []
                for j, cell in enumerate(row):
                    pad = col_widths[j] if j < len(col_widths) else _utf16_len(cell)
                    cells.append(cell + " " * (pad - _utf16_len(cell)))
                row_text = (" " * col_gap).join(cells) + "\n"
                text_parts.append(row_text)
                idx += _utf16_len(row_text)

                if i == 0 and block.get("has_header"):
                    total_width = sum(col_widths) + col_gap * (len(col_widths) - 1)
                    sep_text = "\u2500" * total_width + "\n"
                    text_parts.append(sep_text)
                    idx += _utf16_len(sep_text)

            block_ranges.append((block_start, idx, btype, block))

    full_text = "".join(text_parts)
    if not full_text:
        return []

    requests = []

    # 1. Insert all text at once
    requests.append(
        {"insertText": {"location": _location(start_index, tab_id), "text": full_text}}
    )

    # 2. Reset all styles to clean baseline.
    # Inserted text inherits both paragraph and character styles from the
    # insertion point, which may be a heading left over after clearing the tab.
    # Reset paragraph style to NORMAL_TEXT and clear all direct text formatting,
    # then apply specific styles on top.
    requests.append(
        {
            "updateParagraphStyle": {
                "range": _build_range(start_index, idx, tab_id),
                "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
                "fields": "namedStyleType",
            }
        }
    )
    # Clear direct character formatting (bold, italic, font size, etc.)
    # so text renders according to the named style, not inherited formatting.
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

    # 3. Apply paragraph styles
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

        elif btype == "table":
            # Apply monospace font so columns align properly
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
            # Bold the header row
            rows = block.get("rows", [])
            if block.get("has_header") and rows:
                col_gap = 3
                padded = []
                for j, cell in enumerate(rows[0]):
                    w = _utf16_len(cell)
                    cw = 0
                    for row in rows:
                        if j < len(row):
                            cw = max(cw, _utf16_len(row[j]))
                    padded.append(cell + " " * (cw - w))
                first_row_text = (" " * col_gap).join(padded) + "\n"
                header_end = start + _utf16_len(first_row_text)
                requests.append(
                    {
                        "updateTextStyle": {
                            "range": _build_range(start, header_end, tab_id),
                            "textStyle": {"bold": True},
                            "fields": "bold",
                        }
                    }
                )

    # 4. Apply text styles (bold, italic, code, strikethrough, links)
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
