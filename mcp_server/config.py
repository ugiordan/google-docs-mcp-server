"""Configuration module for template loading and validation."""

import logging
from dataclasses import dataclass
from pathlib import Path

import yaml

from mcp_server.validation import _ID_PATTERN

logger = logging.getLogger("google-docs-mcp")


@dataclass
class Template:
    """Represents a Google Doc template."""

    name: str
    doc_id: str
    default: bool = False


@dataclass
class TemplateConfig:
    """Configuration containing loaded templates."""

    templates: list[Template]

    @property
    def default_template(self) -> Template | None:
        """Return the default template, if any."""
        for template in self.templates:
            if template.default:
                return template
        return None


@dataclass
class SlidesTemplate:
    """Represents a Google Slides template presentation."""

    name: str
    presentation_id: str
    default: bool = False


@dataclass
class SlidesTemplateConfig:
    """Configuration containing loaded Slides templates."""

    templates: list[SlidesTemplate]

    @property
    def default_template(self) -> SlidesTemplate | None:
        for template in self.templates:
            if template.default:
                return template
        return None


def load_templates(path: str) -> TemplateConfig:
    """
    Load templates from YAML file.

    Args:
        path: Path to templates.yaml file

    Returns:
        TemplateConfig with loaded templates (empty if file missing/invalid)
    """
    templates = []

    # Check if file exists
    file_path = Path(path)
    if not file_path.exists():
        return TemplateConfig(templates=[])

    # Try to load YAML
    try:
        with open(file_path) as f:
            data = yaml.safe_load(f)
    except Exception:
        logger.warning("Failed to load templates from %s", path)
        return TemplateConfig(templates=[])

    # Handle empty file
    if not data:
        return TemplateConfig(templates=[])

    # Extract templates list
    templates_list = data.get("templates", [])
    if not isinstance(templates_list, list):
        return TemplateConfig(templates=[])

    # Validate and build template objects
    for item in templates_list:
        if not isinstance(item, dict):
            continue

        name = item.get("name")
        doc_id = item.get("doc_id")
        default = item.get("default", False)

        # Skip if missing required fields
        if not name or not doc_id:
            continue

        # Validate doc_id format - skip invalid IDs silently
        if not _ID_PATTERN.match(doc_id):
            continue

        templates.append(Template(name=name, doc_id=doc_id, default=default))

    return TemplateConfig(templates=templates)


def load_slides_templates(path: str) -> SlidesTemplateConfig:
    """Load Slides templates from the slides_templates section of a YAML file."""
    file_path = Path(path)
    if not file_path.exists():
        return SlidesTemplateConfig(templates=[])

    try:
        with open(file_path) as f:
            data = yaml.safe_load(f)
    except Exception:
        logger.warning("Failed to load slides templates from %s", path)
        return SlidesTemplateConfig(templates=[])

    if not data:
        return SlidesTemplateConfig(templates=[])

    templates_list = data.get("slides_templates", [])
    if not isinstance(templates_list, list):
        return SlidesTemplateConfig(templates=[])

    templates = []
    for item in templates_list:
        if not isinstance(item, dict):
            continue

        name = item.get("name")
        presentation_id = item.get("presentation_id")
        default = item.get("default", False)

        if not name or not presentation_id:
            continue

        if not _ID_PATTERN.match(presentation_id):
            continue

        templates.append(
            SlidesTemplate(name=name, presentation_id=presentation_id, default=default)
        )

    return SlidesTemplateConfig(templates=templates)


def validate_config(credentials_path: str, token_path: str) -> bool:
    """
    Validate that configuration files exist.

    Args:
        credentials_path: Path to credentials.json file
        token_path: Path to tokens.json file (optional, may not exist yet)

    Returns:
        True if valid

    Raises:
        FileNotFoundError: If credentials file doesn't exist
    """
    creds_file = Path(credentials_path)
    if not creds_file.exists():
        raise FileNotFoundError(f"credentials file not found: {credentials_path}")

    # Token file is optional (needed for auth flow, but may not exist yet)
    return True
