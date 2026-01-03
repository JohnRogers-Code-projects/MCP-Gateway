"""
Benchmark runner comparing Python vs Rust JSON-RPC parsing.

Methodology:
- Warm-up phase (discarded)
- Multiple iterations with time.perf_counter_ns()
- Statistical aggregation (mean, std, percentiles)
"""

from __future__ import annotations

import json
import statistics
import time
from dataclasses import dataclass, asdict
from typing import Any

from pydantic import ValidationError

from .models import JsonRpcRequest

# Try to import Rust parser, gracefully degrade if not built
try:
    import mcp_parser

    RUST_AVAILABLE = True
except ImportError:
    mcp_parser = None  # type: ignore[assignment]
    RUST_AVAILABLE = False


# Test payloads matching Rust benchmarks
PAYLOADS: dict[str, str] = {
    "simple": '{"jsonrpc":"2.0","id":1,"method":"tools/list"}',
    "complex": json.dumps(
        {
            "jsonrpc": "2.0",
            "id": "request-12345",
            "method": "tools/call",
            "params": {
                "name": "get_posts",
                "arguments": {
                    "userId": "1",
                    "limit": 10,
                    "filters": {
                        "status": "published",
                        "tags": ["rust", "python", "mcp"],
                    },
                },
            },
        }
    ),
}


@dataclass
class BenchmarkResult:
    """Statistics from a benchmark run."""

    parser: str  # "python" or "rust"
    payload_name: str
    payload_bytes: int
    iterations: int
    mean_ns: float
    std_ns: float
    min_ns: float
    max_ns: float
    p50_ns: float
    p95_ns: float
    p99_ns: float
    ops_per_sec: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _compute_stats(
    parser: str, payload_name: str, payload_bytes: int, iterations: int, timings: list[int]
) -> BenchmarkResult:
    """Compute statistics from timing data."""
    sorted_timings = sorted(timings)
    mean_ns = statistics.mean(timings)

    return BenchmarkResult(
        parser=parser,
        payload_name=payload_name,
        payload_bytes=payload_bytes,
        iterations=iterations,
        mean_ns=mean_ns,
        std_ns=statistics.stdev(timings) if len(timings) > 1 else 0,
        min_ns=sorted_timings[0],
        max_ns=sorted_timings[-1],
        p50_ns=sorted_timings[int(len(timings) * 0.50)],
        p95_ns=sorted_timings[int(len(timings) * 0.95)],
        p99_ns=sorted_timings[min(int(len(timings) * 0.99), len(timings) - 1)],
        ops_per_sec=1_000_000_000 / mean_ns if mean_ns > 0 else 0,
    )


def benchmark_python(
    payload: str, payload_name: str, iterations: int = 10000, warmup: int = 100
) -> BenchmarkResult:
    """
    Benchmark Python json.loads + Pydantic validation.

    This is what the current adapter uses for JSON-RPC parsing.
    """
    payload_bytes = len(payload.encode("utf-8"))

    # Warm-up phase
    for _ in range(warmup):
        data = json.loads(payload)
        _ = JsonRpcRequest(**data)

    # Timed iterations
    timings: list[int] = []
    for _ in range(iterations):
        start = time.perf_counter_ns()
        data = json.loads(payload)
        _ = JsonRpcRequest(**data)
        end = time.perf_counter_ns()
        timings.append(end - start)

    return _compute_stats("python", payload_name, payload_bytes, iterations, timings)


def benchmark_rust(
    payload: str, payload_name: str, iterations: int = 10000, warmup: int = 100
) -> BenchmarkResult:
    """
    Benchmark Rust mcp_parser.parse_request().

    Uses serde_json + custom validation, called via PyO3 bindings.
    """
    if not RUST_AVAILABLE:
        raise RuntimeError(
            "Rust parser not available. Install Rust and run: "
            "cd mcp-gateway/rust/mcp_parser && maturin develop --release"
        )

    payload_bytes = len(payload.encode("utf-8"))

    # Warm-up phase
    for _ in range(warmup):
        _ = mcp_parser.parse_request(payload)

    # Timed iterations
    timings: list[int] = []
    for _ in range(iterations):
        start = time.perf_counter_ns()
        _ = mcp_parser.parse_request(payload)
        end = time.perf_counter_ns()
        timings.append(end - start)

    return _compute_stats("rust", payload_name, payload_bytes, iterations, timings)


async def run_benchmark(
    payload_name: str = "simple", iterations: int = 10000
) -> dict[str, Any]:
    """
    Run benchmark comparison and return results.

    Returns dict with:
    - python: BenchmarkResult
    - rust: BenchmarkResult or None
    - rust_available: bool
    - speedup: float or None
    """
    payload = PAYLOADS.get(payload_name, PAYLOADS["simple"])

    # Always run Python benchmark
    python_result = benchmark_python(payload, payload_name, iterations)

    result: dict[str, Any] = {
        "python": python_result.to_dict(),
        "rust": None,
        "rust_available": RUST_AVAILABLE,
        "speedup": None,
    }

    # Run Rust benchmark if available
    if RUST_AVAILABLE:
        rust_result = benchmark_rust(payload, payload_name, iterations)
        result["rust"] = rust_result.to_dict()
        if python_result.ops_per_sec > 0:
            result["speedup"] = round(rust_result.ops_per_sec / python_result.ops_per_sec, 2)

    return result


def get_payload_info() -> list[dict[str, Any]]:
    """Get information about available test payloads."""
    return [
        {"name": name, "bytes": len(payload.encode("utf-8")), "preview": payload[:50] + "..."}
        for name, payload in PAYLOADS.items()
    ]
