"""
Gateway Failure Types

Canonical failure taxonomy per docs/FAILURE_MODEL.md.
All failures in the gateway MUST be instances of these types.
"""

from __future__ import annotations

from typing import Any


class GatewayFailure(Exception):
    """Base class for all gateway failures."""

    failure_category: str = "unknown"

    def __init__(self, message: str, *, cause: Exception | None = None) -> None:
        super().__init__(message)
        self.cause = cause


class ContractViolation(GatewayFailure):
    """
    The request violates MCP protocol requirements or internal invariants.

    Per docs/FAILURE_MODEL.md:
    - Fatality: Fatal. Request cannot proceed.
    - MCP Representation: JSON-RPC error response with appropriate error code.
    """

    failure_category = "contract_violation"


class UpstreamFailure(GatewayFailure):
    """
    The external service (REST API) returned an error or unexpected response.

    Per docs/FAILURE_MODEL.md:
    - Fatality: Non-fatal to the gateway.
    - MCP Representation: ToolCallResult with isError: true.

    # TODO: UNDECIDED per docs/FAILURE_MODEL.md
    # - Should empty upstream responses be treated as errors?
    # - Should partial upstream responses (missing expected fields) hard-fail?
    # - How should non-JSON upstream responses be categorized?
    """

    failure_category = "upstream_failure"

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(message, cause=cause)
        self.status_code = status_code


class TransportFailure(GatewayFailure):
    """
    Communication with the external service failed at the transport layer.

    Per docs/FAILURE_MODEL.md:
    - Fatality: Fatal to the tool call. The tool cannot complete.
    - MCP Representation: JSON-RPC error with INTERNAL_ERROR or ToolCallResult with isError.
    """

    failure_category = "transport_failure"


class ConfigurationError(GatewayFailure):
    """
    The system is misconfigured and cannot operate correctly.

    Per docs/FAILURE_MODEL.md:
    - Fatality: Fatal. System should not start or should refuse requests.
    - MCP Representation: Not applicable (startup failure).

    # TODO: UNDECIDED per docs/FAILURE_MODEL.md (Issue #27)
    # Configuration errors are not currently enforced at startup.
    # The system does not validate endpoint configuration or fail fast on invalid config.
    """

    failure_category = "configuration_error"
