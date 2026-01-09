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
from pydantic import ValidationError as PydanticValidationError

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
from .errors import ContractViolation, GatewayFailure, GatewayInternalFailure, TransportFailure
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
    ToolTimeoutError,
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

    def _list_tools(self) -> list[Tool]:
        """Return all registered tools in MCP format. Internal use only."""
        return [endpoint.to_mcp_tool() for endpoint in self.endpoints.values()]

    async def _call_tool(self, name: str, arguments: dict[str, Any]) -> ToolCallResult:
        """
        Execute a tool. This is a DUMB executor. Internal use only.

        THIS METHOD DOES NOT:
        - Validate arguments (orchestration's job)
        - Guard against misuse (orchestration's job)
        - Make policy decisions (orchestration's job)
        - Infer intent (orchestration's job)

        It receives a tool name and arguments, makes the HTTP call,
        and returns the result. That's all.

        Orchestration (_handle_tools_call) decides WHAT to call.
        This method only knows HOW to call.
        """
        # AMBIGUITY HARD-FAIL: Unknown tool is a contract violation.
        # Per FAILURE_MODEL.md: "Unknown tool name → Fail with INVALID_PARAMS"
        # This should never happen if orchestration validates correctly.
        if name not in self.endpoints:
            raise ContractViolation(f"Unknown tool: {name}")

        endpoint = self.endpoints[name]
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

        # ---------------------------------------------------------------------
        # DELIBERATE FAILURE MODES: Handle specific failures explicitly
        # These are NOT hidden in a generic catch-all. Each failure mode
        # is visible and can be handled differently by orchestration.
        # ---------------------------------------------------------------------

        except httpx.TimeoutException:
            # TIMEOUT: External service did not respond in time
            # Raise explicit exception so orchestration can decide response
            raise ToolTimeoutError(name, HTTP_TIMEOUT_SECONDS)

        except httpx.HTTPError as e:
            # TransportFailure: Connection refused, DNS failure, TLS errors, etc.
            # Per docs/FAILURE_MODEL.md: Returns ToolCallResult with isError=true
            # TODO: Consider whether this should raise TransportFailure instead
            # of returning a result. Current behavior is per documented MCP representation.
            return ToolCallResult(
                content=[TextContent(text=f"HTTP error: {e!s}")],
                isError=True,
            )

    def _build_url(self, endpoint: RestEndpoint, arguments: dict[str, Any]) -> str:
        """Build URL with path parameters substituted."""
        # EARLY AMBIGUITY CHECK: Detect missing params BEFORE any transformation
        # Path params are always required - cannot build URL with holes
        if endpoint.path_params:
            missing = [p for p in endpoint.path_params if p not in arguments]
            if missing:
                raise ContractViolation(
                    f"Cannot build URL: missing required path parameter(s): {missing}"
                )

        # Only substitute after confirming all params present
        path = endpoint.path
        for param in endpoint.path_params or []:
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

        # EARLY AMBIGUITY CHECK: Detect missing params BEFORE transformation
        # ❗ UNDECIDED — ambiguous behavior requires explicit architectural decision
        # TODO: Body param handling is ambiguous:
        # - For POST/PUT/PATCH: validate_arguments requires them, but this check
        #   is bypassed if call_tool is invoked directly
        # - For GET/DELETE: body params are optional per validate_arguments
        # - Current behavior: silently skip missing params (partial body)
        # - Alternative: fail on any missing body param
        # This silent classification should be replaced with explicit policy.
        missing = [k for k in endpoint.body_params if k not in arguments]
        if missing:
            raise ContractViolation(
                f"Cannot build request body: missing body parameter(s): {missing}"
            )

        return {k: arguments[k] for k in endpoint.body_params}

    def _response_to_content(self, response: httpx.Response) -> list[ContentBlock]:
        """Convert HTTP response to MCP content blocks."""
        # TODO: UNDECIDED per docs/FAILURE_MODEL.md (Issue #21)
        # - Should empty upstream responses be treated as errors?
        # - Should partial upstream responses (missing expected fields) hard-fail?
        # - How should non-JSON upstream responses be categorized?
        # Currently: non-JSON falls back to raw text, empty responses accepted.
        # This is ambiguity tolerance that requires an architectural decision.
        try:
            data = response.json()
            text = json.dumps(data, indent=2)
        except json.JSONDecodeError:
            # AMBIGUITY: Non-JSON response - treating as raw text
            # TODO: UNDECIDED - should this raise UpstreamFailure instead?
            text = response.text

        return [TextContent(text=text)]

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
        # ---------------------------------------------------------------------
        # GATEWAY BOUNDARY: No raw exception may escape this method.
        # All exceptions must be GatewayFailure instances.
        # ---------------------------------------------------------------------
        try:
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
                    list_result = ListToolsResult(tools=self._list_tools())
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

        except GatewayFailure:
            raise
        except Exception as e:
            raise GatewayInternalFailure(str(e), cause=e) from e

    async def _handle_tools_call(
        self, request: JsonRpcRequest, context: ExecutionContext
    ) -> tuple[JsonRpcResponse | JsonRpcErrorResponse, ExecutionContext]:
        """
        Handle tools/call method. ORCHESTRATION decides policy here.

        This is where intelligence lives:
        - Validate arguments against schema
        - Guard destructive operations
        - Decide whether to proceed

        The tool (call_tool) is dumb. It just executes what we tell it.
        """
        if request.params is None:
            response = make_error_response(
                request.id,
                ErrorCode.INVALID_PARAMS,
                "Missing params for tools/call",
            )
            return response, context

        try:
            params = ToolCallParams(**request.params)
        except PydanticValidationError as e:
            # ContractViolation: Request params do not match expected schema
            response = make_error_response(
                request.id,
                ErrorCode.INVALID_PARAMS,
                f"Invalid params: {e}",
            )
            return response, context

        # Update context with tool call information (immutable)
        context = context.with_tool_call(params.name, params.arguments)

        # ---------------------------------------------------------------------
        # ORCHESTRATION POLICY: Validate before invoking tool
        # ---------------------------------------------------------------------
        if params.name not in self.endpoints:
            response = make_error_response(
                request.id,
                ErrorCode.INVALID_PARAMS,
                f"Unknown tool: {params.name}",
            )
            return response, context

        endpoint = self.endpoints[params.name]
        validation_errors = endpoint.validate_arguments(params.arguments)
        if validation_errors:
            response = make_error_response(
                request.id,
                ErrorCode.INVALID_PARAMS,
                f"Tool '{params.name}' validation failed: {'; '.join(validation_errors)}",
                data={"tool": params.name, "errors": validation_errors},
            )
            return response, context

        # ---------------------------------------------------------------------
        # ORCHESTRATION POLICY: Guard destructive operations
        # ---------------------------------------------------------------------
        guard_error = self._check_destructive_operation(params.name, params.arguments)
        if guard_error:
            response = make_error_response(
                request.id,
                ErrorCode.INVALID_PARAMS,
                guard_error,
                data={"tool": params.name},
            )
            return response, context

        # ---------------------------------------------------------------------
        # Execute the tool (tool is dumb - just executes)
        # ---------------------------------------------------------------------
        try:
            call_result = await self._call_tool(params.name, params.arguments)
        except ToolTimeoutError as e:
            # DELIBERATE FAILURE: Timeout is handled explicitly
            # Context records the failure attempt (no result, but tool was called)
            response = make_error_response(
                request.id,
                ErrorCode.INTERNAL_ERROR,
                str(e),
                data={
                    "tool": e.tool_name,
                    "timeout_seconds": e.timeout_seconds,
                    "failure_mode": "timeout",
                },
            )
            return response, context

        # CONTEXT GROWTH: Result is appended to context here.
        context = context.with_result(call_result)

        response = make_success_response(request.id, call_result.model_dump())
        return response, context

    def _check_destructive_operation(
        self, name: str, arguments: dict[str, Any]
    ) -> str | None:
        """
        Check if a destructive operation should be blocked.

        Returns error message if blocked, None if allowed.

        This is ORCHESTRATION policy, not tool logic.
        The tool doesn't know it's being guarded.
        """
        if name in ("delete_post", "update_post"):
            id_value = arguments.get("id", "")
            try:
                id_int = int(id_value)
                if id_int <= 0:
                    return (
                        f"Destructive operation rejected: id={id_value} is not valid. "
                        "Post IDs must be positive integers."
                    )
            except (ValueError, TypeError):
                return (
                    f"Destructive operation rejected: id={id_value!r} is not a valid integer."
                )
        return None


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
