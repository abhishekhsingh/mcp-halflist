"""MCP server with a tool whose description explains a credential-masking feature.

The description names an opt-in environment variable (GET_ENV_INCLUDE_SECRETS)
and mentions credential words. It is a safety note, not an instruction, so the
security scan must not report it as a threat.
"""

from mcp.server.mcpserver import MCPServer

mcp = MCPServer("redaction-test-server", version="1.0.0")


@mcp.tool()
def get_env() -> str:
    """Returns all environment variables, helpful for debugging MCP server configuration.
    Values of credential-like names (a KEY, TOKEN, SECRET, PASSWORD, PASSWD, CREDENTIAL,
    AUTH or COOKIE name segment) are masked as "<redacted>" unless GET_ENV_INCLUDE_SECRETS
    is set to 1 or true in the server's environment."""
    return "{}"


if __name__ == "__main__":
    mcp.run()
