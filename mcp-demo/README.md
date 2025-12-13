# MCP Demo Components

This directory contains the core implementation:

```
mcp-demo/
├── python/          # REST-to-MCP adapter (FastAPI server)
│   ├── rest_to_mcp/ # Core adapter code
│   └── tests/       # Test suite (59 tests)
└── rust/
    └── mcp_parser/  # High-performance JSON-RPC parser
```

## Available Tools (10 total)

**JSONPlaceholder API** (8 tools):
- `get_posts`, `get_post`, `create_post`, `update_post`, `delete_post`
- `get_comments`, `get_users`, `get_user`

**Open-Meteo Weather API** (2 tools):
- `get_weather` - Current weather for coordinates
- `get_forecast` - 7-day forecast for coordinates

## Quick Start

```bash
# Python adapter
cd python
python -m venv .venv && .venv\Scripts\activate  # Windows
pip install -e ".[dev]"
uvicorn rest_to_mcp.server:app --reload

# Rust parser (optional, for benchmarks)
cd rust/mcp_parser
pip install maturin
maturin develop --release
```

See the [root README](../README.md) for full documentation.
