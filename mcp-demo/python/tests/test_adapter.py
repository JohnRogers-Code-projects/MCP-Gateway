"""
Tests for REST-to-MCP adapter.

Tests the core translation logic without hitting external APIs.
Uses httpx's mock transport for isolated testing.
"""

import json

import httpx
import pytest

from rest_to_mcp.adapter import (
    HttpMethod,
    RestEndpoint,
    RestToMcpAdapter,
    JSONPLACEHOLDER_ENDPOINTS,
)
from rest_to_mcp.models import JsonRpcRequest


# -----------------------------------------------------------------------------
# Mock HTTP Transport
# -----------------------------------------------------------------------------


class MockTransport(httpx.AsyncBaseTransport):
    """Mock transport that returns predefined responses."""

    def __init__(self, responses: dict[str, tuple[int, dict]]):
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
        adapter, _ = mock_adapter
        result = await adapter.call_tool("nonexistent", {})
        
        assert result.isError
        assert "Unknown tool" in result.content[0].text

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
        
        response = await adapter.handle_request(request)
        
        assert response.id == 1
        assert "protocolVersion" in response.result
        assert "capabilities" in response.result

    @pytest.mark.asyncio
    async def test_handle_request_tools_list(self, mock_adapter):
        adapter, _ = mock_adapter
        request = JsonRpcRequest(id=2, method="tools/list")
        
        response = await adapter.handle_request(request)
        
        assert response.id == 2
        assert "tools" in response.result
        assert len(response.result["tools"]) == 3

    @pytest.mark.asyncio
    async def test_handle_request_tools_call(self, mock_adapter):
        adapter, _ = mock_adapter
        request = JsonRpcRequest(
            id=3,
            method="tools/call",
            params={"name": "get_items", "arguments": {}},
        )
        
        response = await adapter.handle_request(request)
        
        assert response.id == 3
        assert "content" in response.result

    @pytest.mark.asyncio
    async def test_handle_request_unknown_method(self, mock_adapter):
        adapter, _ = mock_adapter
        request = JsonRpcRequest(id=4, method="unknown/method")
        
        response = await adapter.handle_request(request)
        
        assert hasattr(response, "error")
        assert response.error.code == -32601  # METHOD_NOT_FOUND

    @pytest.mark.asyncio
    async def test_handle_request_missing_params(self, mock_adapter):
        adapter, _ = mock_adapter
        request = JsonRpcRequest(id=5, method="tools/call", params=None)
        
        response = await adapter.handle_request(request)
        
        assert hasattr(response, "error")
        assert response.error.code == -32602  # INVALID_PARAMS


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
