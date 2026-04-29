# Tab Management

Google Docs supports multiple tabs within a single document. The MCP server provides full tab support for reading, writing, and managing tabs.

## Reading Tabs

`read_document` returns all tabs when a document has multiple tabs. Each tab includes `tab_id`, `title`, and `content`. Tab content is wrapped in `<tab-content>` tags.

## Writing to Tabs

`update_document` accepts a `tab_id` parameter to write content to a specific tab without affecting other tabs.

`update_document_markdown` with `tab_id` uses batchUpdate to apply styled content (headings, bold, italic, code, links, blockquotes, tables) to that specific tab. Without `tab_id`, it uploads a .docx file which replaces the entire document including all tabs.

### Diff-Based Updates

When targeting a specific tab, `update_document_markdown` uses paragraph-level diffing to minimize changes. Only modified paragraphs are deleted and reinserted. Unchanged paragraphs are left alone, which preserves any comment anchors attached to them.

If the new content has nothing in common with the existing content, it falls back to a full replacement. See [Comment Preservation](comment-preservation.md) for more details.

## Managing Tabs

| Tool | Description |
|------|-------------|
| `create_tab` | Create a new tab with a given title |
| `delete_tab` | Delete a tab by its `tab_id` |
| `rename_tab` | Change a tab's display title |
