# Google Slides Tools

13 tools for presentation lifecycle management, slide manipulation, and text styling.

## Presentation Operations

| Tool | Description | Parameters |
|------|-------------|------------|
| `list_presentations` | List presentations, optionally filtered by name | `query` (str, optional), `max_results` (int, 1-100, default 10) |
| `read_presentation` | Read all slide content: text, speaker notes, shape IDs, layout info | `presentation_id` (str) |
| `create_presentation` | Create a new presentation, optionally from a template | `title` (str), `folder_id` (str, optional), `template_name` (str, optional) |
| `convert_markdown_to_slides` | Convert markdown to a presentation (slides split on `---`) | `markdown_content` (str), `title` (str), `folder_id` (str, optional), `template_name` (str, optional) |

## Slide Management

| Tool | Description | Parameters |
|------|-------------|------------|
| `add_slide` | Add a slide at a position with optional layout | `presentation_id` (str), `position` (int, optional), `layout` (str, optional: custom display name or predefined) |
| `delete_slide` | Delete a slide (two-step nonce confirmation) | `presentation_id` (str), `slide_id` (str), `nonce` (str, required on second call) |
| `delete_slides` | Delete multiple slides at once (two-step nonce confirmation) | `presentation_id` (str), `slide_ids` (str, comma-separated), `nonce` (str, required on second call) |
| `duplicate_slide` | Copy a slide within a presentation | `presentation_id` (str), `slide_id` (str), `position` (int, optional) |
| `reorder_slides` | Move slides to new positions | `presentation_id` (str), `slide_ids` (str, comma-separated), `position` (int) |

## Content and Styling

| Tool | Description | Parameters |
|------|-------------|------------|
| `update_slide_text` | Replace text in a shape, preserving font/size/color | `presentation_id` (str), `slide_id` (str), `shape_id` (str), `content` (str) |
| `delete_shape` | Delete a shape, image, or element from a slide (two-step nonce confirmation) | `presentation_id` (str), `shape_id` (str), `nonce` (str, required on second call) |
| `update_speaker_notes` | Set speaker notes for a slide | `presentation_id` (str), `slide_id` (str), `notes` (str) |
| `update_slide_text_style` | Style all text in a shape without replacing content | `presentation_id` (str), `shape_id` (str), `bold`/`italic`/`underline` (bool, optional), `font_family` (str, optional), `font_size` (float, optional), `foreground_color` (str '#RRGGBB', optional), `alignment` (str, optional) |

## Behavior Details

### Delete Confirmation

`delete_slide`, `delete_slides`, and `delete_shape` all use the same two-step nonce confirmation as `delete_document`. The first call returns a nonce valid for 30 seconds, the second call with the nonce executes the deletion. Unlike document deletion, slides and shapes are deleted immediately (not trashed).

### Markdown-to-Slides Format

`convert_markdown_to_slides` splits markdown on `---` separators. Each chunk becomes a slide:

- The first `#` or `##` heading becomes the slide title
- Remaining content becomes the slide body
- Speaker notes can be embedded using `<!--notes-->...<!--/notes-->` blocks

```markdown
# First Slide Title

Body content for the first slide.

---

# Second Slide Title

More content here.

<!--notes-->
These are speaker notes for slide 2.
<!--/notes-->
```
