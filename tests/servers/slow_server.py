import asyncio

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("slow-test-server")


@mcp.tool()
def fast_tool(name: str) -> str:
    """A tool that responds quickly."""
    return f"Hello, {name}!"


@mcp.tool()
async def slow_tool(query: str) -> str:
    """A tool that takes a long time to respond."""
    await asyncio.sleep(60)
    return f"Result for {query}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
