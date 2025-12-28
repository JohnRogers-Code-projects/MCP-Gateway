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
from typing import Any

import httpx

from .config import (
    HTTP_ERROR_THRESHOLD,
    HTTP_TIMEOUT_SECONDS,
    JSONPLACEHOLDER_BASE_URL,
)
from .endpoints import (
    DEFAULT_ENDPOINTS,
    JSONPLACEHOLDER_ENDPOINTS,
    HttpMethod,
    RestEndpoint,
)
from .models import (
    ContentBlock,
    ContextError,
    ErrorCode,
    ExecutionContext,
    InitializeResult,
    JsonRpcErrorResponse,
    JsonRpcRequest,
    JsonRpcResponse,
    ListToolsResult,
    TextContent,
    Tool,
    ToolCallParams,
    ToolCallResult,
    ToolValidationError,
    make_error_response,
    make_success_response,
)

# Re-export for backward compatibility
__all__ = [
    "HttpMethod",
    "RestEndpoint",
    "RestToMcpAdapter",
    "create_jsonplaceholder_adapter",
    "create_multi_api_adapter",
    "JSONPLACEHOLDER_ENDPOINTS",
    "OPEN_METEO_ENDPOINTS",
    "OPEN_METEO_BASE",
    "DEFAULT_ENDPOINTS",
]

# Backward compatibility aliases
from .endpoints import OPEN_METEO_ENDPOINTS
from .config import OPEN_METEO_BASE_URL as OPEN_METEO_BASE


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
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=HTTP_TIMEOUT_SECONDS,
            )
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

        CONSTRAINED INVOCATION:
        - Tools receive ONLY declared parameters (unknown args rejected)
        - Destructive operations have additional guards
        - Validation happens BEFORE HTTP request is built
        - Missing/invalid parameters raise ToolValidationError immediately
        - There is no silent degradation, no retry, no recovery

        Flow:
        1. Look up endpoint (fail if unknown)
        2. VALIDATE arguments (fail loudly if invalid)
        3. GUARD destructive operations (deliberate misuse check)
        4. Build HTTP request (params guaranteed valid after checks)
        5. Make request
        6. Transform response
        """
        if name not in self.endpoints:
            return ToolCallResult(
                content=[TextContent(text=f"Unknown tool: {name}")],
                isError=True,
            )

        endpoint = self.endpoints[name]

        # VALIDATION GATE: Fail loudly if arguments are invalid
        validation_errors = endpoint.validate_arguments(arguments)
        if validation_errors:
            raise ToolValidationError(name, validation_errors)

        # DELIBERATE MISUSE CHECK: Guard destructive operations
        # This demonstrates intentional constraint - certain operations
        # have additional checks that cannot be bypassed
        self._guard_destructive_operation(name, arguments)

        url = self._build_url(endpoint, arguments)
        query_params = self._build_query_params(endpoint, arguments)
        body = self._build_body(endpoint, arguments)

        try:
            response = await self.client.request(
                method=endpoint.method.value,
                url=url,
                params=query_params or None,
                json=body,
            )

            content = self._response_to_content(response)
            return ToolCallResult(
                content=content,
                isError=response.status_code >= HTTP_ERROR_THRESHOLD,
            )

        except httpx.HTTPError as e:
            return ToolCallResult(
                content=[TextContent(text=f"HTTP error: {e!s}")],
                isError=True,
            )

    def _build_url(self, endpoint: RestEndpoint, arguments: dict[str, Any]) -> str:
        """Build URL with path parameters substituted."""
        path = endpoint.path
        for param in endpoint.path_params or []:
            if param in arguments:
                path = path.replace(f"{{{param}}}", str(arguments[param]))

        # Use endpoint-specific base_url if provided (multi-API support)
        if endpoint.base_url:
            return endpoint.base_url.rstrip("/") + path
        return path  # Relative to adapter's base_url

    def _build_query_params(
        self, endpoint: RestEndpoint, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """Build query parameters from arguments."""
        query_params = {}
        for param in endpoint.query_params or []:
            if param in arguments:
                query_params[param] = arguments[param]
        return query_params

    def _build_body(
        self, endpoint: RestEndpoint, arguments: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Build request body from arguments."""
        if not endpoint.body_params:
            return None
        return {k: arguments[k] for k in endpoint.body_params if k in arguments}

    def _response_to_content(self, response: httpx.Response) -> list[ContentBlock]:
        """Convert HTTP response to MCP content blocks."""
        try:
            data = response.json()
            text = json.dumps(data, indent=2)
        except json.JSONDecodeError:
            text = response.text

        return [TextContent(text=text)]

    def _guard_destructive_operation(
        self, name: str, arguments: dict[str, Any]
    ) -> None:
        """
        Guard against misuse of destructive operations.

        DELIBERATE CONSTRAINT: Certain operations have additional checks
        that go beyond schema validation. This is intentional.

        WHY THIS EXISTS:
        - Demonstrates that tools can be constrained beyond their schema
        - Makes it obvious that destructive operations are guarded
        - Fails LOUDLY with clear message explaining the constraint

        This method does NOT:
        - Retry on failure
        - Recover silently
        - Provide workarounds

        Raises:
            ToolValidationError: If the operation would be destructive misuse
        """
        # Guard delete_post: ID must be a positive integer
        if name == "delete_post":
            id_value = arguments.get("id", "")
            try:
                id_int = int(id_value)
                if id_int <= 0:
                    raise ToolValidationError(
                        name,
                        [
                            f"Destructive operation rejected: id={id_value} is not a valid post ID. "
                            "Post IDs must be positive integers. This constraint is deliberate."
                        ],
                    )
            except (ValueError, TypeError):
                raise ToolValidationError(
                    name,
                    [
                        f"Destructive operation rejected: id={id_value!r} is not a valid integer. "
                        "delete_post requires a numeric post ID. This constraint is deliberate."
                    ],
                )

        # Guard update_post: ID must be a positive integer
        if name == "update_post":
            id_value = arguments.get("id", "")
            try:
                id_int = int(id_value)
                if id_int <= 0:
                    raise ToolValidationError(
                        name,
                        [
                            f"Destructive operation rejected: id={id_value} is not a valid post ID. "
                            "Post IDs must be positive integers. This constraint is deliberate."
                        ],
                    )
            except (ValueError, TypeError):
                raise ToolValidationError(
                    name,
                    [
                        f"Destructive operation rejected: id={id_value!r} is not a valid integer. "
                        "update_post requires a numeric post ID. This constraint is deliberate."
                    ],
                )

    async def handle_request(
        self, request: JsonRpcRequest
    ) -> tuple[JsonRpcResponse | JsonRpcErrorResponse, ExecutionContext]:
        """
        THE GOLDEN PATH: Single entry point for all MCP operations.

        All requests flow through here. There are no alternative paths.

        Flow:
            handle_request()
              → create ExecutionContext
              → route by method
              → seal context
              → return (response, sealed_context)

        Supported methods:
            initialize  → server capabilities
            tools/list  → available tools
            tools/call  → execute tool (binds tool_name, records result)

        Context is ALWAYS sealed before return. Callers receive immutable context.
        """
        # Create canonical context at entry point (single creation path)
        context = ExecutionContext.from_request(request)

        match request.method:
            case "initialize":
                response = make_success_response(
                    request.id,
                    InitializeResult().model_dump(),
                )
                return response, context.seal()

            case "tools/list":
                list_result = ListToolsResult(tools=self.list_tools())
                response = make_success_response(request.id, list_result.model_dump())
                return response, context.seal()

            case "tools/call":
                response, context = await self._handle_tools_call(request, context)
                return response, context.seal()

            case _:
                response = make_error_response(
                    request.id,
                    ErrorCode.METHOD_NOT_FOUND,
                    f"Unknown method: {request.method}",
                )
                return response, context.seal()

    async def _handle_tools_call(
        self, request: JsonRpcRequest, context: ExecutionContext
    ) -> tuple[JsonRpcResponse | JsonRpcErrorResponse, ExecutionContext]:
        """Handle tools/call method with context tracking."""
        if request.params is None:
            response = make_error_response(
                request.id,
                ErrorCode.INVALID_PARAMS,
                "Missing params for tools/call",
            )
            return response, context

        try:
            params = ToolCallParams(**request.params)
        except Exception as e:
            response = make_error_response(
                request.id,
                ErrorCode.INVALID_PARAMS,
                f"Invalid params: {e}",
            )
            return response, context

        # Update context with tool call information (immutable)
        context = context.with_tool_call(params.name, params.arguments)

        # Execute the tool (may raise ToolValidationError)
        try:
            call_result = await self.call_tool(params.name, params.arguments)
        except ToolValidationError as e:
            # LOUD FAILURE: Validation errors are returned as proper errors
            # not silently swallowed or partially executed
            response = make_error_response(
                request.id,
                ErrorCode.INVALID_PARAMS,
                str(e),
                data={"tool": e.tool_name, "errors": e.errors},
            )
            return response, context

        # CONTEXT GROWTH: Result is appended to context here.
        # Each tool call adds to accumulated context size.
        # For multi-step orchestration, consider context reduction between steps.
        context = context.with_result(call_result)

        response = make_success_response(request.id, call_result.model_dump())
        return response, context


# -----------------------------------------------------------------------------
# Factory Functions
# -----------------------------------------------------------------------------


def create_jsonplaceholder_adapter() -> RestToMcpAdapter:
    """Create an adapter pre-configured for JSONPlaceholder API."""
    return RestToMcpAdapter(
        base_url=JSONPLACEHOLDER_BASE_URL,
        endpoints=JSONPLACEHOLDER_ENDPOINTS,
    )


def create_multi_api_adapter() -> RestToMcpAdapter:
    """
    Create an adapter with multiple APIs registered.

    Demonstrates ContextForge's key value prop: bringing a client's
    vast portfolio of existing APIs into the AI agent ecosystem.
    """
    return RestToMcpAdapter(
        base_url=JSONPLACEHOLDER_BASE_URL,  # Default for relative paths
        endpoints=DEFAULT_ENDPOINTS,
    )
