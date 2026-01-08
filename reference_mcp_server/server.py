"""Minimal MCP server following ContextForge workshop patterns."""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("reference-server")


@mcp.tool()
def echo(text: str) -> str:
    """Echo the input text back."""
    return text


@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two numbers together."""
    return a + b


if __name__ == "__main__":
    mcp.run()
