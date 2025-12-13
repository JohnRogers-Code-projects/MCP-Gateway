"""
Shared test fixtures for REST-to-MCP adapter tests.

Provides reusable mock transports, adapters, and test data.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from rest_to_mcp.endpoints import HttpMethod, RestEndpoint
from rest_to_mcp.adapter import RestToMcpAdapter


# -----------------------------------------------------------------------------
# Mock HTTP Transport
# -----------------------------------------------------------------------------


class MockTransport(httpx.AsyncBaseTransport):
    """
    Mock transport that returns predefined responses.

    Useful for testing HTTP interactions without hitting real APIs.
    """

    def __init__(self, responses: dict[str, tuple[int, dict[str, Any]]]):
        """
        Initialize mock transport with predefined responses.

        Args:
            responses: Dict mapping URL paths to (status_code, response_data) tuples
        """
        self.responses = responses
        self.requests: list[httpx.Request] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        """Handle an async request by returning a predefined response."""
        self.requests.append(request)

        # Match by path
        path = request.url.path
        if path in self.responses:
            status, data = self.responses[path]
            return httpx.Response(status, json=data)

        return httpx.Response(404, json={"error": "Not found"})


# -----------------------------------------------------------------------------
# Test Data
# -----------------------------------------------------------------------------


MOCK_USER_DATA = {
    "id": 1,
    "name": "Leanne Graham",
    "username": "Bret",
    "email": "Sincere@april.biz",
    "address": {
        "street": "Kulas Light",
        "suite": "Apt. 556",
        "city": "Gwenborough",
        "zipcode": "92998-3874",
        "geo": {"lat": "-37.3159", "lng": "81.1496"},
    },
}

MOCK_POST_DATA = {
    "id": 1,
    "userId": 1,
    "title": "sunt aut facere repellat provident occaecati excepturi optio reprehenderit",
    "body": "quia et suscipit...",
}

MOCK_WEATHER_DATA = {
    "current_weather": {
        "temperature": 15.5,
        "windspeed": 10.2,
        "weathercode": 0,
    }
}


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def mock_transport() -> MockTransport:
    """Create a mock transport with common responses."""
    return MockTransport({
        "/items": (200, [{"id": 1, "name": "Item 1"}]),
        "/items/1": (200, {"id": 1, "name": "Item 1"}),
        "/items/999": (404, {"error": "Not found"}),
        "/users/1": (200, MOCK_USER_DATA),
        "/posts/1": (200, MOCK_POST_DATA),
    })


@pytest.fixture
def sample_endpoints() -> list[RestEndpoint]:
    """Create a sample list of endpoints for testing."""
    return [
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
    ]


@pytest.fixture
def mock_adapter(
    sample_endpoints: list[RestEndpoint],
    mock_transport: MockTransport,
) -> tuple[RestToMcpAdapter, MockTransport]:
    """Create an adapter with mock HTTP client."""
    adapter = RestToMcpAdapter(
        base_url="https://api.example.com",
        endpoints=sample_endpoints,
    )

    # Inject mock transport
    adapter._client = httpx.AsyncClient(
        base_url="https://api.example.com",
        transport=mock_transport,
    )

    return adapter, mock_transport


@pytest.fixture
def user_weather_results() -> list[dict[str, Any]]:
    """Sample results for user weather scenario testing."""
    import json

    return [
        {
            "tool": "get_user",
            "args": {"id": "3"},
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps({
                            "id": 3,
                            "name": "Clementine Bauch",
                            "address": {"geo": {"lat": "-68.6102", "lng": "-47.0653"}},
                        }),
                    }
                ]
            },
            "parsed_data": {
                "id": 3,
                "name": "Clementine Bauch",
                "address": {"geo": {"lat": "-68.6102", "lng": "-47.0653"}},
            },
        },
        {
            "tool": "get_weather",
            "args": {"latitude": "-68.6102", "longitude": "-47.0653"},
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps({
                            "current_weather": {
                                "temperature": -5.2,
                                "weathercode": 71,
                            }
                        }),
                    }
                ]
            },
        },
    ]
