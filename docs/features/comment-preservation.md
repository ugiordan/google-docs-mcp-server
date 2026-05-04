# Comment Preservation

When updating document content, preserving existing comments is critical. Google Docs comments are anchored to specific text ranges. If that text is deleted, the comment loses its anchor and becomes orphaned.

## How It Works

### Tab Updates (Diff-Based)

When `update_document_markdown` is called with a `tab_id`, the server uses paragraph-level diffing to minimize changes:

1. Reads the current tab content from the Google Docs API (paragraph text and character indices)
2. Converts the new markdown blocks into comparable paragraph elements
3. Uses `SequenceMatcher` to find unchanged, inserted, deleted, and replaced regions
4. Generates targeted `batchUpdate` requests that only touch changed paragraphs
5. Processes changes in reverse document order so each operation uses original indices

Comments anchored to unchanged paragraphs are never touched, so they remain intact.

If the diff finds nothing in common between old and new content (complete rewrite), it falls back to full replacement.

### Full Document Updates (Save/Restore)

When updating without a `tab_id` (full document replacement via .docx upload), comments cannot be preserved through diffing. Instead, the server:

1. Saves all unresolved comments before the update (content, author, quoted text, replies)
2. Performs the full document replacement
3. Re-creates comments after the update, prefixing each with `[Original Author Name]` for attribution
4. Re-creates replies in order

This is a best-effort approach. Comments whose quoted text no longer exists in the new content cannot be re-anchored. The response includes a `comments_failed` list with details about any comments that could not be restored (author, content, quoted text, reason).

## When Each Strategy Is Used

| Operation | Strategy | Comment Behavior |
|-----------|----------|-----------------|
| `update_document_markdown` with `tab_id` | Diff-based | Preserved on unchanged text |
| `update_document_markdown` without `tab_id` | Save/restore | Best-effort re-creation |
| `update_document` in replace mode | Save/restore | Best-effort re-creation |
| `update_document` in append mode | N/A | Existing content untouched |

## Response Fields

When diff-based updates are used, the response includes `diff_used: true`.

When save/restore is used, the response includes:

- `comments_restored`: number of comments successfully re-created
- `comments_failed`: list of comments that could not be restored, each with `author`, `content`, `quoted_text`, and `reason`
