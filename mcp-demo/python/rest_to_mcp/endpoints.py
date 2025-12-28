"""
Endpoint definitions for REST-to-MCP adapter.

Separates endpoint data from adapter logic for better maintainability.
Each API's endpoints are defined as a list of RestEndpoint objects.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from .config import JSONPLACEHOLDER_BASE_URL, OPEN_METEO_BASE_URL


class HttpMethod(str, Enum):
    """HTTP methods supported by the adapter."""

    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    PATCH = "PATCH"


@dataclass
class RestEndpoint:
    """
    Definition of a REST endpoint to expose as an MCP tool.

    This maps REST semantics to MCP tool semantics:
    - path: URL path (may contain {param} placeholders)
    - method: HTTP method
    - description: Human-readable description for LLM agents
    - path_params: Parameters that go in the URL path
    - query_params: Parameters that go in the query string
    - body_params: Parameters that go in the request body
    - base_url: Optional API-specific base URL (enables multi-API support)
    """

    name: str
    path: str
    method: HttpMethod
    description: str
    path_params: list[str] | None = None
    query_params: list[str] | None = None
    body_params: list[str] | None = None
    base_url: str | None = None

    def validate_arguments(self, arguments: dict[str, Any]) -> list[str]:
        """
        Validate arguments against this endpoint's schema.

        Returns list of validation errors. Empty list = valid.

        CONSTRAINED BY DESIGN:
        - Tools receive ONLY declared parameters
        - Unknown arguments are REJECTED (no silent passthrough)
        - Path params must be non-empty strings
        - Body params required for mutating methods

        This validation is intentionally strict. Tools should not receive
        data they did not ask for. Flexibility here is a liability.
        """
        errors: list[str] = []

        # Collect ALL known parameters for this endpoint
        known_params: set[str] = set()
        known_params.update(self.path_params or [])
        known_params.update(self.query_params or [])
        known_params.update(self.body_params or [])

        # REJECT unknown arguments - tools receive ONLY what they declare
        for arg in arguments:
            if arg not in known_params:
                errors.append(
                    f"Unknown argument '{arg}' - tool '{self.name}' does not accept this parameter"
                )

        # Path params are ALWAYS required - you cannot have a URL with holes
        for param in self.path_params or []:
            if param not in arguments:
                errors.append(f"Missing required path parameter: '{param}'")
            else:
                value = arguments[param]
                # Path params must be non-empty strings (after conversion)
                str_value = str(value).strip()
                if not str_value:
                    errors.append(f"Path parameter '{param}' cannot be empty")

        # Body params are required for mutating methods
        if self.method in (HttpMethod.POST, HttpMethod.PUT, HttpMethod.PATCH):
            for param in self.body_params or []:
                if param not in arguments:
                    errors.append(f"Missing required body parameter: '{param}'")

        return errors

    def to_mcp_tool(self) -> "Tool":
        """Convert this REST endpoint definition to an MCP Tool."""
        from .models import Tool, ToolInputSchema

        properties: dict[str, dict[str, Any]] = {}
        required: list[str] = []

        # Path params are always required
        for param in self.path_params or []:
            properties[param] = {
                "type": "string",
                "description": f"Path parameter: {param}",
            }
            required.append(param)

        # Query params are optional by default
        for param in self.query_params or []:
            properties[param] = {
                "type": "string",
                "description": f"Query parameter: {param}",
            }

        # Body params - required for POST/PUT/PATCH
        for param in self.body_params or []:
            properties[param] = {
                "type": "string",
                "description": f"Body field: {param}",
            }
            if self.method in (HttpMethod.POST, HttpMethod.PUT, HttpMethod.PATCH):
                required.append(param)

        return Tool(
            name=self.name,
            description=self.description,
            inputSchema=ToolInputSchema(
                properties=properties,
                required=required,
            ),
        )


# Avoid circular import
from .models import Tool  # noqa: E402


# -----------------------------------------------------------------------------
# JSONPlaceholder API Endpoints
# https://jsonplaceholder.typicode.com
# -----------------------------------------------------------------------------

JSONPLACEHOLDER_ENDPOINTS: list[RestEndpoint] = [
    RestEndpoint(
        name="get_posts",
        path="/posts",
        method=HttpMethod.GET,
        description="Get all posts. Optionally filter by userId.",
        query_params=["userId"],
    ),
    RestEndpoint(
        name="get_post",
        path="/posts/{id}",
        method=HttpMethod.GET,
        description="Get a specific post by ID.",
        path_params=["id"],
    ),
    RestEndpoint(
        name="create_post",
        path="/posts",
        method=HttpMethod.POST,
        description="Create a new post with title, body, and userId.",
        body_params=["title", "body", "userId"],
    ),
    RestEndpoint(
        name="update_post",
        path="/posts/{id}",
        method=HttpMethod.PUT,
        description="Update an existing post.",
        path_params=["id"],
        body_params=["title", "body", "userId"],
    ),
    RestEndpoint(
        name="delete_post",
        path="/posts/{id}",
        method=HttpMethod.DELETE,
        description="Delete a post by ID.",
        path_params=["id"],
    ),
    RestEndpoint(
        name="get_comments",
        path="/posts/{postId}/comments",
        method=HttpMethod.GET,
        description="Get all comments for a specific post.",
        path_params=["postId"],
    ),
    RestEndpoint(
        name="get_users",
        path="/users",
        method=HttpMethod.GET,
        description="Get all users.",
    ),
    RestEndpoint(
        name="get_user",
        path="/users/{id}",
        method=HttpMethod.GET,
        description="Get a specific user by ID.",
        path_params=["id"],
    ),
]


# -----------------------------------------------------------------------------
# Open-Meteo Weather API Endpoints
# https://open-meteo.com/en/docs
# -----------------------------------------------------------------------------

OPEN_METEO_ENDPOINTS: list[RestEndpoint] = [
    RestEndpoint(
        name="get_weather",
        path="/v1/forecast",
        method=HttpMethod.GET,
        description="Get current weather for coordinates. Returns temperature, wind speed, and conditions.",
        query_params=["latitude", "longitude", "current_weather"],
        base_url=OPEN_METEO_BASE_URL,
    ),
    RestEndpoint(
        name="get_forecast",
        path="/v1/forecast",
        method=HttpMethod.GET,
        description="Get 7-day weather forecast for coordinates.",
        query_params=["latitude", "longitude", "daily", "timezone"],
        base_url=OPEN_METEO_BASE_URL,
    ),
]


# -----------------------------------------------------------------------------
# Combined Endpoints
# -----------------------------------------------------------------------------

DEFAULT_ENDPOINTS: list[RestEndpoint] = JSONPLACEHOLDER_ENDPOINTS + OPEN_METEO_ENDPOINTS
