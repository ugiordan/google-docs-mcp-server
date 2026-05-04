# Quickstart

## Prerequisites

- [Podman](https://podman.io/) (rootless mode recommended)
- Google Cloud project with OAuth 2.0 Desktop credentials ([setup instructions](oauth-setup.md))
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) or any MCP-compatible client

## 1. Set Up Credentials

You need a `credentials.json` from Google Cloud Console. See [Google OAuth Setup](oauth-setup.md) if you don't have one yet.

```bash
mkdir -p ~/.config/google-docs-mcp
cp /path/to/your/credentials.json ~/.config/google-docs-mcp/credentials.json
```

## 2. Authenticate

```bash
touch ~/.config/google-docs-mcp/tokens.json
podman run -it --rm -p 8080:8080 \
  -v ~/.config/google-docs-mcp/tokens.json:/app/tokens.json:rw \
  -v ~/.config/google-docs-mcp/credentials.json:/app/credentials.json:ro \
  ghcr.io/ugiordan/google-docs-mcp-server:latest --auth
```

This prints a URL. Open it in your browser, grant access, and the token is saved automatically.

## 3. Configure Claude Code

Add to your Claude Code configuration (`~/.claude.json`):

```json
{
  "mcpServers": {
    "google-docs": {
      "command": "podman",
      "args": [
        "run", "-i", "--rm",
        "--read-only", "--cap-drop=ALL",
        "--security-opt=no-new-privileges", "--memory=256m",
        "--mount", "type=tmpfs,destination=/tmp",
        "-v", "${HOME}/.config/google-docs-mcp/tokens.json:/app/tokens.json:rw",
        "-v", "${HOME}/.config/google-docs-mcp/templates.yaml:/app/templates.yaml:ro",
        "-v", "${HOME}/.config/google-docs-mcp/credentials.json:/app/credentials.json:ro",
        "-v", "${HOME}/uploads:/uploads:ro",
        "ghcr.io/ugiordan/google-docs-mcp-server:latest"
      ]
    }
  }
}
```

Restart Claude Code. The `google-docs` MCP server should appear with 33 available tools.

## Building from Source

If you prefer to build locally instead of using the published image:

```bash
git clone https://github.com/ugiordan/google-docs-mcp-server.git
cd google-docs-mcp-server
podman build -t google-docs-mcp:latest -f Containerfile .
```

Then replace `ghcr.io/ugiordan/google-docs-mcp-server:latest` with `localhost/google-docs-mcp:latest` in the commands above.

## Token Management

```bash
# Re-authenticate
podman run -it --rm -p 8080:8080 \
  -v ~/.config/google-docs-mcp/tokens.json:/app/tokens.json:rw \
  -v ~/.config/google-docs-mcp/credentials.json:/app/credentials.json:ro \
  ghcr.io/ugiordan/google-docs-mcp-server:latest --auth

# Revoke access and delete tokens
podman run -it --rm \
  -v ~/.config/google-docs-mcp/tokens.json:/app/tokens.json:rw \
  -v ~/.config/google-docs-mcp/credentials.json:/app/credentials.json:ro \
  ghcr.io/ugiordan/google-docs-mcp-server:latest --revoke
```

Tokens are stored at `~/.config/google-docs-mcp/tokens.json` with `0600` permissions. They refresh automatically on expiry.

## Troubleshooting

**403 Forbidden on write operations**: re-run `--auth` to refresh tokens. Ensure the Google account has edit access to the target document.

**AUTH_REQUIRED error**: re-run the `--auth` flow to obtain fresh tokens.

**Container won't start**: verify `credentials.json` and `tokens.json` exist at `~/.config/google-docs-mcp/`. Run `--auth` if tokens are missing.

**Template not found**: check that `templates.yaml` exists, is valid YAML, and the template name matches exactly.
