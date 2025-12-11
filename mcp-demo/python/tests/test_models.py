"""
Tests for MCP protocol models.

Validates that our Pydantic models correctly handle JSON-RPC 2.0
message serialization and deserialization.
"""

import pytest
from pydantic import ValidationError

from rest_to_mcp.models import (
    ErrorCode,
    JsonRpcErrorResponse,
    JsonRpcRequest,
    JsonRpcResponse,
    TextContent,
    Tool,
    ToolInputSchema,
    make_error_response,
    make_success_response,
)


class TestJsonRpcRequest:
    """Tests for JSON-RPC request parsing."""

    def test_valid_request_with_params(self):
        request = JsonRpcRequest(
            id=1,
            method="tools/call",
            params={"name": "get_posts", "arguments": {}},
        )
        assert request.jsonrpc == "2.0"
        assert request.id == 1
        assert request.method == "tools/call"
        assert request.params == {"name": "get_posts", "arguments": {}}

    def test_valid_request_without_params(self):
        request = JsonRpcRequest(id="abc", method="tools/list")
        assert request.params is None

    def test_string_id(self):
        request = JsonRpcRequest(id="request-123", method="initialize")
        assert request.id == "request-123"

    def test_invalid_jsonrpc_version(self):
        with pytest.raises(ValidationError):
            JsonRpcRequest(jsonrpc="1.0", id=1, method="test")

    def test_from_dict(self):
        data = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
        request = JsonRpcRequest(**data)
        assert request.method == "tools/list"


class TestJsonRpcResponse:
    """Tests for JSON-RPC response construction."""

    def test_success_response(self):
        response = JsonRpcResponse(id=1, result={"tools": []})
        assert response.jsonrpc == "2.0"
        assert response.id == 1
        assert response.result == {"tools": []}

    def test_serialization(self):
        response = JsonRpcResponse(id=1, result="ok")
        data = response.model_dump()
        assert data == {"jsonrpc": "2.0", "id": 1, "result": "ok"}


class TestJsonRpcErrorResponse:
    """Tests for JSON-RPC error response construction."""

    def test_error_response(self):
        response = make_error_response(
            request_id=1,
            code=ErrorCode.METHOD_NOT_FOUND,
            message="Unknown method: foo",
        )
        assert response.id == 1
        assert response.error.code == -32601
        assert "Unknown method" in response.error.message

    def test_error_with_null_id(self):
        response = make_error_response(
            request_id=None,
            code=ErrorCode.PARSE_ERROR,
            message="Invalid JSON",
        )
        assert response.id is None

    def test_error_with_data(self):
        response = make_error_response(
            request_id=1,
            code=ErrorCode.INVALID_PARAMS,
            message="Validation failed",
            data={"field": "name", "error": "required"},
        )
        assert response.error.data == {"field": "name", "error": "required"}


class TestHelperFunctions:
    """Tests for response helper functions."""

    def test_make_success_response(self):
        response = make_success_response(42, {"status": "ok"})
        assert response.id == 42
        assert response.result == {"status": "ok"}

    def test_make_error_response_all_codes(self):
        for code in ErrorCode:
            response = make_error_response(1, code, "test")
            assert response.error.code == code.value


class TestToolModels:
    """Tests for MCP tool-related models."""

    def test_tool_creation(self):
        tool = Tool(
            name="get_user",
            description="Get a user by ID",
            inputSchema=ToolInputSchema(
                properties={"id": {"type": "string"}},
                required=["id"],
            ),
        )
        assert tool.name == "get_user"
        assert tool.inputSchema.required == ["id"]

    def test_tool_serialization(self):
        tool = Tool(
            name="test",
            description="A test tool",
            inputSchema=ToolInputSchema(),
        )
        data = tool.model_dump()
        assert data["name"] == "test"
        assert data["inputSchema"]["type"] == "object"

    def test_text_content(self):
        content = TextContent(text="Hello, world!")
        assert content.type == "text"
        assert content.text == "Hello, world!"
