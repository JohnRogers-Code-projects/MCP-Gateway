"""
MCP Protocol Models

Pydantic schemas for JSON-RPC 2.0 messages as used by the Model Context Protocol.
These mirror the message types ContextForge handles in its gateway.

Reference: https://modelcontextprotocol.io/specification
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal, TypedDict

from pydantic import BaseModel, Field

from .config import MCP_PROTOCOL_VERSION, SERVER_NAME, SERVER_VERSION
from .errors import ContractViolation, TransportFailure



# -----------------------------------------------------------------------------
# TypedDict Definitions for Structured Data
# -----------------------------------------------------------------------------


class TextContentDict(TypedDict):
    """Dictionary representation of text content."""

    type: Literal["text"]
    text: str


class ImageContentDict(TypedDict):
    """Dictionary representation of image content."""

    type: Literal["image"]
    data: str
    mimeType: str


ContentBlockDict = TextContentDict | ImageContentDict


class ToolCallResultDict(TypedDict):
    """Dictionary representation of tool call result."""

    content: list[ContentBlockDict]
    isError: bool


class ScenarioStepResultDict(TypedDict, total=False):
    """Dictionary representation of a scenario step result."""

    tool: str
    args: dict[str, Any]
    result: ToolCallResultDict
    parsed_data: dict[str, Any]


class ToolDict(TypedDict):
    """Dictionary representation of an MCP tool."""

    name: str
    description: str
    inputSchema: dict[str, Any]

# -----------------------------------------------------------------------------
# JSON-RPC 2.0 Base Types
# -----------------------------------------------------------------------------


class JsonRpcRequest(BaseModel):
    """
    JSON-RPC 2.0 request object.

    MCP uses JSON-RPC as its wire protocol. Every tool invocation,
    resource fetch, and prompt request is wrapped in this format.
    """

    jsonrpc: Literal["2.0"] = "2.0"
    id: int | str
    method: str
    params: dict[str, Any] | None = None


class JsonRpcResponse(BaseModel):
    """JSON-RPC 2.0 success response."""

    jsonrpc: Literal["2.0"] = "2.0"
    id: int | str
    result: Any


class JsonRpcErrorData(BaseModel):
    """Structured error information."""

    code: int
    message: str
    data: Any | None = None


class JsonRpcErrorResponse(BaseModel):
    """JSON-RPC 2.0 error response."""

    jsonrpc: Literal["2.0"] = "2.0"
    id: int | str | None
    error: JsonRpcErrorData


# Standard JSON-RPC error codes
class ErrorCode(int, Enum):
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603


# -----------------------------------------------------------------------------
# MCP Tool Types
# -----------------------------------------------------------------------------


class ToolInputSchema(BaseModel):
    """
    JSON Schema describing a tool's input parameters.

    This is how MCP tools declare what arguments they accept.
    LLM agents use this schema to construct valid tool calls.
    """

    type: Literal["object"] = "object"
    properties: dict[str, dict[str, Any]] = Field(default_factory=dict)
    required: list[str] = Field(default_factory=list)


class Tool(BaseModel):
    """
    MCP Tool definition.

    Tools are the primary way MCP servers expose functionality.
    Each tool has a name, description (for LLM understanding),
    and a schema defining its parameters.
    """

    name: str
    description: str
    inputSchema: ToolInputSchema  # noqa: N815 (MCP spec uses camelCase)


class ToolCallParams(BaseModel):
    """Parameters for tools/call method."""

    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolCallResult(BaseModel):
    """Result of a tool invocation."""

    content: list[ContentBlock]
    isError: bool = False  # noqa: N815


# -----------------------------------------------------------------------------
# Content Types
# -----------------------------------------------------------------------------


class TextContent(BaseModel):
    """Text content block."""

    type: Literal["text"] = "text"
    text: str


class ImageContent(BaseModel):
    """Image content block (base64 encoded)."""

    type: Literal["image"] = "image"
    data: str
    mimeType: str  # noqa: N815


ContentBlock = TextContent | ImageContent


# -----------------------------------------------------------------------------
# MCP Method Responses
# -----------------------------------------------------------------------------


class ListToolsResult(BaseModel):
    """Response to tools/list method."""

    tools: list[Tool]


class InitializeResult(BaseModel):
    """Response to initialize method."""

    protocolVersion: str = MCP_PROTOCOL_VERSION  # noqa: N815
    serverInfo: dict[str, str] = Field(  # noqa: N815
        default_factory=lambda: {"name": SERVER_NAME, "version": SERVER_VERSION}
    )
    capabilities: dict[str, Any] = Field(default_factory=lambda: {"tools": {}})


# -----------------------------------------------------------------------------
# Helper Functions
# -----------------------------------------------------------------------------


def make_error_response(
    request_id: int | str | None,
    code: ErrorCode,
    message: str,
    data: Any | None = None,
) -> JsonRpcErrorResponse:
    """Construct a JSON-RPC error response."""
    return JsonRpcErrorResponse(
        id=request_id,
        error=JsonRpcErrorData(code=code.value, message=message, data=data),
    )


def make_success_response(request_id: int | str, result: Any) -> JsonRpcResponse:
    """Construct a JSON-RPC success response."""
    return JsonRpcResponse(id=request_id, result=result)


# -----------------------------------------------------------------------------
# Canonical Execution Context
# -----------------------------------------------------------------------------


class ContextError(ContractViolation):
    """Raised when context invariants are violated."""

    pass


class ToolValidationError(ContractViolation):
    """
    Raised when tool invocation fails validation.

    This is a LOUD failure. Invalid tool calls should not silently degrade.
    Every validation error contains:
    - tool_name: Which tool was being invoked
    - errors: List of specific validation failures

    There is no "partial success" mode. Either all required parameters
    are present and valid, or invocation fails completely.
    """

    def __init__(self, tool_name: str, errors: list[str]) -> None:
        self.tool_name = tool_name
        self.errors = errors
        super().__init__(f"Tool '{tool_name}' validation failed: {'; '.join(errors)}")


class ToolTimeoutError(TransportFailure):
    """
    Raised when tool execution exceeds allowed time.

    DELIBERATE FAILURE MODE: Timeouts are handled explicitly, not in a
    generic catch-all. This makes the failure mode visible and allows
    orchestration to decide how to respond.

    Contains:
    - tool_name: Which tool timed out
    - timeout_seconds: How long we waited before giving up
    """

    def __init__(self, tool_name: str, timeout_seconds: float) -> None:
        self.tool_name = tool_name
        self.timeout_seconds = timeout_seconds
        super().__init__(
            f"Tool '{tool_name}' timed out after {timeout_seconds}s. "
            "The external service did not respond in time."
        )


class ExecutionContext:
    """
    Canonical context object — the single source of truth for request state.

    This class is an ACTIVE PARTICIPANT, not a passive data container.
    It enforces invariants, constrains mutation, and fails loudly on misuse.

    WHAT THIS OWNS:
    - Request identity (request_id, method)
    - Tool invocation state (tool_name, arguments)
    - Accumulated results
    - Lifecycle state (sealed or not)

    WHAT THIS REFUSES:
    - Ad-hoc construction (use from_request only)
    - Mutation after sealing
    - Results without a tool call
    - Empty or invalid request identifiers

    INVARIANTS (enforced in code):
    1. request_id must be non-empty (int or non-blank string)
    2. method must be non-empty string
    3. results cannot exist without tool_name being set first
    4. sealed context cannot be mutated
    """

    __slots__ = (
        "_request_id",
        "_method",
        "_tool_name",
        "_arguments",
        "_results",
        "_created_at",
        "_sealed",
    )

    def __init__(
        self,
        request_id: int | str,
        method: str,
        *,
        _trust_caller: bool = False,
    ) -> None:
        """
        Private constructor. Use from_request() instead.

        The _trust_caller flag exists only for internal with_* methods
        that have already validated the source context.
        """
        if not _trust_caller:
            raise ContextError(
                "ExecutionContext must be created via from_request(). "
                "Direct construction is not allowed."
            )

        self._request_id = request_id
        self._method = method
        self._tool_name: str | None = None
        self._arguments: dict[str, Any] = {}
        self._results: tuple[ToolCallResult, ...] = ()
        self._created_at = datetime.now(timezone.utc)
        self._sealed = False

    # -------------------------------------------------------------------------
    # Single Creation Path
    # -------------------------------------------------------------------------

    @classmethod
    def from_request(cls, request: JsonRpcRequest) -> "ExecutionContext":
        """
        THE ONLY valid way to create an ExecutionContext.

        Validates request and fails loudly if invalid.
        """
        # Invariant 1: request_id must be non-empty
        if request.id is None:
            raise ContextError("Cannot create context: request.id is None")
        if isinstance(request.id, str) and not request.id.strip():
            raise ContextError("Cannot create context: request.id is empty string")

        # Invariant 2: method must be non-empty
        if not request.method or not request.method.strip():
            raise ContextError("Cannot create context: request.method is empty")

        ctx = cls(request.id, request.method, _trust_caller=True)
        return ctx

    # -------------------------------------------------------------------------
    # Read-Only Properties (no setters)
    # -------------------------------------------------------------------------

    @property
    def request_id(self) -> int | str:
        return self._request_id

    @property
    def method(self) -> str:
        return self._method

    @property
    def tool_name(self) -> str | None:
        return self._tool_name

    @property
    def arguments(self) -> dict[str, Any]:
        # Return copy to prevent external mutation
        return dict(self._arguments)

    @property
    def results(self) -> tuple[ToolCallResult, ...]:
        return self._results

    @property
    def created_at(self) -> datetime:
        return self._created_at

    @property
    def is_sealed(self) -> bool:
        return self._sealed

    # -------------------------------------------------------------------------
    # Constrained Mutation Methods
    # -------------------------------------------------------------------------

    def with_tool_call(self, name: str, arguments: dict[str, Any]) -> "ExecutionContext":
        """
        Return new context with tool call bound.

        WHY THIS MUTATION IS ALLOWED:
        When routing to tools/call, we learn which tool is being invoked.
        This is the natural point to bind tool identity to context.

        PRECONDITIONS:
        - Context must not be sealed
        - name must be non-empty
        - tool_name must not already be set (no rebinding)
        """
        self._check_not_sealed("with_tool_call")

        if not name or not name.strip():
            raise ContextError("Cannot bind tool call: name is empty")

        if self._tool_name is not None:
            raise ContextError(
                f"Cannot rebind tool call: already bound to '{self._tool_name}'. "
                "Tool identity is immutable once set."
            )

        # Create new context (immutable pattern)
        # Note: _sealed is intentionally not copied. The check above ensures
        # we never reach here from a sealed context. New contexts start unsealed
        # so they can be further mutated until explicitly sealed.
        new_ctx = ExecutionContext(
            self._request_id, self._method, _trust_caller=True
        )
        new_ctx._tool_name = name.strip()
        new_ctx._arguments = dict(arguments)  # defensive copy
        new_ctx._results = self._results
        new_ctx._created_at = self._created_at
        return new_ctx

    def with_result(self, result: ToolCallResult) -> "ExecutionContext":
        """
        Return new context with result appended.

        WHY THIS MUTATION IS ALLOWED:
        After tool execution, we accumulate results. This is the natural
        point to record what the tool returned.

        PRECONDITIONS:
        - Context must not be sealed
        - tool_name must be set (Invariant 3: no results without tool)
        - result must not be None
        """
        self._check_not_sealed("with_result")

        # Invariant 3: Cannot have results without a tool call
        if self._tool_name is None:
            raise ContextError(
                "Cannot add result: no tool_name set. "
                "Results require a tool call to be bound first."
            )

        if result is None:
            raise ContextError("Cannot add result: result is None")

        # Create new context (immutable pattern)
        # Note: _sealed intentionally not copied (see with_tool_call comment)
        new_ctx = ExecutionContext(
            self._request_id, self._method, _trust_caller=True
        )
        new_ctx._tool_name = self._tool_name
        new_ctx._arguments = dict(self._arguments)
        new_ctx._results = self._results + (result,)
        new_ctx._created_at = self._created_at
        return new_ctx

    # -------------------------------------------------------------------------
    # Lifecycle Management
    # -------------------------------------------------------------------------

    def seal(self) -> "ExecutionContext":
        """
        Mark context as sealed. No further mutations allowed.

        Call this when context leaves the adapter and enters external code.
        Returns self for chaining.
        """
        self._sealed = True
        return self

    def _check_not_sealed(self, operation: str) -> None:
        """Enforce Invariant 4: sealed context cannot be mutated."""
        if self._sealed:
            raise ContextError(
                f"Cannot perform '{operation}': context is sealed. "
                "Sealed contexts are immutable."
            )

    # -------------------------------------------------------------------------
    # Context Boundary (THE point where accumulated data is destroyed)
    # -------------------------------------------------------------------------

    def discard_results(self) -> "ExecutionContext":
        """
        DESTROY all accumulated results. Returns context with empty results.

        THIS IS THE CONTEXT BOUNDARY.

        WHY THIS LOSS IS NECESSARY:
        Accumulated tool results contain unbounded data from external sources.
        Downstream code (other tools, external systems) must not see this data.
        If they need specific information, it must be extracted BEFORE this
        boundary and passed explicitly. There is no way to recover discarded
        results. This is intentional.

        This method exists to make context reduction:
        - Visible (you see it in the orchestration flow)
        - Mandatory (there is no "keep some" option)
        - Irreversible (data is destroyed, not hidden)
        """
        self._check_not_sealed("discard_results")

        new_ctx = ExecutionContext(
            self._request_id, self._method, _trust_caller=True
        )
        new_ctx._tool_name = self._tool_name
        new_ctx._arguments = dict(self._arguments)
        new_ctx._results = ()  # DESTROYED. No configuration. No recovery.
        new_ctx._created_at = self._created_at
        return new_ctx

    # -------------------------------------------------------------------------
    # Representation
    # -------------------------------------------------------------------------

    def __repr__(self) -> str:
        sealed_marker = " SEALED" if self._sealed else ""
        tool_info = f" tool={self._tool_name}" if self._tool_name else ""
        result_info = f" results={len(self._results)}" if self._results else ""
        return (
            f"<ExecutionContext id={self._request_id} "
            f"method={self._method}{tool_info}{result_info}{sealed_marker}>"
        )
