"""Markdown to Google Slides converter."""

import re


def split_slides(markdown: str) -> list[str]:
    """Split markdown into slide chunks on --- separators.

    Skips --- inside fenced code blocks (triple backtick regions).
    """
    chunks = []
    current_chunk = []
    in_code_block = False

    for line in markdown.split("\n"):
        stripped = line.strip()

        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_code_block = not in_code_block

        if not in_code_block and re.match(r"^-{3,}\s*$", stripped):
            chunk_text = "\n".join(current_chunk).strip()
            if chunk_text:
                chunks.append(chunk_text)
            current_chunk = []
        else:
            current_chunk.append(line)

    chunk_text = "\n".join(current_chunk).strip()
    if chunk_text:
        chunks.append(chunk_text)

    return chunks


def extract_speaker_notes(chunk: str) -> tuple[str, str]:
    """Extract :::notes block from a slide chunk.

    Returns (content_without_notes, speaker_notes).
    """
    notes_pattern = re.compile(
        r"^:::notes\s*\n(.*?)\n^:::\s*$", re.MULTILINE | re.DOTALL
    )
    match = notes_pattern.search(chunk)
    if match:
        notes = match.group(1).strip()
        content = chunk[: match.start()] + chunk[match.end() :]
        return content.strip(), notes
    return chunk, ""


def parse_slide_chunk(chunk: str) -> dict:
    """Parse a single slide chunk into a slide dict.

    Returns {title, body_text, speaker_notes}.
    """
    content, speaker_notes = extract_speaker_notes(chunk)

    lines = content.split("\n")
    title = ""
    body_lines = []

    for line in lines:
        heading_match = re.match(r"^#{1,2}\s+(.+)$", line)
        if heading_match and not title:
            title = heading_match.group(1).strip()
        else:
            body_lines.append(line)

    body_text = "\n".join(body_lines).strip()

    return {
        "title": title,
        "body_text": body_text,
        "speaker_notes": speaker_notes,
    }


def markdown_to_slide_dicts(markdown: str) -> list[dict]:
    """Convert markdown to a list of slide dicts.

    Slides are separated by --- (horizontal rules).
    First # heading becomes slide title, rest becomes body.
    Speaker notes extracted from :::notes blocks.
    """
    chunks = split_slides(markdown)
    return [parse_slide_chunk(chunk) for chunk in chunks]
