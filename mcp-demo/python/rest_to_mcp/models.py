"""
MCP Protocol Models

Pydantic schemas for JSON-RPC 2.0 messages as used by the Model Context Protocol.
These mirror the message types ContextForge handles in its gateway.

Reference: https://modelcontextprotocol.io/specification
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal, TypedDict

from pydantic import BaseModel, Field

from .config import MCP_PROTOCOL_VERSION, SERVER_NAME, SERVER_VERSION


# -----------------------------------------------------------------------------
# TypedDict Definitions for Structured Data
# -----------------------------------------------------------------------------


class TextContentDict(TypedDict):
    """Dictionary representation of text content."""

    type: Literal["text"]
    text: str


class ImageContentDict(TypedDict):
    """Dictionary representation of image content."""

    type: Literal["image"]
    data: str
    mimeType: str


ContentBlockDict = TextContentDict | ImageContentDict


class ToolCallResultDict(TypedDict):
    """Dictionary representation of tool call result."""

    content: list[ContentBlockDict]
    isError: bool


class ScenarioStepResultDict(TypedDict, total=False):
    """Dictionary representation of a scenario step result."""

    tool: str
    args: dict[str, Any]
    result: ToolCallResultDict
    parsed_data: dict[str, Any]


class ToolDict(TypedDict):
    """Dictionary representation of an MCP tool."""

    name: str
    description: str
    inputSchema: dict[str, Any]

# -----------------------------------------------------------------------------
# JSON-RPC 2.0 Base Types
# -----------------------------------------------------------------------------


class JsonRpcRequest(BaseModel):
    """
    JSON-RPC 2.0 request object.

    MCP uses JSON-RPC as its wire protocol. Every tool invocation,
    resource fetch, and prompt request is wrapped in this format.
    """

    jsonrpc: Literal["2.0"] = "2.0"
    id: int | str
    method: str
    params: dict[str, Any] | None = None


class JsonRpcResponse(BaseModel):
    """JSON-RPC 2.0 success response."""

    jsonrpc: Literal["2.0"] = "2.0"
    id: int | str
    result: Any


class JsonRpcErrorData(BaseModel):
    """Structured error information."""

    code: int
    message: str
    data: Any | None = None


class JsonRpcErrorResponse(BaseModel):
    """JSON-RPC 2.0 error response."""

    jsonrpc: Literal["2.0"] = "2.0"
    id: int | str | None
    error: JsonRpcErrorData


# Standard JSON-RPC error codes
class ErrorCode(int, Enum):
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603


# -----------------------------------------------------------------------------
# MCP Tool Types
# -----------------------------------------------------------------------------


class ToolInputSchema(BaseModel):
    """
    JSON Schema describing a tool's input parameters.

    This is how MCP tools declare what arguments they accept.
    LLM agents use this schema to construct valid tool calls.
    """

    type: Literal["object"] = "object"
    properties: dict[str, dict[str, Any]] = Field(default_factory=dict)
    required: list[str] = Field(default_factory=list)


class Tool(BaseModel):
    """
    MCP Tool definition.

    Tools are the primary way MCP servers expose functionality.
    Each tool has a name, description (for LLM understanding),
    and a schema defining its parameters.
    """

    name: str
    description: str
    inputSchema: ToolInputSchema  # noqa: N815 (MCP spec uses camelCase)


class ToolCallParams(BaseModel):
    """Parameters for tools/call method."""

    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolCallResult(BaseModel):
    """Result of a tool invocation."""

    content: list[ContentBlock]
    isError: bool = False  # noqa: N815


# -----------------------------------------------------------------------------
# Content Types
# -----------------------------------------------------------------------------


class TextContent(BaseModel):
    """Text content block."""

    type: Literal["text"] = "text"
    text: str


class ImageContent(BaseModel):
    """Image content block (base64 encoded)."""

    type: Literal["image"] = "image"
    data: str
    mimeType: str  # noqa: N815


ContentBlock = TextContent | ImageContent


# -----------------------------------------------------------------------------
# MCP Method Responses
# -----------------------------------------------------------------------------


class ListToolsResult(BaseModel):
    """Response to tools/list method."""

    tools: list[Tool]


class InitializeResult(BaseModel):
    """Response to initialize method."""

    protocolVersion: str = MCP_PROTOCOL_VERSION  # noqa: N815
    serverInfo: dict[str, str] = Field(  # noqa: N815
        default_factory=lambda: {"name": SERVER_NAME, "version": SERVER_VERSION}
    )
    capabilities: dict[str, Any] = Field(default_factory=lambda: {"tools": {}})


# -----------------------------------------------------------------------------
# Helper Functions
# -----------------------------------------------------------------------------


def make_error_response(
    request_id: int | str | None,
    code: ErrorCode,
    message: str,
    data: Any | None = None,
) -> JsonRpcErrorResponse:
    """Construct a JSON-RPC error response."""
    return JsonRpcErrorResponse(
        id=request_id,
        error=JsonRpcErrorData(code=code.value, message=message, data=data),
    )


def make_success_response(request_id: int | str, result: Any) -> JsonRpcResponse:
    """Construct a JSON-RPC success response."""
    return JsonRpcResponse(id=request_id, result=result)
