# MCP-Gateway — Explicit Context Mediation for AI Workflows

This repository is a **conceptual demonstration** of how explicit context mediation can be used to build **predictable, composable AI workflows**.

It was designed to function as a reusable system component alongside other repositories (such as MLForge), while remaining **independent of any specific problem domain**.

I built MCP-Gateway to explore what it would take to externalize tool execution, but I deliberately stopped short of integrating it once I realized the complexity tradeoff wasn’t justified yet.

---

## System Context

This repository implements the MCP-Gateway used by ForgeBreaker and LarderLab to expose domain tools to LLMs via a shared interface.
Despite the repository name, this service is active infrastructure within the system described here:
https://github.com/JohnRogers-Code-projects/JohnRogers

MCP-Gateway is responsible only for tool registration, discovery, invocation, and error normalization. All domain logic lives in the consuming applications.

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

- **MCP-Gateway (this repository)**
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

## Trust Model

**This gateway assumes all incoming requests originate from trusted clients.**

There is no authentication, authorization, or rate limiting. Any client that can reach the `/mcp` endpoint can invoke any registered tool with arbitrary arguments.

This is acceptable for:
- Local development
- Internal service-to-service communication within a trusted network
- Demonstration and learning purposes

**Production deployment would require:**
- Transport security (TLS)
- Client authentication (API keys, OAuth 2.0, mTLS)
- Per-tool authorization policies
- Input validation and sanitization at the gateway boundary
- Rate limiting and abuse prevention
- Audit logging of tool invocations

These concerns are intentionally deferred. The goal of this repository is to demonstrate context mediation patterns, not to provide a production-ready security model.

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

## Why This Matters

By making context boundaries explicit and orchestration deliberate, this demo highlights:
- why naive prompt chaining breaks down,
- where context leakage occurs,
- and how AI systems can be made more predictable.

The value of this repository lies not in what it supports — but in what it intentionally refuses to support.
