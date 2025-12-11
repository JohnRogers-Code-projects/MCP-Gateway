"""
Dashboard Routes

Provides the demo dashboard UI and supporting endpoints:
- Static file serving (CSS, JS)
- HTML template rendering
- WebSocket endpoint for streaming test output

Kept separate from server.py to isolate demo UI from core MCP logic.
In production, you'd likely disable this entirely or put it behind auth.
"""

import asyncio
import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

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

    # Find the python directory (where tests live)
    python_dir = BASE_DIR.parent

    try:
        # Run pytest with unbuffered output for real-time streaming
        # -v for verbose, --tb=short for concise tracebacks
        process = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "pytest",
            "-v", "--tb=short", "-x",  # -x stops on first failure for faster feedback
            cwd=str(python_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,  # Merge stderr into stdout
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


def get_static_files() -> StaticFiles:
    """Return StaticFiles instance for mounting."""
    return StaticFiles(directory=str(STATIC_DIR))
