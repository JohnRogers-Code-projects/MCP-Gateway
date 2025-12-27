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
from rest_to_mcp.models import JsonRpcRequest


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
