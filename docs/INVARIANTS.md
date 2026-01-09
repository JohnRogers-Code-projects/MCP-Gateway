# MCP Gateway Invariants

This document lists **only invariants that are mechanically enforced in code**.

Aspirational invariants do not belong here. If it is not enforced, it is not an invariant.

---

## Invariant Registry

### INV-1: Failure Authority

**Statement:** No raw exception may escape the gateway boundary. All failures must be `GatewayFailure` instances.

**Enforced in:**
- `adapter.py:handle_request()` — wraps unknown exceptions in `GatewayInternalFailure`
- `errors.py` — defines `GatewayFailure` hierarchy

**What breaks if violated:** Untyped exceptions could crash the server or leak internal details to clients.

---

### INV-2: Ambiguity Hard-Fail

**Statement:** Ambiguous or underspecified inputs must fail immediately. No guessing, no normalization.

**Enforced in:**
- `models.py:ExecutionContext.from_request()` — rejects empty IDs, empty methods
- `endpoints.py:RestEndpoint.validate_arguments()` — rejects unknown arguments
- `adapter.py:_call_tool()` — raises `ContractViolation` for unknown tools
- `adapter.py:_build_url()` — raises `ContractViolation` for missing path params
- `adapter.py:_build_body()` — raises `ContractViolation` for missing body params

**What breaks if violated:** Silent incorrect behavior. Wrong tool calls. Data corruption.

---

### INV-3: Validation Authority

**Statement:** MCP validation cannot be bypassed. Invalid requests cannot be instantiated.

**Enforced in:**
- `models.py` — All MCP models use `ConfigDict(extra="forbid")`
- `server.py:mcp_endpoint()` — Ingress validation via Pydantic construction
- `server.py:mcp_endpoint()` — Egress type validation before response emission

**What breaks if violated:** Malformed MCP could be emitted to clients. Protocol violations.

---

### INV-4: Execution Authority (Single Request Path)

**Statement:** All gateway execution flows through exactly one entry point. No bypass paths exist.

**Enforced in:**
- `adapter.py:handle_request()` — sole authoritative entry point
- `adapter.py:_call_tool()` — private (underscore prefix)
- `adapter.py:_list_tools()` — private (underscore prefix)
- `server.py` — `GET /tools` endpoint removed

**What breaks if violated:** Validation bypass. Inconsistent behavior. Security holes.

---

### INV-5: State Immutability (Tool Registry)

**Statement:** The tool registry cannot be mutated after construction.

**Enforced in:**
- `adapter.py:__init__()` — wraps registry in `MappingProxyType`
- `adapter.py:endpoints` — property returns frozen view
- `register_endpoint()` — removed entirely

**What breaks if violated:** Runtime configuration drift. Non-deterministic behavior.

---

### INV-6: Context Sealing

**Statement:** ExecutionContext is sealed before leaving the adapter. Sealed contexts cannot be mutated.

**Enforced in:**
- `adapter.py:handle_request()` — calls `context.seal()` before every return
- `models.py:ExecutionContext.seal()` — sets `_sealed = True`
- `models.py:ExecutionContext._check_not_sealed()` — raises `ContextError` on mutation

**What breaks if violated:** Downstream code could corrupt request state. Race conditions.

---

## Invariant Test Requirements

Each invariant MUST have at least one test that verifies:

1. The invariant holds under normal operation
2. Violations cause immediate, typed failure

Tests are located in `tests/test_invariants.py`.

---

## Adding New Invariants

New invariants require:

1. Mechanical enforcement in code (not just convention)
2. Entry in this document with enforcement locations
3. At least one test that asserts violation fails
4. ADR update if the invariant is architectural

If you cannot point to code that enforces it, it is not an invariant.

---

## Relationship to ADR-0001

This document is the operational companion to ADR-0001. The ADR defines architectural decisions; this document lists their enforcement points.

Changes to invariants require ADR review.
