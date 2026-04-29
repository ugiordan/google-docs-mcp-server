# Google Docs MCP Server

A [Model Context Protocol](https://modelcontextprotocol.io/) server that provides Google Docs and Google Slides read and write operations over stdio transport. Built with [FastMCP](https://github.com/jlowin/fastmcp), packaged as a hardened Podman container.

## What It Does

This MCP server gives AI assistants (Claude Code, or any MCP-compatible client) full access to Google Docs and Slides through 33 tools:

- **Google Docs**: list, read, create, update, delete documents. Comment management (add, reply, resolve, delete). Folder lookup and file moves. Markdown-to-doc conversion with template styling. File upload. Per-tab content updates with diff-based comment preservation.
- **Google Slides**: list, read, create presentations. Add, delete, duplicate, reorder slides. Update text and speaker notes. Text styling. Markdown-to-slides conversion.

## Key Design Decisions

- **Container-first**: runs as a hardened Podman container with read-only filesystem, dropped capabilities, non-root execution, and memory limits.
- **Two-step deletes**: destructive operations require a cryptographic nonce confirmation (30-second TTL) to prevent prompt injection attacks from triggering unintended deletions.
- **Comment preservation**: tab updates use paragraph-level diffing to only modify changed content, preserving comment anchors on unchanged text.
- **Prompt injection mitigation**: document content is wrapped in delimiter tags with untrusted data warnings to help the LLM distinguish content from instructions.

## Quick Links

- [Quickstart](getting-started/quickstart.md): get running in 5 minutes
- [Google Docs tools](tools/google-docs.md): all 20 document tools
- [Google Slides tools](tools/google-slides.md): all 13 presentation tools
- [Security](security.md): threat model, container hardening, input validation
- [GitHub Repository](https://github.com/ugiordan/google-docs-mcp-server)

## License

[Apache License 2.0](https://github.com/ugiordan/google-docs-mcp-server/blob/main/LICENSE)
