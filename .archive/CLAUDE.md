# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MCP-Demo is a portfolio project demonstrating REST-to-MCP protocol translation. It consists of two components:
1. **Python REST-to-MCP Adapter** (`mcp-demo/python/`) - FastAPI server translating REST APIs into MCP tool interfaces
2. **Rust MCP Parser** (`mcp-demo/rust/mcp_parser/`) - High-performance JSON-RPC 2.0 parser with PyO3 Python bindings

## Build & Development Commands

### Python Adapter
```bash
cd mcp-demo/python
python -m venv .venv && .venv\Scripts\activate  # Windows
pip install -e ".[dev]"

# Run tests (40 pass, 9 skipped for network-dependent)
pytest

# Run single test file
pytest tests/test_adapter.py -v

# Run server
uvicorn rest_to_mcp.server:app --reload

# Linting and type checking
ruff check .
mypy rest_to_mcp
```

### Rust Parser
```bash
cd mcp-demo/rust/mcp_parser

# Build and test
cargo build --release
cargo test

# Run benchmarks
cargo bench

# Build Python bindings (requires maturin)
pip install maturin
maturin develop --release
```

### Integration Testing
```bash
cd mcp-demo/python
pytest tests/test_integration.py -v
```

## Architecture

```
MCP Client (LLM Agent) ──> REST-to-MCP Adapter (Python) ──> REST API (JSONPlaceholder)
                                    │
                                    ▼
                            Rust Parser (PyO3 bindings)
```

### Python Adapter (`mcp-demo/python/rest_to_mcp/`)
- `models.py` - Pydantic schemas for MCP JSON-RPC messages
- `adapter.py` - REST-to-MCP translation logic, tool discovery from OpenAPI specs
- `server.py` - FastAPI ASGI server exposing MCP endpoint
- `dashboard.py` - Demo UI routes and WebSocket test runner

### Dashboard UI (`mcp-demo/python/rest_to_mcp/static/`, `templates/`)
- Interactive MCP request tester with example payloads
- Documentation explaining core MCP concepts and architecture
- Live test runner streaming pytest output via WebSocket
- Run server and visit http://localhost:8000/ to access

### Rust Parser (`mcp-demo/rust/mcp_parser/src/lib.rs`)
- JSON-RPC 2.0 request/response parsing with serde_json
- PyO3 bindings exposing `parse_request()`, `parse_response()`, `is_valid()`, `parse_requests_batch()`
- Validates JSON-RPC version, required fields, ID types, and params structure

## Key Dependencies
- Python 3.11+, FastAPI, Pydantic 2.5+, httpx, uvicorn, Jinja2, websockets
- Rust 1.70+, PyO3 0.22, serde, maturin for Python wheel builds
- Alpine.js (CDN) for dashboard interactivity - no build step required

## Testing
- Unit tests for models and adapter components
- Integration tests hit live JSONPlaceholder API (no mocks for cheap real calls)
- Rust side uses property-based tests for parser edge cases
- pytest configured with asyncio_mode="auto" and coverage reporting

## Code Standards & Behavior Rules

### Communication Style
- No sycophancy - be direct, objective, and technically honest
- Question requirements when they seem incomplete, contradictory, or suboptimal
- Rubber-duck reasoning for complex logic before implementing

### Before Writing Code
- Explain architectural decisions and trade-offs before implementing
- Suggest better alternatives when a proposed approach is suboptimal
- Use industry-standard patterns and explain why they're standard

### While Working
- Point out code smells and technical debt as you encounter them
- Flag performance implications and security concerns proactively
- Suggest refactors for existing code rather than just adding features
- Call out when dependencies are overkill or outdated

### Code Quality
- Write tests that catch real bugs: edge cases, error conditions, race conditions - not just happy paths
- Explain regex, complex queries, and gnarly algorithms inline with comments
- Never dump cryptic code without explanation

### Token Efficiency
- Be concise - avoid verbose explanations when brief ones suffice
- Don't repeat file contents unnecessarily; reference by line numbers
- Batch related operations into single tool calls where possible
- Skip boilerplate commentary; focus on what's changed and why
- Use diffs and targeted edits over full file rewrites
- Omit obvious observations; state only what adds value