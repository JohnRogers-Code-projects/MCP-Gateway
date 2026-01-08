# MCP Gateway Failure Model

This document defines the canonical failure taxonomy for MCP Gateway.

All failure paths in the system MUST map to one of these categories.
Ambiguity MUST hard-fail. There is no "best effort" mode.

---

## Failure Taxonomy

### 1. ContractViolation

**Definition:** The request violates MCP protocol requirements or internal invariants.

**Current Implementations:**
- `ContextError` — ExecutionContext invariant violation
- `ToolValidationError` — Tool invocation fails argument validation
- `ErrorCode.INVALID_REQUEST` — Malformed JSON-RPC request
- `ErrorCode.INVALID_PARAMS` — Missing or invalid parameters
- `ErrorCode.METHOD_NOT_FOUND` — Unsupported MCP method

**Fatality:** Fatal. Request cannot proceed.

**MCP Representation:** JSON-RPC error response with appropriate error code.

---

### 2. UpstreamFailure

**Definition:** The external service (REST API) returned an error or unexpected response.

**Current Implementations:**
- HTTP response with status >= 400 (mapped to `ToolCallResult.isError = True`)

**Fatality:** Non-fatal to the gateway. The gateway successfully processed the request; the upstream failed.

**MCP Representation:** `ToolCallResult` with `isError: true` and error content.

---

### 3. TransportFailure

**Definition:** Communication with the external service failed at the transport layer.

**Current Implementations:**
- `ToolTimeoutError` — External service did not respond within timeout
- `httpx.HTTPError` — Connection refused, DNS failure, TLS errors, etc.

**Fatality:** Fatal to the tool call. The tool cannot complete.

**MCP Representation:**
- Timeout: JSON-RPC error with `ErrorCode.INTERNAL_ERROR` and structured data (`failure_mode: "timeout"`)
- Other HTTP errors: `ToolCallResult` with `isError: true`

---

### 4. ConfigurationError

**Definition:** The system is misconfigured and cannot operate correctly.

**Current Implementations:**
- None explicitly implemented

**Fatality:** Fatal. System should not start or should refuse requests.

**MCP Representation:** Not applicable (startup failure).

> **UNDECIDED — requires explicit architectural decision:**
> Configuration errors are not currently enforced at startup. The system does not validate endpoint configuration or fail fast on invalid config. See Issue #27.

---

## Failure Propagation Rules

### Rule 1: Failures Must Be Explicit

Every failure MUST be represented by a defined type. Generic `except Exception` handlers are prohibited except at the outermost boundary for logging.

**Current Compliance:** Partial. The adapter catches specific exceptions (`TimeoutException`, `HTTPError`) but has one generic catch for param parsing.

### Rule 2: Ambiguity Must Hard-Fail

If the system cannot determine the correct behavior, it MUST fail rather than guess.

**Examples:**
- Missing required tool arguments → Fail with validation error
- Unknown tool name → Fail with INVALID_PARAMS
- Empty request ID → Fail with ContextError

**Current Compliance:** Implemented in `ExecutionContext` and argument validation.

### Rule 3: No Silent Degradation

Partial data, missing fields, or unexpected responses MUST NOT be silently normalized into "success."

> **UNDECIDED — requires explicit architectural decision:**
> The current implementation does not validate upstream response shapes. An empty JSON response from upstream is treated as success. See Issue #2.

### Rule 4: Context Preserves Failure State

When a failure occurs, the `ExecutionContext` MUST be sealable and returnable with failure information intact.

**Current Compliance:** Implemented. Context is always sealed before return.

---

## Failure Response Format

All failures that reach the MCP boundary MUST be represented as JSON-RPC responses:

### Error Response Structure
```json
{
  "jsonrpc": "2.0",
  "id": "<request_id>",
  "error": {
    "code": <ErrorCode>,
    "message": "<human-readable message>",
    "data": {
      "tool": "<tool_name if applicable>",
      "failure_mode": "<category>",
      "<additional structured data>"
    }
  }
}
```

### Tool Error Result Structure
```json
{
  "content": [{"type": "text", "text": "<error details>"}],
  "isError": true
}
```

---

## Error Code Mapping

| Failure Category | JSON-RPC Error Code | Value |
|-----------------|---------------------|-------|
| ContractViolation (parse) | PARSE_ERROR | -32700 |
| ContractViolation (request) | INVALID_REQUEST | -32600 |
| ContractViolation (method) | METHOD_NOT_FOUND | -32601 |
| ContractViolation (params) | INVALID_PARAMS | -32602 |
| TransportFailure | INTERNAL_ERROR | -32603 |
| UpstreamFailure | (not an error response) | N/A |

---

## Undecided Points

The following require explicit architectural decisions before implementation:

1. **UNDECIDED:** Should empty upstream responses be treated as errors?
2. **UNDECIDED:** Should configuration validation fail startup?
3. **UNDECIDED:** Should partial upstream responses (missing expected fields) hard-fail?
4. **UNDECIDED:** How should non-JSON upstream responses be categorized?

---

## Non-Goals

This failure model explicitly does NOT cover:

- **Retries** — Callers handle retry logic
- **Circuit breakers** — Not implemented
- **Graceful degradation** — Failures are hard failures
- **Error recovery** — No automatic recovery mechanisms

These are documented non-goals per ARCHITECTURE.md.
