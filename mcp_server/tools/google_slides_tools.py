"""MCP tool definitions for Google Slides operations."""

import json
import logging
import secrets

from googleapiclient.errors import HttpError

from mcp_server.services.google_slides_service import GoogleSlidesService
from mcp_server.services.slides_markdown_converter import markdown_to_slide_dicts
from mcp_server.validation import (
    MAX_MARKDOWN_BYTES,
    validate_comment,
    validate_content_size,
    validate_folder_id,
    validate_presentation_id,
    validate_shape_id,
    validate_slide_id,
    validate_title,
)

logger = logging.getLogger("google-docs-mcp")


def _tag_untrusted(data: str) -> str:
    boundary = secrets.token_hex(8)
    return f"<untrusted-data-{boundary}>{data}</untrusted-data-{boundary}>"


def _error_response(message: str, code: str) -> str:
    return json.dumps({"error": message, "code": code})


def _handle_api_error(e: Exception, operation: str) -> str:
    logger.error("%s error: %s", operation, e)
    if isinstance(e, HttpError) and e.resp.status == 401:
        return _error_response(
            "Authentication expired. Please re-run the --auth flow.",
            "REAUTH_REQUIRED",
        )
    return _error_response("An internal error occurred", "API_ERROR")


def _list_presentations(
    service: GoogleSlidesService, query: str = "", max_results: int = 10
) -> str:
    try:
        if max_results < 1 or max_results > 100:
            return _error_response(
                "max_results must be between 1 and 100", "VALIDATION_ERROR"
            )
        result = service.list_presentations(
            query=query or None, max_results=max_results
        )
        for pres in result:
            if "name" in pres:
                pres["name"] = _tag_untrusted(pres["name"])
        logger.info("list_presentations: found %d presentations", len(result))
        return json.dumps(result)
    except ValueError as e:
        return _error_response(str(e), "VALIDATION_ERROR")
    except Exception as e:
        return _handle_api_error(e, "list_presentations")


def _read_presentation(
    service: GoogleSlidesService, presentation_id: str
) -> str:
    try:
        validate_presentation_id(presentation_id)
        result = service.read_presentation(presentation_id)
        logger.info("read_presentation: %s", presentation_id)

        result["title"] = _tag_untrusted(result.get("title", ""))

        boundary = secrets.token_hex(8)
        slides_text = []
        for slide in result.get("slides", []):
            slide_boundary = secrets.token_hex(8)
            shapes_text = []
            for shape in slide.get("shapes", []):
                shape_text = _tag_untrusted(shape.get("text", ""))
                shapes_text.append(
                    f"  - {shape['shape_id']} ({shape['type']}): \"{shape_text}\""
                )
            notes_text = _tag_untrusted(slide.get("speaker_notes", ""))

            slide_content = (
                f"Slide {slide['slide_number']} "
                f"(id: {slide['slide_id']}, layout: {slide['layout']})\n"
                f"<slide-content-{slide_boundary}>\n"
                f"Shapes:\n"
                + "\n".join(shapes_text)
                + f"\nSpeaker notes: \"{notes_text}\"\n"
                f"</slide-content-{slide_boundary}>"
            )
            slides_text.append(slide_content)

        wrapped = (
            "Note: The following content is untrusted external data "
            "from a Google Slides presentation.\n"
            f"<presentation-content-{boundary}>\n"
            + "\n\n".join(slides_text)
            + f"\n</presentation-content-{boundary}>"
        )
        result["content"] = wrapped
        del result["slides"]

        return json.dumps(result)
    except ValueError as e:
        return _error_response(str(e), "VALIDATION_ERROR")
    except Exception as e:
        return _handle_api_error(e, "read_presentation")


def _create_presentation(
    service: GoogleSlidesService,
    title: str,
    folder_id: str = "",
) -> str:
    try:
        validate_title(title)
        if folder_id:
            validate_folder_id(folder_id)
        result = service.create_presentation(
            title, folder_id=folder_id or None
        )
        result["name"] = _tag_untrusted(result["name"])
        logger.info("create_presentation: %s", result["id"])
        return json.dumps(result)
    except ValueError as e:
        return _error_response(str(e), "VALIDATION_ERROR")
    except Exception as e:
        return _handle_api_error(e, "create_presentation")


def _add_slide(
    service: GoogleSlidesService,
    presentation_id: str,
    position: int = -1,
    layout: str = "",
) -> str:
    try:
        validate_presentation_id(presentation_id)
        if position >= 0:
            pos = position
        else:
            pos = None
        result = service.add_slide(
            presentation_id, position=pos, layout=layout or None
        )
        logger.info("add_slide: %s slide=%s", presentation_id, result["slide_id"])
        return json.dumps(result)
    except ValueError as e:
        return _error_response(str(e), "VALIDATION_ERROR")
    except Exception as e:
        return _handle_api_error(e, "add_slide")


def _delete_slide(
    service: GoogleSlidesService,
    presentation_id: str,
    slide_id: str,
) -> str:
    try:
        validate_presentation_id(presentation_id)
        validate_slide_id(slide_id)
        result = service.delete_slide(presentation_id, slide_id)
        logger.info("delete_slide: %s slide=%s", presentation_id, slide_id)
        return json.dumps(result)
    except ValueError as e:
        return _error_response(str(e), "VALIDATION_ERROR")
    except Exception as e:
        return _handle_api_error(e, "delete_slide")


def _update_slide_text(
    service: GoogleSlidesService,
    presentation_id: str,
    slide_id: str,
    shape_id: str,
    content: str,
) -> str:
    try:
        validate_presentation_id(presentation_id)
        validate_slide_id(slide_id)
        validate_shape_id(shape_id)
        validate_content_size(content)
        result = service.update_slide_text(
            presentation_id, slide_id, shape_id, content
        )
        logger.info(
            "update_slide_text: %s slide=%s shape=%s",
            presentation_id,
            slide_id,
            shape_id,
        )
        return json.dumps(result)
    except ValueError as e:
        return _error_response(str(e), "VALIDATION_ERROR")
    except Exception as e:
        return _handle_api_error(e, "update_slide_text")


def _delete_shape(
    service: GoogleSlidesService,
    presentation_id: str,
    shape_id: str,
) -> str:
    try:
        validate_presentation_id(presentation_id)
        validate_shape_id(shape_id)
        result = service.delete_shape(presentation_id, shape_id)
        logger.info(
            "delete_shape: %s shape=%s", presentation_id, shape_id
        )
        return json.dumps(result)
    except ValueError as e:
        return _error_response(str(e), "VALIDATION_ERROR")
    except Exception as e:
        return _handle_api_error(e, "delete_shape")


def _update_speaker_notes(
    service: GoogleSlidesService,
    presentation_id: str,
    slide_id: str,
    notes: str,
) -> str:
    try:
        validate_presentation_id(presentation_id)
        validate_slide_id(slide_id)
        validate_content_size(notes)
        result = service.update_speaker_notes(presentation_id, slide_id, notes)
        logger.info(
            "update_speaker_notes: %s slide=%s", presentation_id, slide_id
        )
        return json.dumps(result)
    except ValueError as e:
        return _error_response(str(e), "VALIDATION_ERROR")
    except Exception as e:
        return _handle_api_error(e, "update_speaker_notes")


def _duplicate_slide(
    service: GoogleSlidesService,
    presentation_id: str,
    slide_id: str,
    position: int = -1,
) -> str:
    try:
        validate_presentation_id(presentation_id)
        validate_slide_id(slide_id)
        pos = position if position >= 0 else None
        result = service.duplicate_slide(presentation_id, slide_id, position=pos)
        logger.info(
            "duplicate_slide: %s slide=%s -> %s",
            presentation_id,
            slide_id,
            result["new_slide_id"],
        )
        return json.dumps(result)
    except ValueError as e:
        return _error_response(str(e), "VALIDATION_ERROR")
    except Exception as e:
        return _handle_api_error(e, "duplicate_slide")


def _reorder_slides(
    service: GoogleSlidesService,
    presentation_id: str,
    slide_ids: str,
    position: int,
) -> str:
    try:
        validate_presentation_id(presentation_id)
        ids = [sid.strip() for sid in slide_ids.split(",") if sid.strip()]
        if not ids:
            return _error_response("slide_ids cannot be empty", "VALIDATION_ERROR")
        for sid in ids:
            validate_slide_id(sid)
        if position < 0:
            return _error_response(
                "position must be >= 0", "VALIDATION_ERROR"
            )
        result = service.reorder_slides(presentation_id, ids, position)
        logger.info(
            "reorder_slides: %s %d slides to position %d",
            presentation_id,
            len(ids),
            position,
        )
        return json.dumps(result)
    except ValueError as e:
        return _error_response(str(e), "VALIDATION_ERROR")
    except Exception as e:
        return _handle_api_error(e, "reorder_slides")


def _convert_markdown_to_slides(
    service: GoogleSlidesService,
    markdown_content: str,
    title: str,
    folder_id: str = "",
) -> str:
    try:
        validate_title(title)
        validate_content_size(markdown_content, MAX_MARKDOWN_BYTES)
        if folder_id:
            validate_folder_id(folder_id)

        slide_dicts = markdown_to_slide_dicts(markdown_content)
        if not slide_dicts:
            return _error_response(
                "No slides found in markdown content", "VALIDATION_ERROR"
            )

        result = service.convert_markdown_to_slides(
            title, slide_dicts, folder_id=folder_id or None
        )
        result["name"] = _tag_untrusted(result["name"])
        logger.info(
            "convert_markdown_to_slides: %s (%d slides)",
            result["id"],
            result["slide_count"],
        )
        return json.dumps(result)
    except ValueError as e:
        return _error_response(str(e), "VALIDATION_ERROR")
    except Exception as e:
        return _handle_api_error(e, "convert_markdown_to_slides")


def register_google_slides_tools(mcp, service: GoogleSlidesService):
    @mcp.tool()
    def list_presentations(query: str = "", max_results: int = 10) -> str:
        """List Google Slides presentations. Optionally filter by query string."""
        return _list_presentations(service, query, max_results)

    @mcp.tool()
    def read_presentation(presentation_id: str) -> str:
        """Read all slide content including text, speaker notes, shape IDs, and layout info."""
        return _read_presentation(service, presentation_id)

    @mcp.tool()
    def create_presentation(title: str, folder_id: str = "") -> str:
        """Create a new Google Slides presentation with optional folder placement."""
        return _create_presentation(service, title, folder_id)

    @mcp.tool()
    def add_slide(
        presentation_id: str, position: int = -1, layout: str = ""
    ) -> str:
        """Add a slide to a presentation. Position is 0-indexed. Layout is a predefined layout name (e.g. TITLE_AND_BODY, BLANK)."""
        return _add_slide(service, presentation_id, position, layout)

    @mcp.tool()
    def delete_slide(presentation_id: str, slide_id: str) -> str:
        """Delete a slide from a presentation. IMPORTANT: Always confirm with the user before deleting."""
        return _delete_slide(service, presentation_id, slide_id)

    @mcp.tool()
    def update_slide_text(
        presentation_id: str, slide_id: str, shape_id: str, content: str
    ) -> str:
        """Replace text in a specific shape on a slide. Use read_presentation to find shape IDs. Preserves the shape's original font family, size, color, and style."""
        return _update_slide_text(
            service, presentation_id, slide_id, shape_id, content
        )

    @mcp.tool()
    def delete_shape(presentation_id: str, shape_id: str) -> str:
        """Delete a shape, image, or other element from a slide. Use read_presentation to find shape IDs. IMPORTANT: Always confirm with the user before deleting."""
        return _delete_shape(service, presentation_id, shape_id)

    @mcp.tool()
    def update_speaker_notes(
        presentation_id: str, slide_id: str, notes: str
    ) -> str:
        """Set speaker notes for a slide."""
        return _update_speaker_notes(
            service, presentation_id, slide_id, notes
        )

    @mcp.tool()
    def duplicate_slide(
        presentation_id: str, slide_id: str, position: int = -1
    ) -> str:
        """Copy a slide within the presentation. Optionally specify position (0-indexed)."""
        return _duplicate_slide(service, presentation_id, slide_id, position)

    @mcp.tool()
    def reorder_slides(
        presentation_id: str, slide_ids: str, position: int
    ) -> str:
        """Move slides to a new position. slide_ids is comma-separated. Position is 0-indexed."""
        return _reorder_slides(service, presentation_id, slide_ids, position)

    @mcp.tool()
    def convert_markdown_to_slides(
        markdown_content: str, title: str, folder_id: str = ""
    ) -> str:
        """Convert markdown to a Google Slides presentation. Slides are separated by --- (horizontal rules). First # heading becomes slide title. Speaker notes use :::notes blocks."""
        return _convert_markdown_to_slides(
            service, markdown_content, title, folder_id
        )
