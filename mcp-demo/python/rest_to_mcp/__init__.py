"""REST-to-MCP Adapter package."""

from .adapter import (
    HttpMethod,
    RestEndpoint,
    RestToMcpAdapter,
    create_jsonplaceholder_adapter,
    create_multi_api_adapter,
)
from .config import (
    HTTP_ERROR_THRESHOLD,
    HTTP_TIMEOUT_SECONDS,
    JSONPLACEHOLDER_BASE_URL,
    JSONPLACEHOLDER_MAX_USER_ID,
    MCP_PROTOCOL_VERSION,
    OPEN_METEO_BASE_URL,
    SERVER_NAME,
    SERVER_VERSION,
    WMO_WEATHER_CODES,
    get_weather_description,
)
from .endpoints import (
    DEFAULT_ENDPOINTS,
    JSONPLACEHOLDER_ENDPOINTS,
    OPEN_METEO_ENDPOINTS,
)
from .models import (
    ContentBlock,
    ContentBlockDict,
    ErrorCode,
    ImageContent,
    InitializeResult,
    JsonRpcErrorData,
    JsonRpcErrorResponse,
    JsonRpcRequest,
    JsonRpcResponse,
    ListToolsResult,
    ScenarioStepResultDict,
    TextContent,
    Tool,
    ToolCallParams,
    ToolCallResult,
    ToolCallResultDict,
    ToolDict,
    ToolInputSchema,
    make_error_response,
    make_success_response,
)

__all__ = [
    # Adapter
    "RestToMcpAdapter",
    "RestEndpoint",
    "HttpMethod",
    "create_jsonplaceholder_adapter",
    "create_multi_api_adapter",
    # Endpoints
    "JSONPLACEHOLDER_ENDPOINTS",
    "OPEN_METEO_ENDPOINTS",
    "DEFAULT_ENDPOINTS",
    # Config
    "JSONPLACEHOLDER_BASE_URL",
    "OPEN_METEO_BASE_URL",
    "HTTP_ERROR_THRESHOLD",
    "HTTP_TIMEOUT_SECONDS",
    "WMO_WEATHER_CODES",
    "get_weather_description",
    "SERVER_NAME",
    "SERVER_VERSION",
    "MCP_PROTOCOL_VERSION",
    "JSONPLACEHOLDER_MAX_USER_ID",
    # Models - Pydantic
    "JsonRpcRequest",
    "JsonRpcResponse",
    "JsonRpcErrorResponse",
    "JsonRpcErrorData",
    "Tool",
    "ToolInputSchema",
    "ToolCallParams",
    "ToolCallResult",
    "ContentBlock",
    "TextContent",
    "ImageContent",
    "ListToolsResult",
    "InitializeResult",
    "ErrorCode",
    "make_error_response",
    "make_success_response",
    # Models - TypedDict
    "ToolDict",
    "ToolCallResultDict",
    "ContentBlockDict",
    "ScenarioStepResultDict",
]
