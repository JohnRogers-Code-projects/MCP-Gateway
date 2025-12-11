# MCP Demo: REST-to-MCP Adapter + Rust Parser

Portfolio project demonstrating skills relevant to IBM ContextForge development.

## What This Is

Two complementary components that mirror ContextForge's core functionality:

1. **Python REST-to-MCP Adapter** - Translates REST APIs into MCP-compliant tool interfaces
2. **Rust MCP Parser** - High-performance JSON-RPC 2.0 message parsing with Python bindings

## Why These Components

ContextForge is fundamentally about protocol translation and gateway functionality. These projects demonstrate:

- **Protocol translation**: REST → MCP conversion (core ContextForge feature)
- **JSON-RPC 2.0**: The wire protocol MCP uses
- **Async Python**: FastAPI/Starlette patterns matching ContextForge's stack
- **Pydantic validation**: Schema enforcement like ContextForge uses
- **Rust-Python interop**: Performance optimization for hot paths
- **Testing discipline**: Automated tests for reliability

## Architecture

```
┌─────────────────┐     ┌──────────────────────┐     ┌─────────────────┐
│   MCP Client    │────▶│  REST-to-MCP Adapter │────▶│   REST API      │
│  (LLM Agent)    │◀────│     (Python)         │◀────│ (JSONPlaceholder)│
└─────────────────┘     └──────────────────────┘     └─────────────────┘
                               │
                               ▼
                        ┌──────────────────┐
                        │   Rust Parser    │
                        │  (PyO3 bindings) │
                        └──────────────────┘
```

## Quick Start

### Python Adapter

```bash
cd python
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest  # 40 tests pass, 9 skipped (network-dependent)
uvicorn rest_to_mcp.server:app --reload
```

### Rust Parser

Requires Rust toolchain (install via https://rustup.rs/).

```bash
cd rust/mcp_parser
cargo test      # Run Rust tests
cargo bench     # Run benchmarks
maturin develop # Build Python bindings (pip install maturin first)
```

### Integration

```bash
cd python
pytest tests/test_integration.py -v
```

## Project Structure

```
mcp-demo/
├── python/
│   ├── rest_to_mcp/
│   │   ├── __init__.py
│   │   ├── models.py      # Pydantic schemas for MCP messages
│   │   ├── adapter.py     # REST-to-MCP translation logic
│   │   └── server.py      # FastAPI server exposing MCP endpoint
│   ├── tests/
│   │   ├── test_models.py
│   │   ├── test_adapter.py
│   │   └── test_integration.py
│   └── pyproject.toml
├── rust/
│   └── mcp_parser/
│       ├── src/lib.rs     # Parser implementation + PyO3 bindings
│       ├── Cargo.toml
│       └── tests/
└── README.md
```

## Key Design Decisions

### Why FastAPI?
ContextForge uses Uvicorn/Gunicorn with async Python. FastAPI provides the same ASGI foundation with automatic OpenAPI docs—useful for demonstrating the adapter's capabilities.

### Why Pydantic?
ContextForge uses Pydantic 2.11+ for validation. These models mirror that approach and show understanding of runtime type enforcement.

### Why Rust for parsing?
JSON-RPC parsing happens on every request. In a gateway handling thousands of requests/second, this is a hot path. Rust provides:
- Zero-copy parsing where possible
- Predictable latency (no GC pauses)
- Memory safety without runtime overhead

The PyO3 bindings let Python code call into Rust seamlessly.

### Why JSONPlaceholder as the target API?
It's stable, free, requires no auth, and has enough endpoints to demonstrate realistic tool mapping. Real deployments would target internal APIs.

## Testing Philosophy

- Unit tests for individual components
- Integration tests for end-to-end flows
- Property-based tests for parser edge cases (Rust side)
- No mocks where real calls are cheap (JSONPlaceholder is free)

## What's Not Here

This is a portfolio demo, not production software. Missing:
- Auth/OAuth (ContextForge handles this extensively)
- Rate limiting (demonstrated conceptually, not implemented)
- Multi-transport (only HTTP, no SSE/WebSocket/stdio)
- Tool caching/registry persistence
- Observability/tracing

These omissions are intentional—the goal is demonstrating core concepts cleanly, not building a second ContextForge.
