"""
Dashboard Routes

Provides the demo dashboard UI and supporting endpoints:
- Static file serving (CSS, JS)
- HTML template rendering
- WebSocket endpoint for streaming test output
- WebSocket endpoint for live benchmark comparison

Kept separate from server.py to isolate demo UI from core MCP logic.
In production, you'd likely disable this entirely or put it behind auth.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from .benchmarks import (
    PAYLOADS,
    RUST_AVAILABLE,
    benchmark_python,
    benchmark_rust,
    get_payload_info,
)
from .playground import (
    EXAMPLE_QUERIES,
    match_scenario,
    substitute_args,
    build_summary,
)

if TYPE_CHECKING:
    from .adapter import RestToMcpAdapter

# Paths relative to this file
BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"

# Router for dashboard endpoints
router = APIRouter()

# Jinja2 templates
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request) -> HTMLResponse:
    """Serve the main dashboard page."""
    return templates.TemplateResponse("dashboard.html", {"request": request})


@router.websocket("/ws/tests")
async def websocket_test_runner(websocket: WebSocket) -> None:
    """
    WebSocket endpoint for streaming test output.

    Runs pytest and streams stdout/stderr line by line to the client.
    This gives real-time feedback rather than blocking until tests complete.

    Security note: In production, this would need authentication.
    Running arbitrary subprocess commands is dangerous - here we only run pytest.
    """
    await websocket.accept()
    await websocket.send_text("WebSocket connected successfully")

    # Find the python directory (where tests live)
    python_dir = BASE_DIR.parent

    try:
        # Run pytest with unbuffered output for real-time streaming
        # -v for verbose, --tb=short for concise tracebacks
        await websocket.send_text(f"Starting pytest in: {python_dir}")
        await websocket.send_text(f"Python executable: {sys.executable}")
        env = {**os.environ, "PYTHONUNBUFFERED": "1"}
        process = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "pytest",
            "-v", "--tb=short", "-x",  # -x stops on first failure for faster feedback
            cwd=str(python_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=env,
        )

        # Stream output line by line
        while True:
            if process.stdout is None:
                break

            line = await process.stdout.readline()
            if not line:
                break

            try:
                await websocket.send_text(line.decode("utf-8", errors="replace").rstrip())
            except WebSocketDisconnect:
                process.kill()
                return

        # Wait for process to complete
        await process.wait()

        # Send summary
        exit_code = process.returncode
        if exit_code == 0:
            await websocket.send_text("\n✓ All tests passed!")
        else:
            await websocket.send_text(f"\n✗ Tests failed (exit code {exit_code})")

    except Exception as e:
        await websocket.send_text(f"Error running tests: {e}")
    finally:
        await websocket.close()


@router.websocket("/ws/benchmarks")
async def websocket_benchmark_runner(websocket: WebSocket) -> None:
    """
    WebSocket endpoint for streaming benchmark results.

    Runs Python vs Rust parser benchmarks and streams progress/results.
    Client sends: {"payload": "simple"|"complex", "iterations": 1000-100000}
    Server sends: {"type": "progress"|"result"|"complete"|"error", ...}
    """
    await websocket.accept()

    try:
        # Receive benchmark config
        data = await websocket.receive_json()
        payload_name = data.get("payload", "simple")
        iterations = min(max(int(data.get("iterations", 10000)), 100), 100000)

        payload = PAYLOADS.get(payload_name, PAYLOADS["simple"])

        # Send initial status
        await websocket.send_json({
            "type": "status",
            "message": f"Running benchmarks with {iterations:,} iterations...",
            "rust_available": RUST_AVAILABLE,
        })

        # Run Python benchmark
        await websocket.send_json({
            "type": "progress",
            "parser": "python",
            "message": "Running Python benchmark (json.loads + Pydantic)...",
        })

        python_result = benchmark_python(payload, payload_name, iterations)

        await websocket.send_json({
            "type": "result",
            "result": python_result.to_dict(),
        })

        # Run Rust benchmark if available
        if RUST_AVAILABLE:
            await websocket.send_json({
                "type": "progress",
                "parser": "rust",
                "message": "Running Rust benchmark (mcp_parser)...",
            })

            rust_result = benchmark_rust(payload, payload_name, iterations)

            await websocket.send_json({
                "type": "result",
                "result": rust_result.to_dict(),
            })

            # Calculate speedup
            speedup = None
            if python_result.ops_per_sec > 0:
                speedup = round(rust_result.ops_per_sec / python_result.ops_per_sec, 2)

            await websocket.send_json({
                "type": "complete",
                "speedup": speedup,
                "message": f"Rust is {speedup}x faster" if speedup else "Benchmark complete",
            })
        else:
            await websocket.send_json({
                "type": "complete",
                "speedup": None,
                "message": "Rust parser not available. Install Rust and run: maturin develop --release",
                "rust_install_hint": True,
            })

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({
                "type": "error",
                "message": str(e),
            })
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


@router.get("/api/benchmark-info")
async def benchmark_info() -> dict:
    """Get information about available benchmarks."""
    return {
        "payloads": get_payload_info(),
        "rust_available": RUST_AVAILABLE,
        "iterations_options": [1000, 10000, 100000],
    }


# Store adapter reference for playground to use
_adapter: RestToMcpAdapter | None = None


def set_adapter(adapter: RestToMcpAdapter) -> None:
    """Set the adapter instance for playground to use."""
    global _adapter
    _adapter = adapter


@router.websocket("/ws/playground")
async def websocket_playground(websocket: WebSocket) -> None:
    """
    WebSocket endpoint for agent playground.

    Executes multi-tool scenarios step-by-step with live streaming.
    Client sends: {"input": "Get posts by user 1"}
    Server sends: scenario_matched, step_start, step_result, complete events
    """
    await websocket.accept()

    try:
        # Receive user input
        data = await websocket.receive_json()
        user_input = data.get("input", "").strip()

        if not user_input:
            await websocket.send_json({
                "type": "error",
                "message": "Please enter a query.",
            })
            return

        # Match scenario
        scenario, captures = match_scenario(user_input)

        if not scenario:
            await websocket.send_json({
                "type": "error",
                "message": f"I don't understand that request. Try one of these:\n• {chr(10).join(EXAMPLE_QUERIES[:3])}",
            })
            return

        # Send scenario matched event
        await websocket.send_json({
            "type": "scenario_matched",
            "name": scenario.description,
            "steps_count": len(scenario.steps),
        })

        # Check adapter availability
        if _adapter is None:
            await websocket.send_json({
                "type": "error",
                "message": "Adapter not initialized. Please restart the server.",
            })
            return

        # Execute steps
        results: list[dict] = []

        for i, step in enumerate(scenario.steps):
            # Send step start
            await websocket.send_json({
                "type": "step_start",
                "index": i,
                "tool": step.tool,
                "label": step.label,
            })

            # Build arguments from template (pass previous results for cross-step data flow)
            args = substitute_args(step.args_template, captures, results)

            # Execute the tool
            parsed_data = {}
            try:
                if step.tool == "__tools_list__":
                    # Special case: tools/list
                    from .models import JsonRpcRequest
                    request = JsonRpcRequest(id=1, method="tools/list", params={})
                    response = await _adapter.handle_request(request)
                    tool_result = response.result if hasattr(response, "result") else {}
                    parsed_data = tool_result
                else:
                    # Normal tool call
                    tool_result = await _adapter.call_tool(step.tool, args)
                    tool_result = tool_result.model_dump() if hasattr(tool_result, "model_dump") else tool_result

                    # Parse the JSON from content for cross-step data flow
                    if isinstance(tool_result, dict) and "content" in tool_result:
                        content_list = tool_result.get("content", [])
                        if content_list and isinstance(content_list[0], dict):
                            text = content_list[0].get("text", "")
                            try:
                                parsed_data = json.loads(text)
                            except (json.JSONDecodeError, TypeError):
                                parsed_data = {}
            except Exception as e:
                tool_result = {"error": str(e)}

            results.append({"tool": step.tool, "args": args, "result": tool_result, "parsed_data": parsed_data})

            # Send step result
            await websocket.send_json({
                "type": "step_result",
                "index": i,
                "tool": step.tool,
                "args": args,
                "result": tool_result,
            })

            # Small delay for visual effect
            await asyncio.sleep(0.4)

        # Build and send summary
        summary = build_summary(scenario, results)

        await websocket.send_json({
            "type": "complete",
            "summary": summary,
        })

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({
                "type": "error",
                "message": str(e),
            })
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


@router.get("/api/playground-examples")
async def playground_examples() -> dict:
    """Get example queries for the playground."""
    return {"examples": EXAMPLE_QUERIES}


def get_static_files() -> StaticFiles:
    """Return StaticFiles instance for mounting."""
    return StaticFiles(directory=str(STATIC_DIR))
