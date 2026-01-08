# Reference MCP Server

A minimal MCP server implementation following the ContextForge MCP workshop patterns.

## What This Is

This is a canonical MCP server that demonstrates the simplest correct implementation using FastMCP. It provides two tools:

- `echo(text)` — Returns the input text
- `add(a, b)` — Returns the sum of two integers

## Why This Exists Alongside the Gateway

The `mcp-demo/` directory contains a more advanced exploration of context mediation patterns, including REST-to-MCP translation, execution contexts, and orchestration concepts.

This reference server is intentionally separate. It exists to show:

1. The baseline MCP server pattern from the workshop
2. How simple an MCP server can be
3. A working example without additional abstractions

The separation is intentional. The gateway explores what happens when you add explicit context boundaries and orchestration. This server shows the starting point.

## How to Run

1. Install dependencies:
   ```bash
   cd reference_mcp_server
   pip install -r requirements.txt
   ```

2. Run the server:
   ```bash
   python server.py
   ```

The server uses stdio transport by default.

## Usage with Claude Desktop

Add to your Claude Desktop configuration:

```json
{
  "mcpServers": {
    "reference": {
      "command": "python",
      "args": ["path/to/reference_mcp_server/server.py"]
    }
  }
}
```
