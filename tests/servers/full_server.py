from mcp.server.fastmcp import FastMCP

mcp = FastMCP("full-test-server")


# ── Tools ────────────────────────────────────────────────────────────────────

@mcp.tool()
def greet(name: str) -> str:
    """Greet someone by name."""
    return f"Hello, {name}!"


@mcp.tool()
def add(a: int, b: int) -> str:
    """Add two numbers together."""
    return str(a + b)


# ── Resources ────────────────────────────────────────────────────────────────

@mcp.resource("resource://config")
def get_config() -> str:
    """Application configuration."""
    return '{"debug": false, "version": "1.0.0"}'


@mcp.resource("resource://readme")
def get_readme() -> str:
    """Project README content."""
    return "# Full Test Server\nA test server with tools, resources, and prompts."


# ── Prompts ──────────────────────────────────────────────────────────────────

@mcp.prompt()
def summarize(text: str) -> str:
    """Summarize the given text."""
    return f"Please summarize the following text:\n\n{text}"


@mcp.prompt()
def translate(text: str, language: str = "Spanish") -> str:
    """Translate text to another language."""
    return f"Please translate the following to {language}:\n\n{text}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
