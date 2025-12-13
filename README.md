# MCP Protocol Demo

**REST-to-MCP adapter with high-performance Rust parsing** — enabling LLMs to interact with any REST API through Anthropic's Model Context Protocol.

> **Note:** This is a portfolio project demonstrating understanding of MCP protocol concepts. It is not affiliated with or derived from any proprietary implementation.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Rust](https://img.shields.io/badge/rust-1.70+-orange.svg)](https://www.rust-lang.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

## What This Does

```
                                                    ┌─────────────────────┐
                                               ┌───▶│  JSONPlaceholder    │
                                               │    │  (Users, Posts)     │
┌─────────────────┐     ┌──────────────────────┤    └─────────────────────┘
│   LLM Agent     │────▶│  REST-to-MCP Adapter │
│ (Claude, GPT)   │◀────│   (Multi-API)        │    ┌─────────────────────┐
└─────────────────┘     └──────────────────────┤    │  Open-Meteo         │
                               │               └───▶│  (Weather)          │
                               ▼                    └─────────────────────┘
                        ┌──────────────────┐
                        │   Rust Parser    │
                        │   (~2M ops/sec)  │
                        └──────────────────┘
```

LLMs speak **MCP** (Model Context Protocol). Most APIs speak **REST**. This adapter bridges the gap:

1. **Tool Discovery** — LLM asks "what can I do?" → adapter returns available REST endpoints as MCP tools
2. **Tool Execution** — LLM calls a tool → adapter translates to REST, executes, returns MCP response
3. **Multi-API Composition** — Chain tools across different APIs with automatic data flow between steps
4. **Fast Parsing** — Rust-powered JSON-RPC 2.0 parsing handles the hot path at ~2M ops/sec

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
| **Agent Playground** | Natural language queries with **cross-API tool chaining** (try "Check weather for user 3") |
| **Benchmarks** | Live Python vs Rust parser performance comparison |
| **Documentation** | Core concepts, architecture, message flow examples |
| **Test Runner** | Execute the full test suite with streaming output (59 tests) |

### Try It

```bash
# List available tools (10 tools across 2 APIs)
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'

# Call a tool (get a post from JSONPlaceholder)
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"get_post","arguments":{"id":1}}}'

# Call a weather tool (Open-Meteo API)
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"get_weather","arguments":{"latitude":"40.7128","longitude":"-74.0060","current_weather":"true"}}}'
```

## Multi-API Composition

A key enterprise capability: **chain tools across different backend APIs** with automatic data flow between steps.

### Real-World Example

```
Query: "Check the weather for user 3"

┌─────────────────────────────────────────────────────────────────────┐
│ Step 1: get_user (JSONPlaceholder API)                              │
│   Request:  GET https://jsonplaceholder.typicode.com/users/3        │
│   Response: { "name": "Clementine Bauch",                           │
│               "address": { "geo": { "lat": "-68.6102",              │
│                                     "lng": "-47.0653" }}}           │
├─────────────────────────────────────────────────────────────────────┤
│ Step 2: get_weather (Open-Meteo API)                                │
│   Input:    Coordinates extracted from Step 1 automatically        │
│   Request:  GET https://api.open-meteo.com/v1/forecast              │
│             ?latitude=-68.6102&longitude=-47.0653&current_weather=true │
│   Response: { "current_weather": { "temperature": -5.2,             │
│                                    "weathercode": 71 }}             │
├─────────────────────────────────────────────────────────────────────┤
│ Result: "Weather for Clementine Bauch: -5.2°C, Slight snow"         │
└─────────────────────────────────────────────────────────────────────┘
```

### How It Works

The adapter uses **result templating** to pass data between steps:

```python
# Scenario definition in playground.py
ScenarioStep(
    tool="get_weather",
    args_template={
        "latitude": "$result.0.address.geo.lat",   # Extract from step 0
        "longitude": "$result.0.address.geo.lng",  # Extract from step 0
    },
)
```

- `$result.0` — References the result of step 0 (get_user)
- `.address.geo.lat` — Dot-notation path into the JSON response

### Why This Matters

This pattern mirrors real enterprise integration scenarios:
- "Get customer from CRM, check their order status in ERP"
- "Fetch server metrics from Instana, create ticket in ServiceNow"
- "Query inventory system, update pricing in commerce platform"

The gateway isn't tied to a single backend—it orchestrates across your entire API portfolio.

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

**Why multi-API composition?**
Real enterprise workflows span multiple systems. A customer lookup might hit CRM, then ERP, then a notification service. The adapter's `$result.N.path` templating enables this without custom code for each integration.

**Why Rust for parsing?**
JSON-RPC parsing happens on every request. In a gateway handling thousands of req/sec, this is the hot path. Rust eliminates GC pauses and provides predictable latency.

**Why JSONPlaceholder + Open-Meteo?**
Both are stable, free, and require no authentication. Together they demonstrate multi-API orchestration with real cross-system data flow. Swap them for any REST APIs in production.

## Deployment

For Railway, Render, or similar:

```bash
# Procfile
web: uvicorn rest_to_mcp.server:app --host 0.0.0.0 --port $PORT
```

The dashboard auto-detects the deployment URL—no hardcoded values.

## License

MIT
