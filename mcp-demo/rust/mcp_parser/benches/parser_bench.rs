//! Benchmarks for MCP parser
//!
//! Run with: cargo bench

use criterion::{black_box, criterion_group, criterion_main, Criterion, Throughput};
use mcp_parser::{parse_request_impl, parse_response_impl, is_valid_jsonrpc};

const SIMPLE_REQUEST: &str = r#"{"jsonrpc":"2.0","id":1,"method":"tools/list"}"#;

const COMPLEX_REQUEST: &str = r#"{
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
                "tags": ["rust", "python", "mcp"]
            }
        }
    }
}"#;

const SIMPLE_RESPONSE: &str = r#"{"jsonrpc":"2.0","id":1,"result":{"status":"ok"}}"#;

fn bench_parse_simple_request(c: &mut Criterion) {
    let mut group = c.benchmark_group("parse_request");
    group.throughput(Throughput::Bytes(SIMPLE_REQUEST.len() as u64));
    
    group.bench_function("simple", |b| {
        b.iter(|| parse_request_impl(black_box(SIMPLE_REQUEST)))
    });
    
    group.finish();
}

fn bench_parse_complex_request(c: &mut Criterion) {
    let mut group = c.benchmark_group("parse_request");
    group.throughput(Throughput::Bytes(COMPLEX_REQUEST.len() as u64));
    
    group.bench_function("complex", |b| {
        b.iter(|| parse_request_impl(black_box(COMPLEX_REQUEST)))
    });
    
    group.finish();
}

fn bench_parse_response(c: &mut Criterion) {
    let mut group = c.benchmark_group("parse_response");
    group.throughput(Throughput::Bytes(SIMPLE_RESPONSE.len() as u64));
    
    group.bench_function("simple", |b| {
        b.iter(|| parse_response_impl(black_box(SIMPLE_RESPONSE)))
    });
    
    group.finish();
}

fn bench_validation(c: &mut Criterion) {
    let mut group = c.benchmark_group("validation");
    
    group.bench_function("is_valid_jsonrpc", |b| {
        b.iter(|| is_valid_jsonrpc(black_box(SIMPLE_REQUEST)))
    });
    
    group.finish();
}

fn bench_batch_parsing(c: &mut Criterion) {
    let requests: Vec<&str> = (0..100)
        .map(|_| SIMPLE_REQUEST)
        .collect();
    
    let mut group = c.benchmark_group("batch");
    group.throughput(Throughput::Elements(100));
    
    group.bench_function("parse_100_requests", |b| {
        b.iter(|| {
            for req in &requests {
                let _ = parse_request_impl(black_box(req));
            }
        })
    });
    
    group.finish();
}

criterion_group!(
    benches,
    bench_parse_simple_request,
    bench_parse_complex_request,
    bench_parse_response,
    bench_validation,
    bench_batch_parsing,
);
criterion_main!(benches);
