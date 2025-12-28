# Architecture

This document describes the internal architecture of the REST-to-MCP adapter.

---

## Request Flow

All MCP requests follow a single path:

```
POST /mcp
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  server.mcp_endpoint()                                      │
│  Parse JSON-RPC request                                     │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  adapter.handle_request()                                   │
│  THE GOLDEN PATH - single entry point for all operations    │
│                                                             │
│  1. Create ExecutionContext from request                    │
│  2. Route by method (initialize, tools/list, tools/call)    │
│  3. Seal context before return                              │
└─────────────────────────────────────────────────────────────┘
    │
    ▼ (for tools/call)
┌─────────────────────────────────────────────────────────────┐
│  adapter._handle_tools_call()                               │
│  ORCHESTRATION - intelligence lives here                    │
│                                                             │
│  1. Validate arguments (reject unknown, require path params)│
│  2. Guard destructive operations                            │
│  3. Delegate to tool executor                               │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  adapter.call_tool()                                        │
│  DUMB EXECUTOR - no intelligence, just HTTP                 │
│                                                             │
│  1. Build URL from endpoint + arguments                     │
│  2. Make HTTP request                                       │
│  3. Return result (success or error)                        │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  Response + Sealed Context                                  │
│  Context is immutable after sealing                         │
└─────────────────────────────────────────────────────────────┘
```

---

## ExecutionContext

The canonical context object that flows through all operations.

### Why It Exists

Context objects make data flow explicit. Without them:
- Request data is transformed into different shapes at each layer
- It becomes impossible to trace what data reached which component
- Debugging requires reading the entire call stack

With ExecutionContext:
- One object carries all request state
- Mutations are explicit and traceable
- Context can be sealed to prevent further changes

### Invariants (Enforced in Code)

1. **Created only via `from_request()`** - No ad-hoc construction
2. **request_id must be non-empty** - Blank IDs rejected
3. **method must be non-empty** - Blank methods rejected
4. **Results require tool_name** - Cannot add results without binding a tool first
5. **Sealed context is immutable** - No mutations after sealing
6. **Tool binding is one-time** - Cannot rebind to a different tool

### Lifecycle

```
from_request()     Create from JSON-RPC request
     │
     ▼
with_tool_call()   Bind tool name and arguments (immutable pattern)
     │
     ▼
with_result()      Append execution result (immutable pattern)
     │
     ▼
seal()             Mark as immutable, ready for return
```

---

## Orchestration vs Tool Separation

### Orchestration (_handle_tools_call)

**Owns:**
- Argument validation
- Policy decisions (destructive operation guards)
- Error response construction
- Context mutation

**Does NOT:**
- Make HTTP calls
- Know about specific REST APIs
- Handle transport-level errors

### Tool Executor (call_tool)

**Owns:**
- HTTP request construction
- URL building
- Response parsing

**Does NOT:**
- Validate arguments
- Guard against misuse
- Make policy decisions
- Infer intent

This separation ensures:
- Tools cannot be misused even if called directly
- Orchestration can be tested without HTTP
- Policy changes don't require tool changes

---

## Domain Isolation

Domain-specific endpoints are isolated in the `domains/` package.

```
rest_to_mcp/
├── domains/
│   ├── __init__.py           # Re-exports
│   ├── jsonplaceholder.py    # JSONPlaceholder API endpoints
│   └── openmeteo.py          # Open-Meteo API endpoints
├── endpoints.py              # Core types + aggregation
└── adapter.py                # Domain-agnostic adapter
```

### To Add a New Domain

1. Create `domains/newdomain.py`:
   ```python
   from ..endpoints import HttpMethod, RestEndpoint

   NEWDOMAIN_ENDPOINTS = [
       RestEndpoint(
           name="operation_name",
           path="/api/path",
           method=HttpMethod.GET,
           description="What this operation does",
           base_url="https://api.newdomain.com",
       ),
   ]
   ```

2. Import in `endpoints.py`:
   ```python
   from .domains.newdomain import NEWDOMAIN_ENDPOINTS
   DEFAULT_ENDPOINTS = ... + NEWDOMAIN_ENDPOINTS
   ```

### To Remove a Domain

1. Delete `domains/domainname.py`
2. Remove import from `endpoints.py`

---

## Deliberate Failure Modes

Failures are handled explicitly, not in generic catch-alls.

### Timeout

```python
except httpx.TimeoutException:
    raise ToolTimeoutError(name, HTTP_TIMEOUT_SECONDS)
```

The exception contains:
- `tool_name`: Which tool timed out
- `timeout_seconds`: How long we waited

Orchestration catches this and returns structured error:
```python
data={
    "tool": e.tool_name,
    "timeout_seconds": e.timeout_seconds,
    "failure_mode": "timeout",
}
```

### Validation Errors

Returned with structured data:
```python
data={"tool": params.name, "errors": validation_errors}
```

### Why Explicit Failure Modes Matter

- Generic `except Exception` hides what actually failed
- Structured error data enables automated handling
- Each failure mode can have different retry/recovery strategies

---

## Intentional Constraints

| Constraint | Why |
|------------|-----|
| Single entry point | One place to understand request handling |
| No dynamic tool discovery | Tools are known at compile time |
| No plugin system | Avoids runtime surprises |
| Sealed context | Prevents mutation after handoff |
| Strict validation | Unknown arguments are errors, not ignored |
| Explicit failures | Each failure type is visible and typed |

---

## Non-Goals

This codebase intentionally does NOT support:

- **Hot-reloading of tools** - Tools are registered at startup
- **Dynamic authorization** - No per-request permission checks
- **Partial execution** - All-or-nothing tool invocation
- **Streaming responses** - Complete responses only
- **Retry logic** - Callers handle retries
- **Caching** - No response memoization
- **Rate limiting** - Not implemented (documented tradeoff)

These are not missing features. They are explicit non-goals that keep the codebase simple and predictable.
