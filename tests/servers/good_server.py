from mcp.server.fastmcp import FastMCP

mcp = FastMCP("good-test-server")


@mcp.tool()
def greet(name: str) -> str:
    """Greet someone by name."""
    return f"Hello, {name}!"


@mcp.tool()
def add(a: int, b: int) -> str:
    """Add two numbers together."""
    return str(a + b)


@mcp.tool()
def search(query: str, limit: int = 10) -> str:
    """Search for something with an optional limit."""
    return f"Found {limit} results for '{query}'"


@mcp.tool()
def get_status() -> str:
    """Get the current status."""
    return "OK"


@mcp.tool()
def echo(data: dict) -> str:
    """Echo back the provided data as a string."""
    return str(data)


if __name__ == "__main__":
    mcp.run(transport="stdio")
