"""
MCP Server

FastAPI application exposing the REST-to-MCP adapter as an MCP-compliant server.

THE GOLDEN PATH (single execution flow):
    POST /mcp
      → server.mcp_endpoint()
        → adapter.handle_request()
          → method handler (initialize | tools/list | tools/call)
            → response + sealed context

All MCP clients MUST use POST /mcp with JSON-RPC 2.0 messages.
Other endpoints (/health, /tools) exist for debugging only.
"""

import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from .adapter import RestToMcpAdapter, create_multi_api_adapter
from .dashboard import get_static_files, router as dashboard_router, set_adapter
from .models import ErrorCode, JsonRpcRequest, make_error_response

# -----------------------------------------------------------------------------
# Application Lifecycle
# -----------------------------------------------------------------------------

adapter: RestToMcpAdapter | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage adapter lifecycle - startup and shutdown."""
    global adapter
    adapter = create_multi_api_adapter()
    # Share adapter with dashboard for playground feature
    set_adapter(adapter)
    yield
    if adapter:
        await adapter.close()


# -----------------------------------------------------------------------------
# FastAPI Application
# -----------------------------------------------------------------------------

app = FastAPI(
    title="REST-to-MCP Adapter",
    description=(
        "Translates REST APIs into MCP-compliant tool interfaces. "
        "Demo adapter with multi-API support: JSONPlaceholder + Open-Meteo."
    ),
    version="0.2.0",
    lifespan=lifespan,
)

# Mount dashboard UI and static files
app.include_router(dashboard_router)
app.mount("/static", get_static_files(), name="static")


@app.post("/mcp")
async def mcp_endpoint(request: Request) -> JSONResponse:
    """
    THE SINGLE ENTRY POINT for all MCP operations.

    This is the golden path. All MCP clients send JSON-RPC 2.0 requests here.
    The adapter routes to the appropriate handler and returns a sealed context.

    Supported methods:
    - initialize: Handshake and capability discovery
    - tools/list: Enumerate available tools
    - tools/call: Execute a tool
    """
    if adapter is None:
        raise HTTPException(status_code=503, detail="Adapter not initialized")

    # Parse raw JSON to handle malformed requests gracefully
    try:
        body = await request.json()
    except json.JSONDecodeError:
        # ContractViolation: Request body is not valid JSON
        error = make_error_response(None, ErrorCode.PARSE_ERROR, "Invalid JSON")
        return JSONResponse(content=error.model_dump(), status_code=200)

    # Validate as JSON-RPC request
    try:
        rpc_request = JsonRpcRequest(**body)
    except ValidationError as e:
        # ContractViolation: Request does not conform to JSON-RPC schema
        error = make_error_response(
            body.get("id") if isinstance(body, dict) else None,
            ErrorCode.INVALID_REQUEST,
            f"Invalid request: {e}",
        )
        return JSONResponse(content=error.model_dump(), status_code=200)

    # Handle the request (returns response + context for traceability)
    response, _context = await adapter.handle_request(rpc_request)
    # Note: context is available here for logging/debugging if needed
    return JSONResponse(content=response.model_dump(), status_code=200)


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy"}


# -----------------------------------------------------------------------------
# Debug Endpoints (NOT part of golden path)
# -----------------------------------------------------------------------------


@app.get("/tools")
async def list_tools() -> dict[str, Any]:
    """
    DEBUG ONLY: List available tools as plain JSON.

    WARNING: This endpoint bypasses the MCP protocol.
    MCP clients MUST use POST /mcp with method="tools/list" instead.

    This exists only for:
    - Manual debugging in browser
    - Quick verification during development
    - Integration test setup

    Do NOT use in production MCP integrations.
    """
    if adapter is None:
        raise HTTPException(status_code=503, detail="Adapter not initialized")

    tools = adapter.list_tools()
    return {"tools": [t.model_dump() for t in tools]}


# -----------------------------------------------------------------------------
# Example usage (for testing)
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
