"""Diff-based document tab updater that preserves comment anchors.

Instead of deleting all content and re-inserting from scratch, computes a
paragraph-level diff between current document content and new markdown blocks.
Only changed regions are modified, preserving comment anchors on unchanged text.
"""

from difflib import SequenceMatcher

from mcp_server.services.batch_style_writer import (
    _build_range,
    _utf16_len,
    blocks_to_batch_requests,
)


def _get_tab_body(doc_response, tab_id):
    """Get the body content list for a specific tab."""
    from mcp_server.services.google_docs_service import GoogleDocsService

    for tab in doc_response.get("tabs", []):
        found = GoogleDocsService._find_tab_recursive(tab, tab_id)
        if found:
            return found.get("documentTab", {}).get("body", {}).get("content", [])
    raise ValueError(f"Tab '{tab_id}' not found")


def _extract_paragraph_text(paragraph):
    """Extract the full text of a paragraph element."""
    return "".join(
        elem.get("textRun", {}).get("content", "")
        for elem in paragraph.get("elements", [])
    )


def _extract_table_fingerprint(table):
    """Serialize table content for diff comparison."""
    parts = []
    for row in table.get("tableRows", []):
        row_parts = []
        for cell in row.get("tableCells", []):
            cell_text = ""
            for content in cell.get("content", []):
                if "paragraph" in content:
                    cell_text += _extract_paragraph_text(content["paragraph"])
            row_parts.append(cell_text)
        parts.append("\t".join(row_parts))
    return "\n".join(parts)


def doc_elements(body_content):
    """Extract structural elements from document body for diffing.

    Returns list of dicts with:
        text: content text (for paragraphs) or fingerprint (for tables)
        start: startIndex in the document
        end: endIndex in the document
        type: "paragraph" or "table"
    """
    elements = []
    for item in body_content:
        start = item.get("startIndex", 0)
        end = item.get("endIndex", 0)
        if start == 0:
            continue

        if "paragraph" in item:
            text = _extract_paragraph_text(item["paragraph"])
            elements.append(
                {"text": text, "start": start, "end": end, "type": "paragraph"}
            )

        elif "table" in item:
            text = _extract_table_fingerprint(item["table"])
            elements.append({"text": text, "start": start, "end": end, "type": "table"})

    return elements


def block_elements(blocks):
    """Convert parsed markdown blocks to comparable elements.

    Each block produces one or more elements. Code blocks produce an extra
    spacer element (matching what blocks_to_batch_requests inserts).
    Tables produce the same fingerprint format as doc_elements.

    Returns list of dicts with:
        text: content text or fingerprint
        block_idx: index into the blocks list
        is_spacer: True for code block spacer paragraphs
    """
    elements = []
    for i, block in enumerate(blocks):
        btype = block["type"]

        if btype in ("heading", "paragraph", "list_item", "blockquote"):
            runs = block.get("runs", [{"text": block.get("text", "")}])
            text = "".join(r.get("text", "") for r in runs) + "\n"
            elements.append({"text": text, "block_idx": i, "is_spacer": False})

        elif btype == "code_block":
            text = block.get("text", "") + "\n"
            elements.append({"text": text, "block_idx": i, "is_spacer": False})
            elements.append({"text": "\n", "block_idx": i, "is_spacer": True})

        elif btype == "horizontal_rule":
            text = "─" * 40 + "\n"
            elements.append({"text": text, "block_idx": i, "is_spacer": False})

        elif btype == "table":
            rows = block.get("rows", [])
            row_parts = []
            for row in rows:
                row_parts.append("\t".join(row))
            text = "\n".join(row_parts)
            elements.append({"text": text, "block_idx": i, "is_spacer": False})
            elements.append({"text": "\n", "block_idx": i, "is_spacer": True})

    return elements


def _blocks_for_target_range(target_elems, blocks, j1, j2):
    """Get the unique blocks corresponding to target elements j1..j2."""
    seen = set()
    result = []
    for j in range(j1, j2):
        elem = target_elems[j]
        if elem["is_spacer"]:
            continue
        idx = elem["block_idx"]
        if idx not in seen:
            seen.add(idx)
            result.append(blocks[idx])
    return result


def compute_diff_requests(doc_response, tab_id, blocks):
    """Compute batchUpdate requests using paragraph-level diff.

    Compares the current tab content against the target blocks and generates
    minimal batchUpdate requests that only touch changed regions.

    Args:
        doc_response: Full document API response (with includeTabsContent=True)
        tab_id: The tab to update
        blocks: Parsed markdown blocks from parse_markdown()

    Returns:
        List of batchUpdate request dicts, or None if full replacement
        is more efficient (nothing in common between old and new content).
    """
    body_content = _get_tab_body(doc_response, tab_id)
    current = doc_elements(body_content)
    target = block_elements(blocks)

    if not current and not target:
        return []

    current_texts = [e["text"] for e in current]
    target_texts = [e["text"] for e in target]

    matcher = SequenceMatcher(None, current_texts, target_texts)
    opcodes = matcher.get_opcodes()

    equal_count = sum(1 for tag, _, _, _, _ in opcodes if tag == "equal")
    if equal_count == 0:
        return None

    doc_end = current[-1]["end"] if current else 2

    requests = []

    for tag, i1, i2, j1, j2 in reversed(opcodes):
        if tag == "equal":
            continue

        if tag == "delete":
            start = current[i1]["start"]
            end = current[i2 - 1]["end"]
            if end >= doc_end:
                end -= 1
            if end > start:
                requests.append(
                    {"deleteContentRange": {"range": _build_range(start, end, tab_id)}}
                )

        elif tag == "insert":
            if i1 < len(current):
                insert_at = current[i1]["start"]
            elif current:
                insert_at = max(current[-1]["end"] - 1, 1)
            else:
                insert_at = 1

            new_blocks = _blocks_for_target_range(target, blocks, j1, j2)
            if new_blocks:
                styled = blocks_to_batch_requests(
                    new_blocks, tab_id=tab_id, start_index=insert_at
                )
                requests.extend(styled)

        elif tag == "replace":
            start = current[i1]["start"]
            end = current[i2 - 1]["end"]
            if end >= doc_end:
                end -= 1
            if end > start:
                requests.append(
                    {"deleteContentRange": {"range": _build_range(start, end, tab_id)}}
                )

            new_blocks = _blocks_for_target_range(target, blocks, j1, j2)
            if new_blocks:
                styled = blocks_to_batch_requests(
                    new_blocks, tab_id=tab_id, start_index=start
                )
                requests.extend(styled)

    return requests


def compute_text_length(blocks):
    """Compute the total UTF-16 length of text that blocks would produce.

    Used to estimate whether diff is worthwhile vs full replacement.
    """
    total = 0
    for block in blocks:
        btype = block["type"]
        if btype in ("heading", "paragraph", "list_item", "blockquote"):
            runs = block.get("runs", [{"text": block.get("text", "")}])
            for r in runs:
                total += _utf16_len(r.get("text", ""))
            total += 1  # trailing \n
        elif btype == "code_block":
            total += _utf16_len(block.get("text", ""))
            total += 2  # \n + spacer \n
        elif btype == "horizontal_rule":
            total += _utf16_len("─" * 40) + 1
        elif btype == "table":
            for row in block.get("rows", []):
                for cell in row:
                    total += _utf16_len(cell)
    return total
