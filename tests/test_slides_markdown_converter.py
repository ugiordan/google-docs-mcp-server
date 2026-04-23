"""Tests for slides_markdown_converter module."""

from mcp_server.services.slides_markdown_converter import (
    extract_speaker_notes,
    markdown_to_slide_dicts,
    parse_slide_chunk,
    split_slides,
)


class TestSplitSlides:
    def test_single_slide(self):
        result = split_slides("# Title\nSome content")
        assert len(result) == 1
        assert "# Title" in result[0]

    def test_multiple_slides(self):
        md = "# Slide 1\nContent 1\n---\n# Slide 2\nContent 2\n---\n# Slide 3"
        result = split_slides(md)
        assert len(result) == 3
        assert "Slide 1" in result[0]
        assert "Slide 2" in result[1]
        assert "Slide 3" in result[2]

    def test_ignores_separator_in_code_block(self):
        md = "# Slide 1\n```yaml\nkey: value\n---\nother: stuff\n```\n---\n# Slide 2"
        result = split_slides(md)
        assert len(result) == 2
        assert "---" in result[0]
        assert "Slide 2" in result[1]

    def test_empty_input(self):
        result = split_slides("")
        assert len(result) == 0

    def test_only_separators(self):
        result = split_slides("---\n---\n---")
        assert len(result) == 0

    def test_whitespace_around_separator(self):
        md = "# Slide 1\n---  \n# Slide 2"
        result = split_slides(md)
        assert len(result) == 2

    def test_more_than_three_dashes(self):
        md = "# Slide 1\n-----\n# Slide 2"
        result = split_slides(md)
        assert len(result) == 2

    def test_nested_code_blocks(self):
        md = "# Slide 1\n```\ncode\n```\n---\n# Slide 2\n```\nmore\n---\ncode\n```"
        result = split_slides(md)
        assert len(result) == 2

    def test_unclosed_code_block_treats_rest_as_code(self):
        md = "# Slide 1\n```\ncode here\n---\n# Slide 2"
        result = split_slides(md)
        assert len(result) == 1
        assert "---" in result[0]

    def test_tilde_fences_treated_as_code(self):
        md = "# Slide 1\n~~~\ncode\n---\nmore\n~~~\n---\n# Slide 2"
        result = split_slides(md)
        assert len(result) == 2
        assert "---" in result[0]

    def test_whitespace_only_chunks_skipped(self):
        md = "---\n   \n\n---\n# Real Slide"
        result = split_slides(md)
        assert len(result) == 1
        assert "Real Slide" in result[0]

    def test_backtick_inside_line_not_a_fence(self):
        md = "# Slide 1\nUse `---` as separator\n---\n# Slide 2"
        result = split_slides(md)
        assert len(result) == 2

    def test_two_dashes_is_not_separator(self):
        md = "# Slide 1\n--\n# Still Slide 1"
        result = split_slides(md)
        assert len(result) == 1


class TestExtractSpeakerNotes:
    def test_extracts_notes(self):
        chunk = "# Title\nContent\n:::notes\nThese are my notes\n:::"
        content, notes = extract_speaker_notes(chunk)
        assert notes == "These are my notes"
        assert ":::notes" not in content
        assert ":::" not in content or content.count(":::") == 0

    def test_no_notes(self):
        chunk = "# Title\nContent"
        content, notes = extract_speaker_notes(chunk)
        assert notes == ""
        assert content == chunk

    def test_multiline_notes(self):
        chunk = "# Title\n:::notes\nLine 1\nLine 2\nLine 3\n:::\nMore content"
        content, notes = extract_speaker_notes(chunk)
        assert "Line 1\nLine 2\nLine 3" == notes
        assert "More content" in content

    def test_notes_at_end(self):
        chunk = "Content here\n:::notes\nNotes here\n:::"
        content, notes = extract_speaker_notes(chunk)
        assert notes == "Notes here"
        assert content.strip() == "Content here"

    def test_multiple_notes_blocks_takes_first(self):
        chunk = (
            "# Title\n:::notes\nFirst notes\n:::\nMiddle\n:::notes\nSecond notes\n:::"
        )
        content, notes = extract_speaker_notes(chunk)
        assert notes == "First notes"

    def test_unclosed_notes_block_no_match(self):
        chunk = "# Title\n:::notes\nThese notes never close"
        content, notes = extract_speaker_notes(chunk)
        assert notes == ""
        assert ":::notes" in content

    def test_notes_with_empty_content(self):
        chunk = "# Title\n:::notes\n\n:::"
        content, notes = extract_speaker_notes(chunk)
        assert notes == ""


class TestParseSlideChunk:
    def test_title_and_body(self):
        chunk = "# My Title\nSome body text\nMore text"
        result = parse_slide_chunk(chunk)
        assert result["title"] == "My Title"
        assert "Some body text" in result["body_text"]
        assert "More text" in result["body_text"]

    def test_no_title(self):
        chunk = "Just some text\nNo heading here"
        result = parse_slide_chunk(chunk)
        assert result["title"] == ""
        assert "Just some text" in result["body_text"]

    def test_h2_title(self):
        chunk = "## Second Level\nBody"
        result = parse_slide_chunk(chunk)
        assert result["title"] == "Second Level"

    def test_only_first_heading_is_title(self):
        chunk = "# First Title\n# Second Title\nBody"
        result = parse_slide_chunk(chunk)
        assert result["title"] == "First Title"
        assert "# Second Title" in result["body_text"]

    def test_with_notes(self):
        chunk = "# Title\nBody\n:::notes\nMy notes\n:::"
        result = parse_slide_chunk(chunk)
        assert result["title"] == "Title"
        assert result["speaker_notes"] == "My notes"
        assert ":::notes" not in result["body_text"]

    def test_empty_chunk(self):
        result = parse_slide_chunk("")
        assert result["title"] == ""
        assert result["body_text"] == ""
        assert result["speaker_notes"] == ""

    def test_h3_not_treated_as_title(self):
        chunk = "### Third Level\nBody text"
        result = parse_slide_chunk(chunk)
        assert result["title"] == ""
        assert "### Third Level" in result["body_text"]

    def test_body_only_no_heading(self):
        chunk = "Just plain text\nWith multiple lines"
        result = parse_slide_chunk(chunk)
        assert result["title"] == ""
        assert "Just plain text" in result["body_text"]


class TestMarkdownToSlideDicts:
    def test_full_presentation(self):
        md = """# Welcome
Introduction slide

---

# Topic 1
- Point A
- Point B

:::notes
Remember to mention X
:::

---

# Topic 2
Final content"""
        result = markdown_to_slide_dicts(md)
        assert len(result) == 3
        assert result[0]["title"] == "Welcome"
        assert result[1]["title"] == "Topic 1"
        assert result[1]["speaker_notes"] == "Remember to mention X"
        assert result[2]["title"] == "Topic 2"

    def test_single_slide(self):
        result = markdown_to_slide_dicts("# Only Slide\nContent")
        assert len(result) == 1
        assert result[0]["title"] == "Only Slide"

    def test_empty_markdown(self):
        result = markdown_to_slide_dicts("")
        assert len(result) == 0
