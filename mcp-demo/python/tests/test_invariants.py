"""
Invariant Enforcement Tests

These tests exist ONLY to verify that invariant violations fail immediately.
They are NOT feature tests. They are NOT happy-path tests.

Each test asserts: "If you violate this invariant, you get a typed failure."

See docs/INVARIANTS.md for the invariant registry.
"""

import pytest
from pydantic import ValidationError

from rest_to_mcp.adapter import RestToMcpAdapter
from rest_to_mcp.endpoints import HttpMethod, RestEndpoint
from rest_to_mcp.errors import ContractViolation, GatewayFailure
from rest_to_mcp.models import (
    ExecutionContext,
    JsonRpcRequest,
    JsonRpcResponse,
    ToolCallParams,
    ContextError,
)


# -----------------------------------------------------------------------------
# INV-1: Failure Authority
# No raw exception may escape the gateway boundary.
# -----------------------------------------------------------------------------


class TestFailureAuthority:
    """Verify all gateway failures are typed GatewayFailure instances."""

    def test_context_error_is_gateway_failure(self):
        """ContextError must be a GatewayFailure subclass."""
        assert issubclass(ContextError, GatewayFailure)

    def test_contract_violation_is_gateway_failure(self):
        """ContractViolation must be a GatewayFailure subclass."""
        assert issubclass(ContractViolation, GatewayFailure)


# -----------------------------------------------------------------------------
# INV-2: Ambiguity Hard-Fail
# Ambiguous inputs must fail immediately.
# -----------------------------------------------------------------------------


class TestAmbiguityHardFail:
    """Verify ambiguous inputs cause immediate failure."""

    def test_empty_request_id_fails(self):
        """Empty string request ID must be rejected."""
        request = JsonRpcRequest(id="", method="initialize")
        with pytest.raises(ContextError) as exc_info:
            ExecutionContext.from_request(request)
        assert "empty" in str(exc_info.value).lower()

    def test_whitespace_method_fails(self):
        """Whitespace-only method must be rejected."""
        request = JsonRpcRequest(id=1, method="   ")
        with pytest.raises(ContextError) as exc_info:
            ExecutionContext.from_request(request)
        assert "empty" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_unknown_tool_fails(self):
        """Unknown tool name must raise ContractViolation."""
        adapter = RestToMcpAdapter(
            base_url="https://example.com",
            endpoints=[],
        )
        with pytest.raises(ContractViolation) as exc_info:
            await adapter._call_tool("nonexistent", {})
        assert "Unknown tool" in str(exc_info.value)

    def test_unknown_arguments_rejected(self):
        """Unknown arguments must be rejected by validation."""
        endpoint = RestEndpoint(
            name="get_item",
            path="/items/{id}",
            method=HttpMethod.GET,
            description="Get item",
            path_params=["id"],
        )
        errors = endpoint.validate_arguments({"id": "1", "unknown": "bad"})
        assert len(errors) == 1
        assert "Unknown argument" in errors[0]


# -----------------------------------------------------------------------------
# INV-3: Validation Authority
# Invalid MCP cannot be instantiated.
# -----------------------------------------------------------------------------


class TestValidationAuthority:
    """Verify MCP validation is un-bypassable."""

    def test_extra_fields_rejected_in_request(self):
        """Extra fields in JsonRpcRequest must be rejected."""
        with pytest.raises(ValidationError):
            JsonRpcRequest(
                id=1,
                method="initialize",
                extra_field="not_allowed",
            )

    def test_extra_fields_rejected_in_response(self):
        """Extra fields in JsonRpcResponse must be rejected."""
        with pytest.raises(ValidationError):
            JsonRpcResponse(
                id=1,
                result={},
                extra_field="not_allowed",
            )

    def test_extra_fields_rejected_in_tool_call_params(self):
        """Extra fields in ToolCallParams must be rejected."""
        with pytest.raises(ValidationError):
            ToolCallParams(
                name="test",
                arguments={},
                extra_field="not_allowed",
            )


# -----------------------------------------------------------------------------
# INV-4: Execution Authority
# Execution methods are private.
# -----------------------------------------------------------------------------


class TestExecutionAuthority:
    """Verify execution paths are structurally restricted."""

    def test_call_tool_is_private(self):
        """call_tool must be private (underscore prefix)."""
        adapter = RestToMcpAdapter(base_url="https://example.com", endpoints=[])
        # Public method should not exist
        assert not hasattr(adapter, "call_tool")
        # Private method should exist
        assert hasattr(adapter, "_call_tool")

    def test_list_tools_is_private(self):
        """list_tools must be private (underscore prefix)."""
        adapter = RestToMcpAdapter(base_url="https://example.com", endpoints=[])
        # Public method should not exist
        assert not hasattr(adapter, "list_tools")
        # Private method should exist
        assert hasattr(adapter, "_list_tools")


# -----------------------------------------------------------------------------
# INV-5: State Immutability
# Tool registry cannot be mutated after construction.
# -----------------------------------------------------------------------------


class TestStateImmutability:
    """Verify tool registry is frozen after construction."""

    def test_registry_mutation_raises_typeerror(self):
        """Direct registry mutation must raise TypeError."""
        adapter = RestToMcpAdapter(
            base_url="https://example.com",
            endpoints=[
                RestEndpoint(
                    name="test",
                    path="/test",
                    method=HttpMethod.GET,
                    description="Test endpoint",
                ),
            ],
        )
        with pytest.raises(TypeError):
            adapter.endpoints["new_tool"] = "should_fail"

    def test_registry_deletion_raises_typeerror(self):
        """Registry item deletion must raise TypeError."""
        adapter = RestToMcpAdapter(
            base_url="https://example.com",
            endpoints=[
                RestEndpoint(
                    name="test",
                    path="/test",
                    method=HttpMethod.GET,
                    description="Test endpoint",
                ),
            ],
        )
        with pytest.raises(TypeError):
            del adapter.endpoints["test"]

    def test_register_endpoint_removed(self):
        """register_endpoint method must not exist."""
        adapter = RestToMcpAdapter(base_url="https://example.com", endpoints=[])
        assert not hasattr(adapter, "register_endpoint")


# -----------------------------------------------------------------------------
# INV-6: Context Sealing
# Sealed contexts cannot be mutated.
# -----------------------------------------------------------------------------


class TestContextSealing:
    """Verify sealed contexts reject mutation."""

    def test_sealed_context_rejects_tool_call(self):
        """with_tool_call on sealed context must raise ContextError."""
        request = JsonRpcRequest(id=1, method="test")
        context = ExecutionContext.from_request(request)
        context.seal()

        with pytest.raises(ContextError) as exc_info:
            context.with_tool_call("tool", {})
        assert "sealed" in str(exc_info.value).lower()

    def test_sealed_context_rejects_result(self):
        """with_result on sealed context must raise ContextError."""
        request = JsonRpcRequest(id=1, method="test")
        context = ExecutionContext.from_request(request)
        context = context.with_tool_call("tool", {})
        context.seal()

        from rest_to_mcp.models import ToolCallResult, TextContent

        result = ToolCallResult(content=[TextContent(text="test")])
        with pytest.raises(ContextError) as exc_info:
            context.with_result(result)
        assert "sealed" in str(exc_info.value).lower()

    def test_sealed_context_rejects_discard(self):
        """discard_results on sealed context must raise ContextError."""
        request = JsonRpcRequest(id=1, method="test")
        context = ExecutionContext.from_request(request)
        context.seal()

        with pytest.raises(ContextError) as exc_info:
            context.discard_results()
        assert "sealed" in str(exc_info.value).lower()
