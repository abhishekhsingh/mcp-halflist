from mcp.server.mcpserver import MCPServer

mcp = MCPServer("bad-test-server", version="1.0.0")


@mcp.tool(description="")
def empty_description_tool(x: str) -> str:
    return x


@mcp.tool()
def crash_tool(x: str) -> str:
    """This tool always crashes."""
    raise RuntimeError("Intentional crash for testing")


@mcp.tool()
def good_tool(name: str) -> str:
    """A good tool that works normally."""
    return f"Hello, {name}!"


if __name__ == "__main__":
    mcp.run(transport="stdio")
