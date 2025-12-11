"""REST-to-MCP Adapter package."""

from .adapter import HttpMethod, RestEndpoint, RestToMcpAdapter, create_jsonplaceholder_adapter
from .models import (
    ErrorCode,
    JsonRpcErrorResponse,
    JsonRpcRequest,
    JsonRpcResponse,
    Tool,
    ToolCallResult,
)

__all__ = [
    "RestToMcpAdapter",
    "RestEndpoint",
    "HttpMethod",
    "create_jsonplaceholder_adapter",
    "JsonRpcRequest",
    "JsonRpcResponse",
    "JsonRpcErrorResponse",
    "Tool",
    "ToolCallResult",
    "ErrorCode",
]
