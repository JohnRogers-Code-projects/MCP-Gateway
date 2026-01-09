"""
Tests for REST-to-MCP adapter.

Tests the core translation logic without hitting external APIs.
Uses httpx's mock transport for isolated testing.
"""

import json
from typing import Any

import httpx
import pytest

from rest_to_mcp.endpoints import HttpMethod, RestEndpoint
from rest_to_mcp.adapter import RestToMcpAdapter, JSONPLACEHOLDER_ENDPOINTS
from rest_to_mcp.errors import ContractViolation
from rest_to_mcp.models import JsonRpcRequest, ToolValidationError


# -----------------------------------------------------------------------------
# Mock HTTP Transport (local copy for tests that don't use fixtures)
# -----------------------------------------------------------------------------


class MockTransport(httpx.AsyncBaseTransport):
    """Mock transport that returns predefined responses."""

    def __init__(self, responses: dict[str, tuple[int, dict[str, Any]]]):
        self.responses = responses
        self.requests: list[httpx.Request] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)

        # Match by path
        path = request.url.path
        if path in self.responses:
            status, data = self.responses[path]
            return httpx.Response(status, json=data)

        return httpx.Response(404, json={"error": "Not found"})


# -----------------------------------------------------------------------------
# RestEndpoint Tests
# -----------------------------------------------------------------------------


class TestRestEndpoint:
    """Tests for REST endpoint definition and conversion."""

    def test_to_mcp_tool_simple(self):
        endpoint = RestEndpoint(
            name="get_items",
            path="/items",
            method=HttpMethod.GET,
            description="Get all items",
        )
        tool = endpoint.to_mcp_tool()
        
        assert tool.name == "get_items"
        assert tool.description == "Get all items"
        assert tool.inputSchema.properties == {}
        assert tool.inputSchema.required == []

    def test_to_mcp_tool_with_path_params(self):
        endpoint = RestEndpoint(
            name="get_item",
            path="/items/{id}",
            method=HttpMethod.GET,
            description="Get item by ID",
            path_params=["id"],
        )
        tool = endpoint.to_mcp_tool()
        
        assert "id" in tool.inputSchema.properties
        assert "id" in tool.inputSchema.required

    def test_to_mcp_tool_with_query_params(self):
        endpoint = RestEndpoint(
            name="search_items",
            path="/items",
            method=HttpMethod.GET,
            description="Search items",
            query_params=["q", "limit"],
        )
        tool = endpoint.to_mcp_tool()
        
        assert "q" in tool.inputSchema.properties
        assert "limit" in tool.inputSchema.properties
        # Query params are optional
        assert "q" not in tool.inputSchema.required

    def test_to_mcp_tool_with_body_params(self):
        endpoint = RestEndpoint(
            name="create_item",
            path="/items",
            method=HttpMethod.POST,
            description="Create item",
            body_params=["name", "value"],
        )
        tool = endpoint.to_mcp_tool()

        # Body params are required for POST
        assert "name" in tool.inputSchema.required
        assert "value" in tool.inputSchema.required


# -----------------------------------------------------------------------------
# Constrained Tool Invocation Tests (PR 4)
# -----------------------------------------------------------------------------


class TestRestEndpointValidation:
    """
    Tests for endpoint argument validation.

    CONSTRAINED BY DESIGN:
    - Tools receive ONLY declared parameters
    - Unknown arguments are REJECTED
    - There is no silent degradation
    """

    def test_validate_path_params_missing(self):
        """Missing path params must be rejected."""
        endpoint = RestEndpoint(
            name="get_item",
            path="/items/{id}",
            method=HttpMethod.GET,
            description="Get item by ID",
            path_params=["id"],
        )

        errors = endpoint.validate_arguments({})
        assert len(errors) == 1
        assert "path parameter" in errors[0]
        assert "'id'" in errors[0]

    def test_validate_path_params_empty_string(self):
        """Empty path params must be rejected."""
        endpoint = RestEndpoint(
            name="get_item",
            path="/items/{id}",
            method=HttpMethod.GET,
            description="Get item by ID",
            path_params=["id"],
        )

        errors = endpoint.validate_arguments({"id": "   "})
        assert len(errors) == 1
        assert "cannot be empty" in errors[0]

    def test_validate_path_params_present(self):
        """Valid path params pass validation."""
        endpoint = RestEndpoint(
            name="get_item",
            path="/items/{id}",
            method=HttpMethod.GET,
            description="Get item by ID",
            path_params=["id"],
        )

        errors = endpoint.validate_arguments({"id": "123"})
        assert errors == []

    def test_validate_body_params_missing_for_post(self):
        """Missing body params for POST must be rejected."""
        endpoint = RestEndpoint(
            name="create_item",
            path="/items",
            method=HttpMethod.POST,
            description="Create item",
            body_params=["name", "value"],
        )

        errors = endpoint.validate_arguments({})
        assert len(errors) == 2
        assert any("'name'" in e for e in errors)
        assert any("'value'" in e for e in errors)

    def test_validate_body_params_partial_for_post(self):
        """Partial body params for POST must be rejected."""
        endpoint = RestEndpoint(
            name="create_item",
            path="/items",
            method=HttpMethod.POST,
            description="Create item",
            body_params=["name", "value"],
        )

        errors = endpoint.validate_arguments({"name": "test"})
        assert len(errors) == 1
        assert "'value'" in errors[0]

    def test_validate_body_params_optional_for_get(self):
        """Body params are not required for GET."""
        endpoint = RestEndpoint(
            name="get_item",
            path="/items/{id}",
            method=HttpMethod.GET,
            description="Get item by ID",
            path_params=["id"],
            body_params=["optional_body"],  # Unusual but valid
        )

        errors = endpoint.validate_arguments({"id": "123"})
        assert errors == []

    def test_validate_query_params_optional(self):
        """Query params are always optional."""
        endpoint = RestEndpoint(
            name="search_items",
            path="/items",
            method=HttpMethod.GET,
            description="Search items",
            query_params=["q", "limit", "offset"],
        )

        # No query params provided - should be valid
        errors = endpoint.validate_arguments({})
        assert errors == []

    def test_validate_multiple_errors(self):
        """Multiple validation errors are collected."""
        endpoint = RestEndpoint(
            name="update_item",
            path="/items/{id}",
            method=HttpMethod.PUT,
            description="Update item",
            path_params=["id"],
            body_params=["name", "value"],
        )

        errors = endpoint.validate_arguments({})
        assert len(errors) == 3  # 1 path + 2 body

    # -------------------------------------------------------------------------
    # CONSTRAINED: Unknown arguments are REJECTED
    # -------------------------------------------------------------------------

    def test_validate_rejects_unknown_arguments(self):
        """Unknown arguments must be rejected - tools receive ONLY what they declare."""
        endpoint = RestEndpoint(
            name="get_item",
            path="/items/{id}",
            method=HttpMethod.GET,
            description="Get item by ID",
            path_params=["id"],
        )

        errors = endpoint.validate_arguments({"id": "123", "extra": "not_allowed"})
        assert len(errors) == 1
        assert "Unknown argument" in errors[0]
        assert "'extra'" in errors[0]
        assert "does not accept" in errors[0]

    def test_validate_rejects_multiple_unknown_arguments(self):
        """Multiple unknown arguments all rejected."""
        endpoint = RestEndpoint(
            name="get_items",
            path="/items",
            method=HttpMethod.GET,
            description="Get all items",
        )

        errors = endpoint.validate_arguments({"foo": "bar", "baz": "qux"})
        assert len(errors) == 2
        assert all("Unknown argument" in e for e in errors)

    def test_validate_allows_optional_query_params(self):
        """Optional query params are allowed but not required."""
        endpoint = RestEndpoint(
            name="search",
            path="/search",
            method=HttpMethod.GET,
            description="Search",
            query_params=["q", "limit"],
        )

        # Providing optional params is fine
        errors = endpoint.validate_arguments({"q": "test"})
        assert errors == []

        # But unknown params still rejected
        errors = endpoint.validate_arguments({"q": "test", "unknown": "bad"})
        assert len(errors) == 1
        assert "Unknown argument" in errors[0]


class TestToolValidationError:
    """Tests for ToolValidationError exception."""

    def test_exception_message(self):
        """Exception message includes tool name and all errors."""
        error = ToolValidationError("get_user", ["error 1", "error 2"])

        assert "get_user" in str(error)
        assert "error 1" in str(error)
        assert "error 2" in str(error)

    def test_exception_attributes(self):
        """Exception exposes tool name and errors."""
        error = ToolValidationError("get_user", ["missing id"])

        assert error.tool_name == "get_user"
        assert error.errors == ["missing id"]


# -----------------------------------------------------------------------------
# Deliberate Failure Mode Tests (PR 5)
# -----------------------------------------------------------------------------


class TestToolTimeoutError:
    """
    Tests for ToolTimeoutError exception.

    DELIBERATE FAILURE MODE: Timeouts are explicit, not hidden in catch-all.
    """

    def test_exception_message(self):
        """Exception message includes tool name and timeout."""
        from rest_to_mcp.models import ToolTimeoutError

        error = ToolTimeoutError("get_weather", 30.0)

        assert "get_weather" in str(error)
        assert "30.0" in str(error)
        assert "timed out" in str(error)

    def test_exception_attributes(self):
        """Exception exposes tool name and timeout."""
        from rest_to_mcp.models import ToolTimeoutError

        error = ToolTimeoutError("get_weather", 30.0)

        assert error.tool_name == "get_weather"
        assert error.timeout_seconds == 30.0


class TestDeliberateFailureModes:
    """
    Tests for deliberate failure handling.

    EXPLICIT FAILURES:
    - Timeouts are caught and raised as ToolTimeoutError
    - Orchestration handles the error with structured response
    - Failure mode is visible in the response data
    """

    @pytest.fixture
    def timeout_adapter(self):
        """Create adapter that will timeout."""
        # Use a mock transport that raises TimeoutException
        import httpx

        class TimeoutTransport(httpx.AsyncBaseTransport):
            async def handle_async_request(self, request):
                raise httpx.TimeoutException("Connection timed out")

        adapter = RestToMcpAdapter(
            base_url="https://api.example.com",
            endpoints=[
                RestEndpoint(
                    name="slow_endpoint",
                    path="/slow",
                    method=HttpMethod.GET,
                    description="An endpoint that times out",
                ),
            ],
        )
        adapter._client = httpx.AsyncClient(transport=TimeoutTransport())
        return adapter

    @pytest.mark.asyncio
    async def test_call_tool_raises_timeout_error(self, timeout_adapter):
        """call_tool raises ToolTimeoutError on timeout."""
        from rest_to_mcp.models import ToolTimeoutError

        with pytest.raises(ToolTimeoutError) as exc_info:
            await timeout_adapter.call_tool("slow_endpoint", {})

        assert exc_info.value.tool_name == "slow_endpoint"
        assert exc_info.value.timeout_seconds > 0

    @pytest.mark.asyncio
    async def test_handle_request_returns_timeout_error(self, timeout_adapter):
        """handle_request returns structured error on timeout."""
        request = JsonRpcRequest(
            id=1,
            method="tools/call",
            params={"name": "slow_endpoint", "arguments": {}},
        )

        response, context = await timeout_adapter.handle_request(request)

        assert hasattr(response, "error")
        assert response.error.code == -32603  # INTERNAL_ERROR
        assert "timed out" in response.error.message
        assert response.error.data is not None
        assert response.error.data["failure_mode"] == "timeout"
        assert response.error.data["tool"] == "slow_endpoint"
        assert context.is_sealed

    @pytest.mark.asyncio
    async def test_timeout_preserves_context_state(self, timeout_adapter):
        """Timeout preserves context with tool binding but no result."""
        request = JsonRpcRequest(
            id=1,
            method="tools/call",
            params={"name": "slow_endpoint", "arguments": {}},
        )

        response, context = await timeout_adapter.handle_request(request)

        # Context was bound to tool before timeout
        assert context.tool_name == "slow_endpoint"
        # But no result was recorded (tool didn't complete)
        assert len(context.results) == 0


class TestDestructiveOperationGuards:
    """
    Tests for orchestration-level guards on destructive operations.

    ORCHESTRATION POLICY:
    - Guards live in orchestration, not in tools
    - Tools are dumb - they don't know they're being guarded
    - Invalid operations are blocked before tool execution
    """

    @pytest.fixture
    def adapter_with_delete(self):
        """Create adapter with delete_post and update_post endpoints."""
        adapter = RestToMcpAdapter(
            base_url="https://api.example.com",
            endpoints=[
                RestEndpoint(
                    name="delete_post",
                    path="/posts/{id}",
                    method=HttpMethod.DELETE,
                    description="Delete a post by ID",
                    path_params=["id"],
                ),
                RestEndpoint(
                    name="update_post",
                    path="/posts/{id}",
                    method=HttpMethod.PUT,
                    description="Update a post",
                    path_params=["id"],
                    body_params=["title", "body", "userId"],
                ),
            ],
        )
        return adapter

    @pytest.mark.asyncio
    async def test_orchestration_guards_delete_with_zero_id(self, adapter_with_delete):
        """Orchestration rejects delete_post with id=0."""
        request = JsonRpcRequest(
            id=1,
            method="tools/call",
            params={"name": "delete_post", "arguments": {"id": "0"}},
        )

        response, _ = await adapter_with_delete.handle_request(request)

        assert hasattr(response, "error")
        assert "Destructive operation rejected" in response.error.message

    @pytest.mark.asyncio
    async def test_orchestration_guards_delete_with_negative_id(self, adapter_with_delete):
        """Orchestration rejects delete_post with negative id."""
        request = JsonRpcRequest(
            id=1,
            method="tools/call",
            params={"name": "delete_post", "arguments": {"id": "-5"}},
        )

        response, _ = await adapter_with_delete.handle_request(request)

        assert hasattr(response, "error")
        assert "Destructive operation rejected" in response.error.message
        assert "positive integers" in response.error.message

    @pytest.mark.asyncio
    async def test_orchestration_guards_delete_with_non_numeric_id(self, adapter_with_delete):
        """Orchestration rejects delete_post with non-numeric id."""
        request = JsonRpcRequest(
            id=1,
            method="tools/call",
            params={"name": "delete_post", "arguments": {"id": "abc"}},
        )

        response, _ = await adapter_with_delete.handle_request(request)

        assert hasattr(response, "error")
        assert "Destructive operation rejected" in response.error.message
        assert "not a valid integer" in response.error.message

    @pytest.mark.asyncio
    async def test_orchestration_guards_update_with_zero_id(self, adapter_with_delete):
        """Orchestration rejects update_post with id=0."""
        request = JsonRpcRequest(
            id=1,
            method="tools/call",
            params={
                "name": "update_post",
                "arguments": {"id": "0", "title": "x", "body": "y", "userId": "1"},
            },
        )

        response, _ = await adapter_with_delete.handle_request(request)

        assert hasattr(response, "error")
        assert "Destructive operation rejected" in response.error.message

    @pytest.mark.asyncio
    async def test_orchestration_guards_update_with_non_numeric_id(self, adapter_with_delete):
        """Orchestration rejects update_post with non-numeric id."""
        request = JsonRpcRequest(
            id=1,
            method="tools/call",
            params={
                "name": "update_post",
                "arguments": {"id": "not_a_number", "title": "x", "body": "y", "userId": "1"},
            },
        )

        response, _ = await adapter_with_delete.handle_request(request)

        assert hasattr(response, "error")
        assert "Destructive operation rejected" in response.error.message
        assert "not a valid integer" in response.error.message


# -----------------------------------------------------------------------------
# RestToMcpAdapter Tests
# -----------------------------------------------------------------------------


class TestRestToMcpAdapter:
    """Tests for the adapter's MCP protocol handling."""

    @pytest.fixture
    def mock_adapter(self):
        """Create adapter with mock HTTP client."""
        adapter = RestToMcpAdapter(
            base_url="https://api.example.com",
            endpoints=[
                RestEndpoint(
                    name="get_items",
                    path="/items",
                    method=HttpMethod.GET,
                    description="Get all items",
                ),
                RestEndpoint(
                    name="get_item",
                    path="/items/{id}",
                    method=HttpMethod.GET,
                    description="Get item by ID",
                    path_params=["id"],
                ),
                RestEndpoint(
                    name="create_item",
                    path="/items",
                    method=HttpMethod.POST,
                    description="Create item",
                    body_params=["name"],
                ),
            ],
        )
        
        # Inject mock transport
        transport = MockTransport({
            "/items": (200, [{"id": 1, "name": "Item 1"}]),
            "/items/1": (200, {"id": 1, "name": "Item 1"}),
            "/items/999": (404, {"error": "Not found"}),
        })
        adapter._client = httpx.AsyncClient(
            base_url="https://api.example.com",
            transport=transport,
        )
        
        return adapter, transport

    def test_list_tools(self, mock_adapter):
        adapter, _ = mock_adapter
        tools = adapter.list_tools()
        
        assert len(tools) == 3
        names = [t.name for t in tools]
        assert "get_items" in names
        assert "get_item" in names
        assert "create_item" in names

    @pytest.mark.asyncio
    async def test_call_tool_success(self, mock_adapter):
        adapter, transport = mock_adapter
        result = await adapter.call_tool("get_items", {})
        
        assert not result.isError
        assert len(result.content) == 1
        assert "Item 1" in result.content[0].text

    @pytest.mark.asyncio
    async def test_call_tool_with_path_param(self, mock_adapter):
        adapter, transport = mock_adapter
        result = await adapter.call_tool("get_item", {"id": "1"})
        
        assert not result.isError
        # Verify the path was constructed correctly
        assert transport.requests[-1].url.path == "/items/1"

    @pytest.mark.asyncio
    async def test_call_tool_unknown_tool(self, mock_adapter):
        """Unknown tool raises ContractViolation (ambiguity hard-fail)."""
        adapter, _ = mock_adapter
        with pytest.raises(ContractViolation) as exc_info:
            await adapter.call_tool("nonexistent", {})

        assert "Unknown tool" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_call_tool_http_error_response(self, mock_adapter):
        adapter, _ = mock_adapter
        result = await adapter.call_tool("get_item", {"id": "999"})
        
        # 404 responses should set isError=True
        assert result.isError

    @pytest.mark.asyncio
    async def test_handle_request_initialize(self, mock_adapter):
        adapter, _ = mock_adapter
        request = JsonRpcRequest(id=1, method="initialize")

        response, context = await adapter.handle_request(request)

        assert response.id == 1
        assert "protocolVersion" in response.result
        assert "capabilities" in response.result
        assert context.request_id == 1
        assert context.method == "initialize"
        assert context.is_sealed  # Context must be sealed on return

    @pytest.mark.asyncio
    async def test_handle_request_tools_list(self, mock_adapter):
        adapter, _ = mock_adapter
        request = JsonRpcRequest(id=2, method="tools/list")

        response, context = await adapter.handle_request(request)

        assert response.id == 2
        assert "tools" in response.result
        assert len(response.result["tools"]) == 3
        assert context.method == "tools/list"
        assert context.is_sealed  # Context must be sealed on return

    @pytest.mark.asyncio
    async def test_handle_request_tools_call(self, mock_adapter):
        adapter, _ = mock_adapter
        request = JsonRpcRequest(
            id=3,
            method="tools/call",
            params={"name": "get_items", "arguments": {}},
        )

        response, context = await adapter.handle_request(request)

        assert response.id == 3
        assert "content" in response.result
        assert context.tool_name == "get_items"
        assert len(context.results) == 1
        assert context.is_sealed  # Context must be sealed on return

    @pytest.mark.asyncio
    async def test_handle_request_unknown_method(self, mock_adapter):
        adapter, _ = mock_adapter
        request = JsonRpcRequest(id=4, method="unknown/method")

        response, context = await adapter.handle_request(request)

        assert hasattr(response, "error")
        assert response.error.code == -32601  # METHOD_NOT_FOUND
        assert context.method == "unknown/method"
        assert context.is_sealed  # Context must be sealed even on error

    @pytest.mark.asyncio
    async def test_handle_request_missing_params(self, mock_adapter):
        adapter, _ = mock_adapter
        request = JsonRpcRequest(id=5, method="tools/call", params=None)

        response, context = await adapter.handle_request(request)

        assert hasattr(response, "error")
        assert response.error.code == -32602  # INVALID_PARAMS
        assert context.is_sealed  # Context must be sealed even on error

    @pytest.mark.asyncio
    async def test_call_tool_is_dumb_executor(self, mock_adapter):
        """call_tool does NOT validate - it's a dumb executor."""
        adapter, _ = mock_adapter

        # call_tool with missing params does NOT raise - it just tries to execute
        # Validation is orchestration's job, not the tool's job
        result = await adapter.call_tool("get_items", {})
        # It succeeds because get_items has no required params
        assert not result.isError

    @pytest.mark.asyncio
    async def test_handle_request_validates_at_orchestration_layer(self, mock_adapter):
        """Validation happens in orchestration (handle_request), not in tool."""
        adapter, _ = mock_adapter
        request = JsonRpcRequest(
            id=6,
            method="tools/call",
            params={"name": "get_item", "arguments": {}},  # Missing 'id'
        )

        response, context = await adapter.handle_request(request)

        # Orchestration caught the validation error
        assert hasattr(response, "error")
        assert response.error.code == -32602  # INVALID_PARAMS
        assert "get_item" in response.error.message
        assert response.error.data is not None
        assert response.error.data["tool"] == "get_item"
        assert len(response.error.data["errors"]) == 1
        assert context.is_sealed

    @pytest.mark.asyncio
    async def test_handle_request_validation_error_preserves_context(self, mock_adapter):
        """Validation errors should preserve tool binding in context."""
        adapter, _ = mock_adapter
        request = JsonRpcRequest(
            id=7,
            method="tools/call",
            params={"name": "get_item", "arguments": {}},
        )

        response, context = await adapter.handle_request(request)

        # Context should still have tool_name bound even on validation failure
        assert context.tool_name == "get_item"
        # But no results (tool never executed)
        assert len(context.results) == 0


# -----------------------------------------------------------------------------
# JSONPlaceholder Endpoints Tests
# -----------------------------------------------------------------------------


class TestJsonPlaceholderEndpoints:
    """Tests for the pre-configured JSONPlaceholder endpoints."""

    def test_endpoints_defined(self):
        assert len(JSONPLACEHOLDER_ENDPOINTS) == 8

    def test_all_endpoints_have_descriptions(self):
        for endpoint in JSONPLACEHOLDER_ENDPOINTS:
            assert endpoint.description, f"{endpoint.name} missing description"

    def test_endpoint_names_unique(self):
        names = [e.name for e in JSONPLACEHOLDER_ENDPOINTS]
        assert len(names) == len(set(names)), "Duplicate endpoint names"

    def test_crud_operations_covered(self):
        methods = {e.method for e in JSONPLACEHOLDER_ENDPOINTS}
        assert HttpMethod.GET in methods
        assert HttpMethod.POST in methods
        assert HttpMethod.PUT in methods
        assert HttpMethod.DELETE in methods


# -----------------------------------------------------------------------------
# Multi-API Tests
# -----------------------------------------------------------------------------


class TestMultiApiSupport:
    """Tests for multi-API composition feature."""

    def test_open_meteo_endpoints_defined(self):
        from rest_to_mcp.endpoints import OPEN_METEO_ENDPOINTS
        assert len(OPEN_METEO_ENDPOINTS) == 2
        names = [e.name for e in OPEN_METEO_ENDPOINTS]
        assert "get_weather" in names
        assert "get_forecast" in names

    def test_open_meteo_endpoints_have_base_url(self):
        from rest_to_mcp.endpoints import OPEN_METEO_ENDPOINTS
        from rest_to_mcp.config import OPEN_METEO_BASE_URL
        for endpoint in OPEN_METEO_ENDPOINTS:
            assert endpoint.base_url == OPEN_METEO_BASE_URL

    def test_default_endpoints_combines_apis(self):
        from rest_to_mcp.endpoints import DEFAULT_ENDPOINTS
        # 8 JSONPlaceholder + 2 Open-Meteo
        assert len(DEFAULT_ENDPOINTS) == 10

    def test_multi_api_adapter_has_all_tools(self):
        from rest_to_mcp.adapter import create_multi_api_adapter
        adapter = create_multi_api_adapter()
        tools = adapter.list_tools()
        tool_names = [t.name for t in tools]
        # JSONPlaceholder tools
        assert "get_user" in tool_names
        assert "get_posts" in tool_names
        # Open-Meteo tools
        assert "get_weather" in tool_names
        assert "get_forecast" in tool_names

    def test_endpoint_with_base_url_generates_full_url(self):
        """Verify that endpoint-specific base_url is used in URL construction."""
        from rest_to_mcp.endpoints import RestEndpoint, HttpMethod
        from rest_to_mcp.config import OPEN_METEO_BASE_URL

        endpoint = RestEndpoint(
            name="test_weather",
            path="/v1/forecast",
            method=HttpMethod.GET,
            description="Test weather endpoint",
            query_params=["latitude"],
            base_url=OPEN_METEO_BASE_URL,
        )

        # The endpoint should have its own base_url
        assert endpoint.base_url == "https://api.open-meteo.com"


# -----------------------------------------------------------------------------
# Domain Adapter Isolation Tests
# -----------------------------------------------------------------------------


class TestDomainAdapterIsolation:
    """Tests verifying domain-specific endpoints are properly isolated."""

    def test_domain_modules_exist(self):
        """Domain modules should be importable directly."""
        from rest_to_mcp.domains import jsonplaceholder, openmeteo
        assert hasattr(jsonplaceholder, "JSONPLACEHOLDER_ENDPOINTS")
        assert hasattr(openmeteo, "OPEN_METEO_ENDPOINTS")

    def test_domain_endpoints_match_aggregated(self):
        """Endpoints imported from domains should match aggregated list."""
        from rest_to_mcp.domains.jsonplaceholder import JSONPLACEHOLDER_ENDPOINTS as jp_direct
        from rest_to_mcp.domains.openmeteo import OPEN_METEO_ENDPOINTS as om_direct
        from rest_to_mcp.endpoints import (
            JSONPLACEHOLDER_ENDPOINTS as jp_aggregated,
            OPEN_METEO_ENDPOINTS as om_aggregated,
        )
        assert jp_direct is jp_aggregated
        assert om_direct is om_aggregated

    def test_domain_isolation_jsonplaceholder_has_no_base_url(self):
        """JSONPlaceholder endpoints use adapter's base_url (no per-endpoint base_url)."""
        from rest_to_mcp.domains.jsonplaceholder import JSONPLACEHOLDER_ENDPOINTS
        for endpoint in JSONPLACEHOLDER_ENDPOINTS:
            assert endpoint.base_url is None

    def test_domain_isolation_openmeteo_has_base_url(self):
        """Open-Meteo endpoints have their own base_url."""
        from rest_to_mcp.domains.openmeteo import OPEN_METEO_ENDPOINTS
        from rest_to_mcp.config import OPEN_METEO_BASE_URL
        for endpoint in OPEN_METEO_ENDPOINTS:
            assert endpoint.base_url == OPEN_METEO_BASE_URL

    def test_adding_domain_pattern(self):
        """
        Verify the pattern for adding a new domain.

        A new domain should only require:
        1. Creating domains/newdomain.py with NEWDOMAIN_ENDPOINTS
        2. Importing in endpoints.py (or directly where needed)

        This test documents the pattern without adding an actual domain.
        """
        from rest_to_mcp.endpoints import RestEndpoint, HttpMethod

        # Simulating a new domain definition
        MOCK_DOMAIN_ENDPOINTS = [
            RestEndpoint(
                name="mock_operation",
                path="/mock",
                method=HttpMethod.GET,
                description="Mock operation for pattern test",
                base_url="https://mock.example.com",
            ),
        ]

        # The pattern: new endpoints can be registered without modifying adapter
        from rest_to_mcp.adapter import RestToMcpAdapter
        from rest_to_mcp.config import JSONPLACEHOLDER_BASE_URL

        adapter = RestToMcpAdapter(
            base_url=JSONPLACEHOLDER_BASE_URL,
            endpoints=MOCK_DOMAIN_ENDPOINTS,
        )

        tools = adapter.list_tools()
        assert len(tools) == 1
        assert tools[0].name == "mock_operation"


# -----------------------------------------------------------------------------
# Playground Cross-Step Data Flow Tests
# -----------------------------------------------------------------------------


class TestPlaygroundDataFlow:
    """Tests for cross-step result extraction in playground scenarios."""

    def test_extract_nested_value_simple(self):
        from rest_to_mcp.playground import extract_nested_value
        data = {"name": "John", "age": 30}
        assert extract_nested_value(data, "name") == "John"
        assert extract_nested_value(data, "age") == 30

    def test_extract_nested_value_deep(self):
        from rest_to_mcp.playground import extract_nested_value
        data = {"address": {"geo": {"lat": "-68.6102", "lng": "-47.0653"}}}
        assert extract_nested_value(data, "address.geo.lat") == "-68.6102"
        assert extract_nested_value(data, "address.geo.lng") == "-47.0653"

    def test_extract_nested_value_missing(self):
        from rest_to_mcp.playground import extract_nested_value
        data = {"name": "John"}
        assert extract_nested_value(data, "address.geo.lat") is None

    def test_substitute_args_with_previous_results(self):
        from rest_to_mcp.playground import substitute_args

        previous_results = [
            {
                "tool": "get_user",
                "parsed_data": {
                    "id": 3,
                    "name": "Clementine Bauch",
                    "address": {"geo": {"lat": "-68.6102", "lng": "-47.0653"}},
                },
            }
        ]

        args_template = {
            "latitude": "$result.0.address.geo.lat",
            "longitude": "$result.0.address.geo.lng",
        }

        result = substitute_args(args_template, [], previous_results)
        assert result["latitude"] == "-68.6102"
        assert result["longitude"] == "-47.0653"

    def test_weather_scenario_patterns(self):
        from rest_to_mcp.playground import match_scenario

        # Test various phrasings that should match the weather scenario
        test_inputs = [
            "Check weather for user 3",
            "Get the weather for user 3",
            "What's the weather at user 3",
            "user 3 weather",
        ]

        for input_text in test_inputs:
            scenario, captures = match_scenario(input_text)
            assert scenario is not None, f"Failed to match: {input_text}"
            assert scenario.id == "user_weather", f"Wrong scenario for: {input_text}"
            assert "3" in captures, f"Failed to capture user ID from: {input_text}"

    def test_build_summary_handles_missing_user(self):
        """Test that build_summary returns helpful error when user not found."""
        from rest_to_mcp.playground import build_summary, SCENARIOS

        # Find the user_weather scenario
        scenario = next(s for s in SCENARIOS if s.id == "user_weather")

        # Simulate results where user was not found (empty response from JSONPlaceholder)
        results = [
            {
                "tool": "get_user",
                "result": {"content": [{"type": "text", "text": "{}"}]},
                "parsed_data": {},  # Empty - user doesn't exist
            }
        ]

        summary = build_summary(scenario, results)
        assert "could not be completed" in summary.lower() or "not found" in summary.lower()
        assert "error" in summary.lower() or "⚠️" in summary

    def test_build_summary_success(self):
        """Test that build_summary returns correct output for successful weather lookup."""
        import json
        from rest_to_mcp.playground import build_summary, SCENARIOS

        scenario = next(s for s in SCENARIOS if s.id == "user_weather")

        user_data = {
            "id": 3,
            "name": "Clementine Bauch",
            "address": {"geo": {"lat": "-68.6102", "lng": "-47.0653"}},
        }
        weather_data = {
            "current_weather": {"temperature": -5.2, "weathercode": 71}
        }

        # build_summary expects result in the format returned by adapter
        results = [
            {
                "tool": "get_user",
                "result": {"content": [{"type": "text", "text": json.dumps(user_data)}]},
            },
            {
                "tool": "get_weather",
                "result": {"content": [{"type": "text", "text": json.dumps(weather_data)}]},
            },
        ]

        summary = build_summary(scenario, results)
        assert "Clementine Bauch" in summary
        assert "-5.2" in summary
        assert "snow" in summary.lower()  # weathercode 71 = Slight snow

    def test_example_queries_include_error_demo(self):
        """Verify that example queries include an error handling demonstration."""
        from rest_to_mcp.playground import EXAMPLE_QUERIES

        assert len(EXAMPLE_QUERIES) == 5
        # Should include a query that will fail (user 999 doesn't exist)
        error_demo = [q for q in EXAMPLE_QUERIES if "999" in q]
        assert len(error_demo) == 1, "Should have one error demo query with non-existent user"
