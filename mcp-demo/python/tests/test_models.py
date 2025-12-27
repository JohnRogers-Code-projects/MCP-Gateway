"""
Tests for MCP protocol models.

Validates that our Pydantic models correctly handle JSON-RPC 2.0
message serialization and deserialization.
"""

import pytest
from pydantic import ValidationError

from rest_to_mcp.models import (
    ContextError,
    ErrorCode,
    ExecutionContext,
    JsonRpcErrorResponse,
    JsonRpcRequest,
    JsonRpcResponse,
    TextContent,
    Tool,
    ToolCallResult,
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


class TestExecutionContext:
    """
    Tests for the canonical ExecutionContext.

    These tests verify that ExecutionContext enforces its invariants
    and fails loudly when misused.
    """

    # -------------------------------------------------------------------------
    # Invariant 1: Direct construction is forbidden
    # -------------------------------------------------------------------------

    def test_direct_construction_forbidden(self):
        """Direct construction must raise ContextError."""
        with pytest.raises(ContextError) as exc_info:
            ExecutionContext(1, "test")

        assert "from_request()" in str(exc_info.value)

    # -------------------------------------------------------------------------
    # Invariant 2: request_id must be non-empty
    # -------------------------------------------------------------------------

    def test_from_request_rejects_empty_string_id(self):
        """Empty string request_id must be rejected."""
        request = JsonRpcRequest(id="   ", method="test")

        with pytest.raises(ContextError) as exc_info:
            ExecutionContext.from_request(request)

        assert "request.id is empty" in str(exc_info.value)

    # -------------------------------------------------------------------------
    # Invariant 3: method must be non-empty
    # -------------------------------------------------------------------------

    def test_from_request_rejects_empty_method(self):
        """Empty method must be rejected."""
        request = JsonRpcRequest(id=1, method="")

        with pytest.raises(ContextError) as exc_info:
            ExecutionContext.from_request(request)

        assert "method is empty" in str(exc_info.value)

    def test_from_request_rejects_whitespace_method(self):
        """Whitespace-only method must be rejected."""
        request = JsonRpcRequest(id=1, method="   ")

        with pytest.raises(ContextError) as exc_info:
            ExecutionContext.from_request(request)

        assert "method is empty" in str(exc_info.value)

    # -------------------------------------------------------------------------
    # Valid creation path
    # -------------------------------------------------------------------------

    def test_from_request_valid(self):
        """Valid request creates context correctly."""
        request = JsonRpcRequest(id=42, method="tools/call")
        context = ExecutionContext.from_request(request)

        assert context.request_id == 42
        assert context.method == "tools/call"
        assert context.tool_name is None
        assert context.arguments == {}
        assert context.results == ()
        assert context.is_sealed is False

    def test_from_request_string_id(self):
        """String request IDs are valid."""
        request = JsonRpcRequest(id="req-123", method="initialize")
        context = ExecutionContext.from_request(request)

        assert context.request_id == "req-123"

    def test_created_at_is_utc(self):
        """created_at must use UTC timezone."""
        from datetime import timezone

        request = JsonRpcRequest(id=1, method="test")
        context = ExecutionContext.from_request(request)

        assert context.created_at.tzinfo == timezone.utc

    # -------------------------------------------------------------------------
    # Invariant 4: tool_name cannot be rebound
    # -------------------------------------------------------------------------

    def test_with_tool_call_rejects_rebinding(self):
        """Once tool_name is set, it cannot be changed."""
        request = JsonRpcRequest(id=1, method="tools/call")
        context = ExecutionContext.from_request(request)
        context = context.with_tool_call("get_user", {"id": "1"})

        with pytest.raises(ContextError) as exc_info:
            context.with_tool_call("get_posts", {})

        assert "already bound" in str(exc_info.value)
        assert "get_user" in str(exc_info.value)

    def test_with_tool_call_rejects_empty_name(self):
        """Empty tool name must be rejected."""
        request = JsonRpcRequest(id=1, method="tools/call")
        context = ExecutionContext.from_request(request)

        with pytest.raises(ContextError) as exc_info:
            context.with_tool_call("", {})

        assert "name is empty" in str(exc_info.value)

    # -------------------------------------------------------------------------
    # Invariant 5: results require tool_name
    # -------------------------------------------------------------------------

    def test_with_result_requires_tool_name(self):
        """Cannot add results without tool_name being set first."""
        request = JsonRpcRequest(id=1, method="tools/call")
        context = ExecutionContext.from_request(request)
        result = ToolCallResult(content=[TextContent(text="data")])

        with pytest.raises(ContextError) as exc_info:
            context.with_result(result)

        assert "no tool_name set" in str(exc_info.value)

    def test_with_result_rejects_none(self):
        """Cannot add None as result."""
        request = JsonRpcRequest(id=1, method="tools/call")
        context = ExecutionContext.from_request(request).with_tool_call("test", {})

        with pytest.raises(ContextError) as exc_info:
            context.with_result(None)

        assert "result is None" in str(exc_info.value)

    # -------------------------------------------------------------------------
    # Invariant 6: sealed context cannot be mutated
    # -------------------------------------------------------------------------

    def test_sealed_context_rejects_with_tool_call(self):
        """Sealed context cannot accept with_tool_call."""
        request = JsonRpcRequest(id=1, method="tools/call")
        context = ExecutionContext.from_request(request).seal()

        with pytest.raises(ContextError) as exc_info:
            context.with_tool_call("test", {})

        assert "sealed" in str(exc_info.value)

    def test_sealed_context_rejects_with_result(self):
        """Sealed context cannot accept with_result."""
        request = JsonRpcRequest(id=1, method="tools/call")
        context = ExecutionContext.from_request(request)
        context = context.with_tool_call("test", {}).seal()
        result = ToolCallResult(content=[TextContent(text="data")])

        with pytest.raises(ContextError) as exc_info:
            context.with_result(result)

        assert "sealed" in str(exc_info.value)

    # -------------------------------------------------------------------------
    # Immutability of mutation methods
    # -------------------------------------------------------------------------

    def test_with_tool_call_returns_new_context(self):
        """with_tool_call must return a new instance."""
        request = JsonRpcRequest(id=1, method="tools/call")
        original = ExecutionContext.from_request(request)
        updated = original.with_tool_call("get_user", {"id": "5"})

        # Original unchanged
        assert original.tool_name is None
        assert original.arguments == {}

        # New context has updates
        assert updated.tool_name == "get_user"
        assert updated.arguments == {"id": "5"}

        # Different objects
        assert original is not updated

    def test_with_result_returns_new_context(self):
        """with_result must return a new instance."""
        request = JsonRpcRequest(id=1, method="tools/call")
        context = ExecutionContext.from_request(request).with_tool_call("test", {})
        result = ToolCallResult(content=[TextContent(text="data")])

        updated = context.with_result(result)

        assert len(context.results) == 0
        assert len(updated.results) == 1
        assert context is not updated

    # -------------------------------------------------------------------------
    # Defensive copying
    # -------------------------------------------------------------------------

    def test_arguments_returns_copy(self):
        """arguments property must return a copy to prevent mutation."""
        request = JsonRpcRequest(id=1, method="tools/call")
        context = ExecutionContext.from_request(request)
        context = context.with_tool_call("test", {"key": "value"})

        args = context.arguments
        args["key"] = "modified"

        # Original should be unchanged
        assert context.arguments["key"] == "value"

    # -------------------------------------------------------------------------
    # Repr for debugging
    # -------------------------------------------------------------------------

    def test_repr_unsealed(self):
        """Repr shows context state clearly."""
        request = JsonRpcRequest(id=1, method="tools/call")
        context = ExecutionContext.from_request(request)

        assert "id=1" in repr(context)
        assert "method=tools/call" in repr(context)
        assert "SEALED" not in repr(context)

    def test_repr_sealed(self):
        """Repr shows sealed state."""
        request = JsonRpcRequest(id=1, method="tools/call")
        context = ExecutionContext.from_request(request).seal()

        assert "SEALED" in repr(context)

    # -------------------------------------------------------------------------
    # Context Boundaries
    # -------------------------------------------------------------------------

    def test_context_size_empty(self):
        """Empty context has size 0."""
        request = JsonRpcRequest(id=1, method="tools/call")
        context = ExecutionContext.from_request(request)

        assert context.context_size() == 0

    def test_context_size_with_results(self):
        """Context size increases with results."""
        request = JsonRpcRequest(id=1, method="tools/call")
        context = ExecutionContext.from_request(request).with_tool_call("test", {})

        result1 = ToolCallResult(content=[TextContent(text="short")])
        result2 = ToolCallResult(content=[TextContent(text="a longer result")])

        ctx1 = context.with_result(result1)
        ctx2 = ctx1.with_result(result2)

        assert ctx1.context_size() > 0
        assert ctx2.context_size() > ctx1.context_size()

    def test_result_count(self):
        """result_count returns number of results."""
        request = JsonRpcRequest(id=1, method="tools/call")
        context = ExecutionContext.from_request(request).with_tool_call("test", {})

        assert context.result_count() == 0

        result = ToolCallResult(content=[TextContent(text="data")])
        ctx1 = context.with_result(result)
        ctx2 = ctx1.with_result(result)

        assert ctx1.result_count() == 1
        assert ctx2.result_count() == 2

    def test_with_reduced_results_keeps_recent(self):
        """with_reduced_results keeps only most recent results."""
        request = JsonRpcRequest(id=1, method="tools/call")
        context = ExecutionContext.from_request(request).with_tool_call("test", {})

        r1 = ToolCallResult(content=[TextContent(text="first")])
        r2 = ToolCallResult(content=[TextContent(text="second")])
        r3 = ToolCallResult(content=[TextContent(text="third")])

        ctx = context.with_result(r1).with_result(r2).with_result(r3)
        assert ctx.result_count() == 3

        # Reduce to 1 (most recent)
        reduced = ctx.with_reduced_results(1)
        assert reduced.result_count() == 1
        assert reduced.results[0].content[0].text == "third"

    def test_with_reduced_results_keeps_multiple(self):
        """with_reduced_results can keep multiple recent results."""
        request = JsonRpcRequest(id=1, method="tools/call")
        context = ExecutionContext.from_request(request).with_tool_call("test", {})

        r1 = ToolCallResult(content=[TextContent(text="first")])
        r2 = ToolCallResult(content=[TextContent(text="second")])
        r3 = ToolCallResult(content=[TextContent(text="third")])

        ctx = context.with_result(r1).with_result(r2).with_result(r3)
        reduced = ctx.with_reduced_results(2)

        assert reduced.result_count() == 2
        assert reduced.results[0].content[0].text == "second"
        assert reduced.results[1].content[0].text == "third"

    def test_with_reduced_results_zero_clears_all(self):
        """with_reduced_results(0) removes all results."""
        request = JsonRpcRequest(id=1, method="tools/call")
        context = ExecutionContext.from_request(request).with_tool_call("test", {})

        result = ToolCallResult(content=[TextContent(text="data")])
        ctx = context.with_result(result).with_result(result)

        reduced = ctx.with_reduced_results(0)
        assert reduced.result_count() == 0

    def test_with_reduced_results_rejects_negative(self):
        """with_reduced_results rejects negative max_results."""
        request = JsonRpcRequest(id=1, method="tools/call")
        context = ExecutionContext.from_request(request).with_tool_call("test", {})

        with pytest.raises(ContextError) as exc_info:
            context.with_reduced_results(-1)

        assert "non-negative" in str(exc_info.value)

    def test_with_reduced_results_rejects_sealed(self):
        """with_reduced_results rejects sealed context."""
        request = JsonRpcRequest(id=1, method="tools/call")
        context = ExecutionContext.from_request(request).with_tool_call("test", {})
        result = ToolCallResult(content=[TextContent(text="data")])
        ctx = context.with_result(result).seal()

        with pytest.raises(ContextError) as exc_info:
            ctx.with_reduced_results(1)

        assert "sealed" in str(exc_info.value)

    def test_repr_shows_size(self):
        """Repr includes context size when results exist."""
        request = JsonRpcRequest(id=1, method="tools/call")
        context = ExecutionContext.from_request(request).with_tool_call("test", {})
        result = ToolCallResult(content=[TextContent(text="data")])
        ctx = context.with_result(result)

        assert "size=" in repr(ctx)
