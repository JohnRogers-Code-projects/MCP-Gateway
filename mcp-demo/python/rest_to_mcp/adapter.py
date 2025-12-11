"""
REST-to-MCP Adapter

Translates REST API endpoints into MCP-compliant tools. This is the core
functionality that mirrors ContextForge's protocol translation capability.

The adapter:
1. Defines REST endpoints as MCP tools with proper schemas
2. Handles MCP tool/call requests by making HTTP calls to the REST API
3. Transforms REST responses into MCP content blocks
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from typing import Any

import httpx

from .models import (
    ContentBlock,
    ErrorCode,
    InitializeResult,
    JsonRpcErrorResponse,
    JsonRpcRequest,
    JsonRpcResponse,
    ListToolsResult,
    TextContent,
    Tool,
    ToolCallParams,
    ToolCallResult,
    ToolInputSchema,
    make_error_response,
    make_success_response,
)


class HttpMethod(str, Enum):
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
    """

    name: str
    path: str
    method: HttpMethod
    description: str
    path_params: list[str] | None = None
    query_params: list[str] | None = None
    body_params: list[str] | None = None

    def to_mcp_tool(self) -> Tool:
        """Convert this REST endpoint definition to an MCP Tool."""
        properties: dict[str, dict[str, Any]] = {}
        required: list[str] = []

        # Path params are always required
        for param in self.path_params or []:
            properties[param] = {"type": "string", "description": f"Path parameter: {param}"}
            required.append(param)

        # Query params are optional by default
        for param in self.query_params or []:
            properties[param] = {"type": "string", "description": f"Query parameter: {param}"}

        # Body params - required for POST/PUT/PATCH
        for param in self.body_params or []:
            properties[param] = {"type": "string", "description": f"Body field: {param}"}
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


class RestToMcpAdapter:
    """
    Adapts a REST API to the MCP protocol.

    This class is the heart of the protocol translation. It:
    1. Maintains a registry of REST endpoints exposed as MCP tools
    2. Handles MCP JSON-RPC requests and routes them appropriately
    3. Makes HTTP calls to the underlying REST API
    4. Transforms responses back to MCP format

    In ContextForge, this pattern is used to virtualize legacy APIs
    as MCP-compliant tool servers.
    """

    def __init__(self, base_url: str, endpoints: list[RestEndpoint] | None = None):
        self.base_url = base_url.rstrip("/")
        self.endpoints: dict[str, RestEndpoint] = {}
        self._client: httpx.AsyncClient | None = None

        for endpoint in endpoints or []:
            self.register_endpoint(endpoint)

    def register_endpoint(self, endpoint: RestEndpoint) -> None:
        """Register a REST endpoint as an MCP tool."""
        self.endpoints[endpoint.name] = endpoint

    @property
    def client(self) -> httpx.AsyncClient:
        """Lazy-initialize HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(base_url=self.base_url, timeout=30.0)
        return self._client

    async def close(self) -> None:
        """Clean up HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def list_tools(self) -> list[Tool]:
        """Return all registered tools in MCP format."""
        return [endpoint.to_mcp_tool() for endpoint in self.endpoints.values()]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> ToolCallResult:
        """
        Execute a tool by calling the underlying REST endpoint.

        This is where the actual translation happens:
        1. Look up the endpoint definition
        2. Build the HTTP request (path, query, body)
        3. Make the request
        4. Transform the response to MCP content blocks
        """
        if name not in self.endpoints:
            return ToolCallResult(
                content=[TextContent(text=f"Unknown tool: {name}")],
                isError=True,
            )

        endpoint = self.endpoints[name]

        # Build URL with path parameters
        path = endpoint.path
        for param in endpoint.path_params or []:
            if param in arguments:
                path = path.replace(f"{{{param}}}", str(arguments[param]))

        # Build query parameters
        query_params = {}
        for param in endpoint.query_params or []:
            if param in arguments:
                query_params[param] = arguments[param]

        # Build request body
        body = None
        if endpoint.body_params:
            body = {k: arguments[k] for k in endpoint.body_params if k in arguments}

        try:
            response = await self.client.request(
                method=endpoint.method.value,
                url=path,
                params=query_params or None,
                json=body,
            )

            # Transform response to MCP content
            content = self._response_to_content(response)
            return ToolCallResult(
                content=content,
                isError=response.status_code >= 400,
            )

        except httpx.HTTPError as e:
            return ToolCallResult(
                content=[TextContent(text=f"HTTP error: {e!s}")],
                isError=True,
            )

    def _response_to_content(self, response: httpx.Response) -> list[ContentBlock]:
        """Convert HTTP response to MCP content blocks."""
        try:
            data = response.json()
            # Pretty-print JSON for readability
            text = json.dumps(data, indent=2)
        except json.JSONDecodeError:
            text = response.text

        return [TextContent(text=text)]

    async def handle_request(
        self, request: JsonRpcRequest
    ) -> JsonRpcResponse | JsonRpcErrorResponse:
        """
        Main entry point for handling MCP JSON-RPC requests.

        Routes requests to the appropriate handler based on method:
        - initialize: Return server capabilities
        - tools/list: Return available tools
        - tools/call: Execute a tool
        """
        match request.method:
            case "initialize":
                return make_success_response(
                    request.id,
                    InitializeResult().model_dump(),
                )

            case "tools/list":
                list_result = ListToolsResult(tools=self.list_tools())
                return make_success_response(request.id, list_result.model_dump())

            case "tools/call":
                if request.params is None:
                    return make_error_response(
                        request.id,
                        ErrorCode.INVALID_PARAMS,
                        "Missing params for tools/call",
                    )

                try:
                    params = ToolCallParams(**request.params)
                except Exception as e:
                    return make_error_response(
                        request.id,
                        ErrorCode.INVALID_PARAMS,
                        f"Invalid params: {e}",
                    )

                call_result = await self.call_tool(params.name, params.arguments)
                return make_success_response(request.id, call_result.model_dump())

            case _:
                return make_error_response(
                    request.id,
                    ErrorCode.METHOD_NOT_FOUND,
                    f"Unknown method: {request.method}",
                )


# -----------------------------------------------------------------------------
# Pre-configured adapter for JSONPlaceholder API
# -----------------------------------------------------------------------------

JSONPLACEHOLDER_ENDPOINTS = [
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


def create_jsonplaceholder_adapter() -> RestToMcpAdapter:
    """Create an adapter pre-configured for JSONPlaceholder API."""
    return RestToMcpAdapter(
        base_url="https://jsonplaceholder.typicode.com",
        endpoints=JSONPLACEHOLDER_ENDPOINTS,
    )
