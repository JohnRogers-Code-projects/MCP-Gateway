# MCP Protocol Demo

**REST-to-MCP adapter with high-performance Rust parsing** — enabling LLMs to interact with any REST API through Anthropic's Model Context Protocol.

> **Note:** This is a portfolio project demonstrating understanding of MCP protocol concepts. It is not affiliated with or derived from any proprietary implementation.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Rust](https://img.shields.io/badge/rust-1.70+-orange.svg)](https://www.rust-lang.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

## What This Does

```
┌─────────────────┐     ┌──────────────────────┐     ┌─────────────────┐
│   LLM Agent     │────▶│  REST-to-MCP Adapter │────▶│   Any REST API  │
│ (Claude, GPT)   │◀────│                      │◀────│                 │
└─────────────────┘     └──────────────────────┘     └─────────────────┘
                               │
                               ▼
                        ┌──────────────────┐
                        │   Rust Parser    │
                        │   (~2M ops/sec)  │
                        └──────────────────┘
```

LLMs speak **MCP** (Model Context Protocol). Most APIs speak **REST**. This adapter bridges the gap:

1. **Tool Discovery** — LLM asks "what can I do?" → adapter returns available REST endpoints as MCP tools
2. **Tool Execution** — LLM calls a tool → adapter translates to REST, executes, returns MCP response
3. **Fast Parsing** — Rust-powered JSON-RPC 2.0 parsing handles the hot path at ~2M ops/sec

## Quick Start

```bash
# Clone and setup
git clone https://github.com/RogersJohn/MCP-Demo.git
cd MCP-Demo/mcp-demo/python

# Install
python -m venv .venv && .venv\Scripts\activate  # Windows
# or: source .venv/bin/activate                  # macOS/Linux
pip install -e ".[dev]"

# Run
uvicorn rest_to_mcp.server:app --reload
```

Open **http://localhost:8000** for the interactive dashboard.

## Live Demo

The dashboard includes:

| Tab | What It Does |
|-----|--------------|
| **Interactive Demo** | Send MCP requests, see responses in real-time |
| **Agent Playground** | Natural language queries triggering multi-tool orchestration |
| **Benchmarks** | Live Python vs Rust parser performance comparison |
| **Documentation** | Core concepts, architecture, message flow examples |
| **Test Runner** | Execute the full test suite with streaming output |

### Try It

```bash
# List available tools
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'

# Call a tool (get a post from JSONPlaceholder)
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"get_post","arguments":{"id":1}}}'
```

## Project Structure

```
mcp-demo/
├── python/
│   ├── rest_to_mcp/
│   │   ├── models.py      # Pydantic schemas for MCP messages
│   │   ├── adapter.py     # REST → MCP translation engine
│   │   ├── server.py      # FastAPI server
│   │   └── dashboard.py   # Demo UI routes
│   └── tests/             # Unit + integration tests
└── rust/
    └── mcp_parser/        # High-performance JSON-RPC parser
        └── src/lib.rs     # PyO3 bindings for Python interop
```

## Tech Stack

| Component | Technology | Why |
|-----------|------------|-----|
| Server | FastAPI + Uvicorn | Async ASGI, automatic OpenAPI docs |
| Validation | Pydantic 2.x | Runtime type enforcement, fast serialization |
| HTTP Client | httpx | Async requests to target REST APIs |
| Parser | Rust + PyO3 | Zero-GC latency on the hot path |
| Dashboard | Alpine.js | Reactive UI, no build step |

## Running Tests

```bash
cd mcp-demo/python

# All tests
pytest

# With coverage
pytest --cov=rest_to_mcp --cov-report=html

# Integration tests only (hits live API)
pytest tests/test_integration.py -v
```

## Rust Parser (Optional)

The Rust parser is optional but recommended for production workloads.

```bash
cd mcp-demo/rust/mcp_parser

# Build and test
cargo test
cargo bench  # ~2M ops/sec for simple requests

# Build Python wheel
pip install maturin
maturin develop --release
```

## Design Decisions

**Why protocol translation?**
Most valuable APIs already exist as REST. Rewriting them for MCP is wasteful. Translation lets LLMs use existing infrastructure.

**Why Rust for parsing?**
JSON-RPC parsing happens on every request. In a gateway handling thousands of req/sec, this is the hot path. Rust eliminates GC pauses and provides predictable latency.

**Why JSONPlaceholder as the demo API?**
Stable, free, no auth required, enough endpoints to demonstrate realistic tool mapping. Swap it for any REST API in production.

## Deployment

For Railway, Render, or similar:

```bash
# Procfile
web: uvicorn rest_to_mcp.server:app --host 0.0.0.0 --port $PORT
```

The dashboard auto-detects the deployment URL—no hardcoded values.

## License

MIT
