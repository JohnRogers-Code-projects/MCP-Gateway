# ADR-0001: Core Architecture Decisions

**Status:** Accepted
**Date:** 2026-01-08
**Deciders:** Repository owner

---

## Context

MCP Gateway translates REST API endpoints into MCP-compliant tools. The system must:

1. Maintain predictable behavior under all conditions
2. Make data flow explicit and traceable
3. Prevent silent failures and guessing
4. Keep the codebase simple and auditable

Modern AI systems often suffer from implicit prompt chaining, unbounded context growth, and loosely coordinated tool calls. This gateway exists to demonstrate an alternative based on explicit context objects, bounded information flow, and deliberate orchestration.

---

## Decision

### 1. Single Request Path ("Golden Path")

All MCP requests flow through exactly one entry point: `adapter.handle_request()`.

There are no alternative handlers, no direct tool invocation paths, and no bypasses.

**Rationale:** One path means one place to understand, audit, and secure request handling.

### 2. Canonical Execution Context

All request state is carried in `ExecutionContext`, which:

- Is created only via `from_request()` (single creation path)
- Enforces invariants (non-empty IDs, no results without tool binding)
- Is sealed before leaving the adapter (immutable after handoff)
- Uses immutable patterns for all mutations (`with_tool_call()`, `with_result()`)

**Rationale:** Explicit context objects make data flow visible. Sealed contexts prevent downstream mutation.

### 3. Separation of Orchestration and Execution

- **Orchestration** (`_handle_tools_call`) owns policy: argument validation, destructive operation guards, error response construction
- **Tool Executor** (`call_tool`) owns mechanics: HTTP request construction, URL building, response parsing

The tool executor is deliberately "dumb." It does not validate, guard, or infer intent.

**Rationale:** Separation ensures tools cannot be misused even if called directly, orchestration can be tested without HTTP, and policy changes don't require tool changes.

### 4. Deliberate Failure Modes

Failures are handled explicitly with typed exceptions:

- `ContextError` — Invariant violations
- `ToolValidationError` — Invalid tool parameters
- `ToolTimeoutError` — External service timeout

Generic `except Exception` is prohibited except at the outermost boundary.

**Rationale:** Explicit failure types make each failure mode visible, testable, and independently handleable.

### 5. Tools Are Immutable After Registration

Tools are registered at startup and do not change during runtime.

**Rationale:** Runtime tool mutation creates configuration drift and makes behavior non-deterministic.

**Enforcement:** The tool registry is wrapped in `MappingProxyType` after construction. Mutation attempts raise `TypeError`. The `register_endpoint()` method has been removed.

---

## Rejected Alternatives

### Plugin/Extension System

A dynamic plugin system would allow adding tools at runtime.

**Rejected because:**
- Introduces runtime surprises
- Makes behavior non-deterministic
- Complicates security auditing
- Contradicts the "predictable behavior" goal

### Multiple Request Handlers

Separate handlers for different MCP methods (one for `tools/list`, one for `tools/call`, etc.).

**Rejected because:**
- Fragments request flow understanding
- Creates bypass opportunities
- Makes cross-cutting concerns (logging, context creation) inconsistent

### Generic Exception Handling

Catching all exceptions with a single handler that normalizes errors.

**Rejected because:**
- Hides actual failure modes
- Prevents type-specific error handling
- Makes debugging difficult
- Allows silent degradation

### Mutable Context Objects

Using a context object that can be mutated in place throughout the request lifecycle.

**Rejected because:**
- Makes it impossible to know context state at any point
- Allows downstream code to corrupt upstream state
- Prevents safe concurrency

---

## Non-Negotiable Invariants

These invariants MUST NOT be violated without a new ADR:

1. **Single entry point:** All requests go through `handle_request()`
2. **Context sealing:** Context is sealed before leaving the adapter
3. **No guessing:** Ambiguous inputs fail rather than being normalized
4. **Explicit failures:** Every failure maps to a defined type
5. **Tool immutability:** Tools do not change after startup

---

## Adapter Prohibitions

The adapter is explicitly FORBIDDEN from:

1. **Inferring intent** — If the request doesn't specify something, fail; don't guess
2. **Silent normalization** — Partial or malformed data is not "fixed up"
3. **Dynamic tool discovery** — Tools are known at compile/startup time
4. **Tolerating ambiguity** — Unknown arguments are errors, not ignored
5. **Hiding failures** — Every error is surfaced, not swallowed
6. **Breaking the golden path** — No alternative request handling paths

---

## Consequences

### Positive

- System behavior is predictable and auditable
- Failures are visible and categorized
- Context state is always known
- Security review is tractable (one path)

### Negative

- Less flexible than plugin systems
- Requires restart to add tools
- Stricter than necessary for simple use cases

### Neutral

- Requires discipline to maintain invariants
- Documentation must stay synchronized with code

---

## Compliance

Compliance with this ADR is verified by:

1. Code review against prohibited behaviors
2. Tests that assert invariant violations fail (see `tests/test_invariants.py`)
3. Absence of alternative request paths
4. Structural enforcement in code (see `docs/INVARIANTS.md`)

**Enforcement status:**
- Issue #20 (Failure authority): Enforced
- Issue #21 (Ambiguity hard-fail): Enforced
- Issue #22 (Validation authority): Enforced
- Issue #23 (Execution authority): Enforced
- Issue #24 (Tool immutability): Enforced
