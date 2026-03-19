import pytest

from mcp_server.config import load_templates, validate_config


class TestLoadTemplates:
    def test_loads_valid_yaml(self, tmp_path):
        f = tmp_path / "templates.yaml"
        f.write_text("""
templates:
  - name: "standard"
    doc_id: "1aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789ABC"
    default: true
  - name: "report"
    doc_id: "2xYzAbCdEfGhIjKlMnOpQrStUvWx0123456789DEF"
""")
        result = load_templates(str(f))
        assert len(result.templates) == 2
        assert result.default_template.name == "standard"

    def test_returns_empty_for_missing_file(self):
        result = load_templates("/nonexistent/path.yaml")
        assert len(result.templates) == 0
        assert result.default_template is None

    def test_returns_empty_for_empty_file(self, tmp_path):
        f = tmp_path / "templates.yaml"
        f.write_text("")
        result = load_templates(str(f))
        assert len(result.templates) == 0

    def test_validates_doc_id_format(self, tmp_path):
        f = tmp_path / "templates.yaml"
        f.write_text("""
templates:
  - name: "bad"
    doc_id: "../../../etc/passwd"
    default: true
""")
        result = load_templates(str(f))
        assert len(result.templates) == 0  # invalid ID skipped


class TestValidateConfig:
    def test_valid_config(self, tmp_path):
        creds = tmp_path / "credentials.json"
        creds.write_text("{}")
        tokens = tmp_path / "tokens.json"
        tokens.write_text("{}")
        assert validate_config(str(creds), str(tokens)) is True

    def test_missing_credentials(self):
        with pytest.raises(FileNotFoundError, match="credentials"):
            validate_config("/nonexistent/creds.json", "/some/tokens.json")
