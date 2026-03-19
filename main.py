"""Entry point for Google Docs MCP server."""

import sys


def main():
    if "--auth" in sys.argv:
        import os

        from mcp_server.auth import run_auth_flow

        credentials_path = os.environ.get(
            "GOOGLE_CREDENTIALS_PATH", "/app/credentials.json"
        )
        token_path = os.environ.get("GOOGLE_TOKEN_PATH", "/app/tokens.json")
        run_auth_flow(credentials_path, token_path)
    elif "--revoke" in sys.argv:
        import os

        from mcp_server.auth import revoke_tokens

        token_path = os.environ.get("GOOGLE_TOKEN_PATH", "/app/tokens.json")
        revoke_tokens(token_path)
    else:
        from mcp_server.main import create_server

        mcp = create_server()
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
