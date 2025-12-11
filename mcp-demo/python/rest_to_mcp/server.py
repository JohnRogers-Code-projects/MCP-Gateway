"""
MCP Server

FastAPI application exposing the REST-to-MCP adapter as an MCP-compliant server.
Handles JSON-RPC 2.0 over HTTP POST, which is one of the transports MCP supports.

In production ContextForge, this would also support:
- SSE (Server-Sent Events) for streaming
- WebSocket for bidirectional communication
- stdio for CLI integration

This demo focuses on HTTP for simplicity.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from .adapter import RestToMcpAdapter, create_jsonplaceholder_adapter
from .dashboard import get_static_files, router as dashboard_router
from .models import ErrorCode, JsonRpcRequest, make_error_response

# -----------------------------------------------------------------------------
# Application Lifecycle
# -----------------------------------------------------------------------------

adapter: RestToMcpAdapter | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage adapter lifecycle - startup and shutdown."""
    global adapter
    adapter = create_jsonplaceholder_adapter()
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
        "Demo adapter for JSONPlaceholder API."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# Mount dashboard UI and static files
app.include_router(dashboard_router)
app.mount("/static", get_static_files(), name="static")


@app.post("/mcp")
async def mcp_endpoint(request: Request) -> JSONResponse:
    """
    Main MCP endpoint accepting JSON-RPC 2.0 requests.

    This is where MCP clients (like LLM agents) send their requests.
    The adapter handles routing to the appropriate method handler.
    """
    if adapter is None:
        raise HTTPException(status_code=503, detail="Adapter not initialized")

    # Parse raw JSON to handle malformed requests gracefully
    try:
        body = await request.json()
    except Exception:
        error = make_error_response(None, ErrorCode.PARSE_ERROR, "Invalid JSON")
        return JSONResponse(content=error.model_dump(), status_code=200)

    # Validate as JSON-RPC request
    try:
        rpc_request = JsonRpcRequest(**body)
    except ValidationError as e:
        error = make_error_response(
            body.get("id") if isinstance(body, dict) else None,
            ErrorCode.INVALID_REQUEST,
            f"Invalid request: {e}",
        )
        return JSONResponse(content=error.model_dump(), status_code=200)

    # Handle the request
    response = await adapter.handle_request(rpc_request)
    return JSONResponse(content=response.model_dump(), status_code=200)


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy"}


@app.get("/tools")
async def list_tools() -> dict[str, Any]:
    """
    Convenience endpoint to list available tools.

    Not part of MCP spec - just useful for debugging and exploration.
    In production, use the MCP tools/list method instead.
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
