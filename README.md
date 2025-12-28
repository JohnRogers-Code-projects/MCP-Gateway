# MCP-Demo — Explicit Context Mediation for AI Workflows

This repository is a **conceptual demonstration** of how explicit context mediation can be used to build **predictable, composable AI workflows**.

It is designed to function as a reusable system component alongside other repositories (such as MLForge), while remaining **independent of any specific problem domain**.

---

## Purpose

Modern AI systems often rely on:
- implicit prompt chaining,
- unbounded context growth,
- loosely coordinated tool calls.

These approaches work initially but tend to fail as systems grow in complexity.

This repository explores an alternative approach based on:
- **explicit context objects**
- **bounded information flow**
- **deliberate orchestration**

The goal is not to build a framework, but to make **design tradeoffs visible and reviewable**.

---

## What This Repository Is (and Is Not)

### This repository **is**:
- A focused demonstration of context mediation concepts
- A single, opinionated orchestration flow
- A teaching and reasoning artifact
- A reusable component that does not change across domains

### This repository **is not**:
- A general-purpose MCP framework
- A plugin system
- A production-ready orchestration engine
- A reimplementation of any proprietary product

---

## Relationship to Other Repositories

This repository is part of a modular, multi-repo system:

- **MLForge**  
  Owns execution, persistence, job lifecycle, and APIs.

- **MCP-Demo (this repository)**  
  Owns context boundaries, orchestration decisions, and tool sequencing.

- **ForgeBreaker**  
  Intentionally stresses and breaks assumptions to explore failure modes.

New domains (e.g. trading cards, ingredient inventories, recommendation systems) can be introduced by supplying **domain adapters**, without modifying these core components.

---

## Design Constraints (Intentional)

This demo intentionally enforces the following constraints:

- A single explicit orchestration path (“golden path”)
- One canonical context object
- No dynamic tool discovery
- No plugin or extension mechanisms
- No attempt to scale or generalize beyond the demo

These constraints are deliberate.  
They exist to make **reasoning, boundaries, and failure modes obvious**, not to maximize flexibility.

---

## Domain Independence

Any domain-specific logic in this repository exists only for demonstration purposes.

Replacing the domain (e.g. trading cards → ingredients) requires changes only to:
- domain adapters
- domain vocabulary
- example data

The orchestration and context mediation logic remains unchanged.

---

## Inspiration and IP Boundaries

This project is inspired by publicly discussed concepts behind systems such as IBM’s ContextForge, but:

- does **not** implement proprietary APIs
- does **not** reproduce internal designs
- uses original code and simplified examples

The intent is conceptual exploration, not replication.

---

## Architecture Overview

The Python implementation in `mcp-demo/python/` demonstrates these concepts:

### Canonical Context Object

Every request creates an `ExecutionContext` that flows through all operations:
- Created via `from_request()` (single creation path)
- Immutable mutations via `with_tool_call()` and `with_result()`
- Sealed before returning to callers

### Single Golden Path

All MCP requests flow through one path:
```
POST /mcp → handle_request() → method handler → sealed response
```

### Orchestration vs Tool Separation

- **Orchestration** (`_handle_tools_call`): Validates, guards, decides policy
- **Tool Executor** (`call_tool`): Dumb HTTP executor, no intelligence

### Domain Isolation

Domain-specific endpoints are isolated in `domains/` package:
- Add a domain: create one file, import in `endpoints.py`
- Remove a domain: delete file, remove import

See [`mcp-demo/python/ARCHITECTURE.md`](mcp-demo/python/ARCHITECTURE.md) for detailed technical documentation.

---

## Why This Matters

By making context boundaries explicit and orchestration deliberate, this demo highlights:
- why naive prompt chaining breaks down,
- where context leakage occurs,
- and how AI systems can be made more predictable.

The value of this repository lies not in what it supports — but in what it intentionally refuses to support.