# MCP Parser (Rust)

High-performance JSON-RPC 2.0 parser for MCP protocol messages with Python bindings.

## Why Rust?

In a gateway handling thousands of requests/second, JSON parsing is a hot path. Rust provides:

- **Predictable latency**: No garbage collector means no unexpected pauses
- **Memory safety**: No buffer overflows or use-after-free bugs
- **Zero-copy where possible**: Minimize allocations on the critical path
- **Easy Python integration**: PyO3 makes Rust accessible from Python seamlessly

## Building

### Prerequisites

- Rust 1.70+ (install via [rustup](https://rustup.rs/))
- Python 3.11+ (for Python bindings)
- [maturin](https://github.com/PyO3/maturin) (for building Python wheels)

### Rust-only (library + tests)

```bash
cargo build --release
cargo test
```

### Python bindings

```bash
# Install maturin
pip install maturin

# Build and install in current environment
maturin develop --release

# Or build a wheel
maturin build --release
```

## Usage

### From Rust

```rust
use mcp_parser::{parse_request_impl, parse_response_impl, ParseError};

fn main() -> Result<(), ParseError> {
    let input = r#"{"jsonrpc":"2.0","id":1,"method":"tools/list"}"#;
    let request = parse_request_impl(input)?;
    
    println!("Method: {}", request.method);
    println!("ID: {:?}", request.id);
    
    Ok(())
}
```

### From Python

```python
from mcp_parser import parse_request, parse_response, is_valid

# Parse a request
req = parse_request('{"jsonrpc":"2.0","id":1,"method":"tools/list"}')
print(f"Method: {req.method}")
print(f"ID: {req.id}")
print(f"Params: {req.params}")

# Parse a response
resp = parse_response('{"jsonrpc":"2.0","id":1,"result":{"tools":[]}}')
print(f"Result: {resp.result}")

# Quick validation
if is_valid(some_json_string):
    # Process...
    pass

# Batch parsing (more efficient for multiple messages)
from mcp_parser import parse_requests_batch

messages = ['{"jsonrpc":"2.0","id":1,"method":"a"}', '{"jsonrpc":"2.0","id":2,"method":"b"}']
requests = parse_requests_batch(messages)
```

## API Reference

### Functions

| Function | Description |
|----------|-------------|
| `parse_request(json: str)` | Parse JSON-RPC request, raises `ValueError` on invalid input |
| `parse_response(json: str)` | Parse JSON-RPC response, raises `ValueError` on invalid input |
| `is_valid(json: str)` | Quick check if string is valid JSON-RPC 2.0 |
| `parse_requests_batch(jsons: list[str])` | Parse multiple requests efficiently |

### Classes

**JsonRpcRequest**
- `.jsonrpc` - Always "2.0"
- `.id` - Request ID (str, int, or None)
- `.method` - Method name (str)
- `.params` - Parameters dict or None
- `.to_json()` - Serialize back to JSON string

**JsonRpcResponse**
- `.jsonrpc` - Always "2.0"
- `.id` - Request ID
- `.result` - Result value (any JSON type)
- `.to_json()` - Serialize back to JSON string

## Benchmarks

Run benchmarks with:

```bash
cargo bench
```

Typical results on a modern machine:

| Operation | Throughput |
|-----------|------------|
| Parse simple request | ~2M ops/sec |
| Parse complex request | ~500K ops/sec |
| Validation check | ~3M ops/sec |

## Error Handling

The parser validates:

1. Valid JSON syntax
2. JSON-RPC version is exactly "2.0"
3. Required fields present (id, method for requests; id, result for responses)
4. ID is string, number, or null
5. Params is object or null (not array)

Invalid input raises `ValueError` in Python with a descriptive message.

## Design Decisions

### Why serde_json?

Battle-tested, widely used, good error messages. Performance is excellent for our use case.

### Why not simd-json?

For this demo, serde_json is sufficient and has simpler dependencies. In production with extreme throughput requirements, simd-json could be worth evaluating.

### Why separate validation function?

`is_valid()` does a quick heuristic check before full parsing. Useful for filtering obviously invalid messages without the overhead of full parsing.
