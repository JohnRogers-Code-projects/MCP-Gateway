"""
Endpoint definitions for REST-to-MCP adapter.

This module contains:
- Core types: HttpMethod, RestEndpoint
- Aggregated endpoint lists imported from domain modules

Domain-specific endpoints are isolated in the domains/ package.
To add a new domain: create domains/newdomain.py and import here.
To remove a domain: delete the file and remove the import.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


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
# Domain Endpoints (imported from isolated domain modules)
# -----------------------------------------------------------------------------

from .domains.jsonplaceholder import JSONPLACEHOLDER_ENDPOINTS
from .domains.openmeteo import OPEN_METEO_ENDPOINTS


# -----------------------------------------------------------------------------
# Combined Endpoints
# -----------------------------------------------------------------------------

DEFAULT_ENDPOINTS: list[RestEndpoint] = JSONPLACEHOLDER_ENDPOINTS + OPEN_METEO_ENDPOINTS
