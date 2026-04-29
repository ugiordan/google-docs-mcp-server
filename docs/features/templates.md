# Templates

Templates let you apply consistent styling when converting markdown to Google Docs and Slides.

## Configuration

Create `~/.config/google-docs-mcp/templates.yaml`:

```yaml
templates:
  - name: "standard"
    doc_id: "1aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789ABC"
    default: true
  - name: "report"
    doc_id: "2xYzAbCdEfGhIjKlMnOpQrStUvWx0123456789DEF"

slides_templates:
  - name: "corporate"
    presentation_id: "1aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789ABC"
    default: true
```

If `templates.yaml` is missing or empty, all tools work normally with default styling.

## Docs Templates

The `doc_id` is the ID of a Google Doc whose named styles will be extracted and applied. Find it in the document URL: `docs.google.com/document/d/{doc_id}/edit`.

**Styles copied**: heading fonts (H1-H6), body text font, font sizes, line spacing, text colors.

**Not copied**: complex layouts, columns, page breaks, headers/footers, Apps Script, macros.

### Style Preservation

When `update_document_markdown` is called without a `template_name`, the tool preserves the document's existing named styles (heading fonts, body font, sizes, colors, line spacing). This is important for branded documents where replacing content should not strip formatting.

## Slides Templates

The `presentation_id` is the ID of a Google Slides presentation that serves as the base for new presentations. Find it in the URL: `docs.google.com/presentation/d/{presentation_id}/edit`.

When a slides template is configured, `create_presentation` and `convert_markdown_to_slides` copy the template presentation (via Drive API `files.copy`) instead of creating a blank one. The copy inherits the template's theme, master slides, layouts, fonts, and colors. The template itself is never modified.

### Template Selection

- If a default template is set, it is used automatically
- Pass `template_name` to pick a specific template
- Without any slides template configuration, presentations are created blank
- If templates are configured and no `template_name` is provided, the tool returns the list of available templates
