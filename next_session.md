# MCP-Demo: Next Session

## Purpose of This Project

This is a **portfolio demonstration** created to show understanding of MCP protocol concepts and REST-to-MCP translation patterns. It is NOT a clone or reimplementation of IBM ContextForge.

**Goal:** Demonstrate competency in the technical concepts relevant to IBM's ContextForge product as part of a job application. This project shows I understand:
- Protocol translation (REST → MCP)
- JSON-RPC 2.0 message handling
- Tool discovery and execution patterns
- Performance optimization with Rust
- Multi-tool agent orchestration

All code is original, uses only public documentation about MCP, and targets freely available public APIs.

---

## Current State (2024-12-12)

Project is **feature-complete** with:
- REST-to-MCP adapter translating JSONPlaceholder API
- Rust JSON-RPC parser with PyO3 bindings
- Interactive dashboard with 5 tabs
- Tooltips explaining technical concepts in plain English
- 49 Python tests + 14 Rust tests passing

---

## Next Feature: Multi-API Tool Composition

### Why This Matters

IBM's ContextForge value proposition includes "rapidly bring a client's **vast portfolio** of existing APIs into the AI agent ecosystem." Currently this demo only shows one API. Adding a second API demonstrates:

1. The gateway pattern isn't tied to a single backend
2. Cross-system data flow (enterprise integration core skill)
3. Agent orchestration across multiple services

### Implementation Plan

**Add Open-Meteo weather API** (free, no API key required)

1. **Add weather tools to `adapter.py`:**
   - `get_weather` - Get current weather for coordinates
   - `get_forecast` - Get 7-day forecast for coordinates

2. **Add cross-API scenario to `playground.py`:**
   ```
   Query: "Get the location of user 3 and check the weather there"

   Step 1: get_user (JSONPlaceholder) → returns user with address/geo
   Step 2: get_weather (Open-Meteo) → uses lat/lng from user
   Step 3: Summary combining both results
   ```

3. **No UI changes needed** - playground already handles multi-step traces

### API Details

Open-Meteo endpoint:
```
GET https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lng}&current_weather=true
```

JSONPlaceholder users include geo coordinates:
```json
{
  "id": 3,
  "name": "Clementine Bauch",
  "address": {
    "geo": { "lat": "-68.6102", "lng": "-47.0653" }
  }
}
```

### Estimated Scope

~1-2 hours:
- Add `RestEndpoint` definitions for Open-Meteo (~15 min)
- Add scenario pattern matching (~15 min)
- Test and verify (~30 min)

---

## Files to Modify

| File | Change |
|------|--------|
| `adapter.py` | Add Open-Meteo endpoints to `JSONPLACEHOLDER_ENDPOINTS` (rename to `DEFAULT_ENDPOINTS`) |
| `playground.py` | Add cross-API scenario with geo lookup |
| `mcp-demo/README.md` | Update to mention multi-API capability |

---

## How to Run

```bash
cd mcp-demo/python
. .venv/Scripts/activate  # Windows
uvicorn rest_to_mcp.server:app --reload
```

Open http://localhost:8000 - Rust parser should show as available in Benchmarks tab.

---

## Test Commands

```bash
# Python tests
cd mcp-demo/python && pytest -v

# Rust tests
cd mcp-demo/rust/mcp_parser
PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1 cargo test
```
