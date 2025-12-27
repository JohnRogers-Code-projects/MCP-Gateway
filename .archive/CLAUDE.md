# Claude Instructions — MCP-Demo

This repository is a **conceptual demonstration**, not a framework.

Claude is used as an implementation assistant under **strict constraints**.

If a suggestion violates the intent described here, it should be rejected.

---

## Primary Goal

Refactor and maintain this repository so that:

- Context flow is explicit and traceable
- Orchestration decisions are deliberate and readable
- Boundaries between AI, tools, and orchestration are obvious
- Replacing the domain requires changing only a small adapter layer

Clarity and intent take precedence over flexibility or reuse.

---

## Non-Goals (Hard Constraints)

Claude must **not**:

- Introduce plugin systems
- Add configuration layers
- Generalize for arbitrary domains
- Create reusable libraries
- Add abstraction “just in case”
- Optimize for scalability or production readiness
- Mirror or reproduce proprietary ContextForge APIs or naming

If something appears “too flexible” or “framework-like”, it is likely incorrect.

---

## Design Philosophy

- One canonical context object
- One explicit orchestration flow (“golden path”)
- Tools are system components, not magic
- Context growth is intentional
- Context reduction is explicit
- Failure modes are visible

Deletion of code is encouraged if it improves clarity.

---

## Refactoring Strategy

All changes must be broken into **small, reviewable pull requests**.

Each pull request should:
- Change one conceptual thing
- Be understandable in isolation
- Include a brief rationale
- Minimize surface-area changes
- Prefer removing code over adding abstraction

---

## Required Pull Request Sequence

### PR 1 — Canonical Context Object
- Identify and centralize the primary context structure
- Remove implicit or ad-hoc context passing
- Make context shape obvious and documented

---

### PR 2 — Single Golden Path
- Identify the primary orchestration flow
- Remove or collapse alternative execution paths
- Ensure execution can be followed top-to-bottom

---

### PR 3 — Explicit Context Boundaries
- Identify where context grows
- Add at least one deliberate context reduction or summarization
- Make boundary decisions explicit in code

---

### PR 4 — Constrained Tool Invocation
- Replace generic “run tool” abstractions
- Make tool assumptions explicit
- Fail loudly when assumptions are violated

---

### PR 5 — Deliberate Failure Mode
- Introduce one realistic failure scenario
- Handle it explicitly
- Avoid generic exception handling
- Make tradeoffs visible

---

### PR 6 — Domain Adapter Isolation
- Isolate domain-specific logic
- Ensure swapping domains requires minimal change
- Prefer simple, concrete adapters over abstractions

---

### PR 7 — Documentation Alignment
- Ensure README reflects actual code structure
- Add comments only where they explain intent
- Remove comments that restate obvious behavior

---

## Final Instruction

This repository should feel:

- Opinionated
- Constrained
- Deliberate
- Easy to reason about

If a change exists only to make future changes easier, it should be rejected.