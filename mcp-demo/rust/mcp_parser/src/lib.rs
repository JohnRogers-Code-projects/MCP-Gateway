//! MCP JSON-RPC Parser
//!
//! High-performance parser for MCP protocol messages. Provides:
//! - Zero-copy parsing where possible
//! - Strict JSON-RPC 2.0 validation
//! - Python bindings via PyO3
//!
//! # Why Rust?
//!
//! In a gateway like ContextForge handling thousands of requests/second,
//! JSON parsing is a hot path. Rust provides:
//! - Predictable latency (no GC pauses)
//! - Memory safety without runtime overhead
//! - Easy integration with Python via PyO3
//!
//! # Usage from Python
//!
//! ```python
//! from mcp_parser import parse_request, parse_response, ParseError
//!
//! # Parse a request
//! req = parse_request('{"jsonrpc":"2.0","id":1,"method":"tools/list"}')
//! print(req.method)  # "tools/list"
//!
//! # Parse with validation
//! try:
//!     parse_request('{"invalid": "json-rpc"}')
//! except ParseError as e:
//!     print(e)  # Missing required field: method
//! ```

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::HashMap;
use thiserror::Error;

// -----------------------------------------------------------------------------
// Error Types
// -----------------------------------------------------------------------------

/// Errors that can occur during parsing
#[derive(Error, Debug)]
pub enum ParseError {
    #[error("Invalid JSON: {0}")]
    InvalidJson(String),

    #[error("Invalid JSON-RPC version: expected '2.0', got '{0}'")]
    InvalidVersion(String),

    #[error("Missing required field: {0}")]
    MissingField(&'static str),

    #[error("Invalid field type for '{0}': expected {1}")]
    InvalidFieldType(&'static str, &'static str),

    #[error("Invalid request ID: must be string, number, or null")]
    InvalidId,
}

impl From<ParseError> for PyErr {
    fn from(err: ParseError) -> PyErr {
        PyValueError::new_err(err.to_string())
    }
}

// -----------------------------------------------------------------------------
// Core Data Structures
// -----------------------------------------------------------------------------

/// Parsed JSON-RPC request
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct JsonRpcRequest {
    pub jsonrpc: String,
    pub id: RequestId,
    pub method: String,
    pub params: Option<HashMap<String, Value>>,
}

/// Request ID can be string, number, or null
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(untagged)]
pub enum RequestId {
    String(String),
    Number(i64),
    Null,
}

/// Parsed JSON-RPC response (success case)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct JsonRpcResponse {
    pub jsonrpc: String,
    pub id: RequestId,
    pub result: Value,
}

/// Parsed JSON-RPC error response
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct JsonRpcError {
    pub jsonrpc: String,
    pub id: RequestId,
    pub error: ErrorData,
}

/// Error data structure
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ErrorData {
    pub code: i32,
    pub message: String,
    pub data: Option<Value>,
}

// -----------------------------------------------------------------------------
// Parsing Functions
// -----------------------------------------------------------------------------

/// Parse a JSON-RPC request with validation
pub fn parse_request_impl(input: &str) -> Result<JsonRpcRequest, ParseError> {
    // Parse JSON
    let value: Value = serde_json::from_str(input)
        .map_err(|e| ParseError::InvalidJson(e.to_string()))?;

    let obj = value.as_object().ok_or(ParseError::InvalidJson(
        "Expected JSON object".to_string(),
    ))?;

    // Validate jsonrpc version
    let version = obj
        .get("jsonrpc")
        .and_then(|v| v.as_str())
        .ok_or(ParseError::MissingField("jsonrpc"))?;

    if version != "2.0" {
        return Err(ParseError::InvalidVersion(version.to_string()));
    }

    // Parse ID (required for requests)
    let id = parse_id(obj.get("id").ok_or(ParseError::MissingField("id"))?)?;

    // Parse method (required)
    let method = obj
        .get("method")
        .and_then(|v| v.as_str())
        .ok_or(ParseError::MissingField("method"))?
        .to_string();

    // Parse params (optional)
    let params = match obj.get("params") {
        Some(Value::Object(map)) => {
            let mut result = HashMap::new();
            for (k, v) in map {
                result.insert(k.clone(), v.clone());
            }
            Some(result)
        }
        Some(Value::Null) | None => None,
        Some(_) => return Err(ParseError::InvalidFieldType("params", "object or null")),
    };

    Ok(JsonRpcRequest {
        jsonrpc: "2.0".to_string(),
        id,
        method,
        params,
    })
}

/// Parse a JSON-RPC response
pub fn parse_response_impl(input: &str) -> Result<JsonRpcResponse, ParseError> {
    let value: Value = serde_json::from_str(input)
        .map_err(|e| ParseError::InvalidJson(e.to_string()))?;

    let obj = value.as_object().ok_or(ParseError::InvalidJson(
        "Expected JSON object".to_string(),
    ))?;

    // Validate jsonrpc version
    let version = obj
        .get("jsonrpc")
        .and_then(|v| v.as_str())
        .ok_or(ParseError::MissingField("jsonrpc"))?;

    if version != "2.0" {
        return Err(ParseError::InvalidVersion(version.to_string()));
    }

    // Parse ID
    let id = match obj.get("id") {
        Some(v) => parse_id(v)?,
        None => RequestId::Null,
    };

    // Parse result
    let result = obj
        .get("result")
        .cloned()
        .ok_or(ParseError::MissingField("result"))?;

    Ok(JsonRpcResponse {
        jsonrpc: "2.0".to_string(),
        id,
        result,
    })
}

/// Parse request ID from JSON value
fn parse_id(value: &Value) -> Result<RequestId, ParseError> {
    match value {
        Value::String(s) => Ok(RequestId::String(s.clone())),
        Value::Number(n) => n
            .as_i64()
            .map(RequestId::Number)
            .ok_or(ParseError::InvalidId),
        Value::Null => Ok(RequestId::Null),
        _ => Err(ParseError::InvalidId),
    }
}

/// Validate that a string is valid JSON-RPC (quick check without full parse)
pub fn is_valid_jsonrpc(input: &str) -> bool {
    // Quick heuristic check before full parse
    if !input.contains("\"jsonrpc\"") || !input.contains("\"2.0\"") {
        return false;
    }
    
    // Attempt full parse
    serde_json::from_str::<Value>(input)
        .map(|v| {
            v.get("jsonrpc")
                .and_then(|v| v.as_str())
                .map(|s| s == "2.0")
                .unwrap_or(false)
        })
        .unwrap_or(false)
}

// -----------------------------------------------------------------------------
// Python Bindings
// -----------------------------------------------------------------------------

/// Python wrapper for JsonRpcRequest
#[pyclass(name = "JsonRpcRequest")]
#[derive(Clone)]
pub struct PyJsonRpcRequest {
    inner: JsonRpcRequest,
}

#[pymethods]
impl PyJsonRpcRequest {
    /// The JSON-RPC version (always "2.0")
    #[getter]
    fn jsonrpc(&self) -> &str {
        &self.inner.jsonrpc
    }

    /// The request ID (string or int)
    #[getter]
    fn id(&self) -> PyObject {
        Python::with_gil(|py| match &self.inner.id {
            RequestId::String(s) => s.into_py(py),
            RequestId::Number(n) => n.into_py(py),
            RequestId::Null => py.None(),
        })
    }

    /// The method name being called
    #[getter]
    fn method(&self) -> &str {
        &self.inner.method
    }

    /// The request parameters (if any)
    #[getter]
    fn params(&self) -> PyObject {
        Python::with_gil(|py| {
            match &self.inner.params {
                Some(map) => {
                    // Convert to Python dict
                    let dict = pyo3::types::PyDict::new(py);
                    for (k, v) in map {
                        let py_value = json_value_to_py(py, v);
                        dict.set_item(k, py_value).unwrap();
                    }
                    dict.into_py(py)
                }
                None => py.None(),
            }
        })
    }

    /// Convert to JSON string
    fn to_json(&self) -> PyResult<String> {
        serde_json::to_string(&self.inner)
            .map_err(|e| PyValueError::new_err(e.to_string()))
    }

    fn __repr__(&self) -> String {
        format!(
            "JsonRpcRequest(id={:?}, method={:?})",
            self.inner.id, self.inner.method
        )
    }
}

/// Python wrapper for JsonRpcResponse
#[pyclass(name = "JsonRpcResponse")]
#[derive(Clone)]
pub struct PyJsonRpcResponse {
    inner: JsonRpcResponse,
}

#[pymethods]
impl PyJsonRpcResponse {
    #[getter]
    fn jsonrpc(&self) -> &str {
        &self.inner.jsonrpc
    }

    #[getter]
    fn id(&self) -> PyObject {
        Python::with_gil(|py| match &self.inner.id {
            RequestId::String(s) => s.into_py(py),
            RequestId::Number(n) => n.into_py(py),
            RequestId::Null => py.None(),
        })
    }

    #[getter]
    fn result(&self) -> PyObject {
        Python::with_gil(|py| json_value_to_py(py, &self.inner.result))
    }

    fn to_json(&self) -> PyResult<String> {
        serde_json::to_string(&self.inner)
            .map_err(|e| PyValueError::new_err(e.to_string()))
    }

    fn __repr__(&self) -> String {
        format!("JsonRpcResponse(id={:?})", self.inner.id)
    }
}

/// Convert serde_json Value to Python object
fn json_value_to_py(py: Python<'_>, value: &Value) -> PyObject {
    match value {
        Value::Null => py.None(),
        Value::Bool(b) => b.into_py(py),
        Value::Number(n) => {
            if let Some(i) = n.as_i64() {
                i.into_py(py)
            } else if let Some(f) = n.as_f64() {
                f.into_py(py)
            } else {
                py.None()
            }
        }
        Value::String(s) => s.into_py(py),
        Value::Array(arr) => {
            let list: Vec<PyObject> = arr.iter().map(|v| json_value_to_py(py, v)).collect();
            list.into_py(py)
        }
        Value::Object(map) => {
            let dict = pyo3::types::PyDict::new(py);
            for (k, v) in map {
                dict.set_item(k, json_value_to_py(py, v)).unwrap();
            }
            dict.into_py(py)
        }
    }
}

// -----------------------------------------------------------------------------
// Python Module Functions
// -----------------------------------------------------------------------------

/// Parse a JSON-RPC request string into a structured object
#[pyfunction]
fn parse_request(input: &str) -> PyResult<PyJsonRpcRequest> {
    let inner = parse_request_impl(input)?;
    Ok(PyJsonRpcRequest { inner })
}

/// Parse a JSON-RPC response string into a structured object
#[pyfunction]
fn parse_response(input: &str) -> PyResult<PyJsonRpcResponse> {
    let inner = parse_response_impl(input)?;
    Ok(PyJsonRpcResponse { inner })
}

/// Check if a string is valid JSON-RPC 2.0 (quick validation)
#[pyfunction]
fn is_valid(input: &str) -> bool {
    is_valid_jsonrpc(input)
}

/// Batch parse multiple requests (more efficient than parsing one at a time)
#[pyfunction]
fn parse_requests_batch(inputs: Vec<&str>) -> PyResult<Vec<PyJsonRpcRequest>> {
    inputs
        .into_iter()
        .map(|input| {
            let inner = parse_request_impl(input)?;
            Ok(PyJsonRpcRequest { inner })
        })
        .collect()
}

/// Python module definition
#[pymodule]
fn mcp_parser(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(parse_request, m)?)?;
    m.add_function(wrap_pyfunction!(parse_response, m)?)?;
    m.add_function(wrap_pyfunction!(is_valid, m)?)?;
    m.add_function(wrap_pyfunction!(parse_requests_batch, m)?)?;
    m.add_class::<PyJsonRpcRequest>()?;
    m.add_class::<PyJsonRpcResponse>()?;
    Ok(())
}

// -----------------------------------------------------------------------------
// Rust Tests
// -----------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_valid_request() {
        let input = r#"{"jsonrpc":"2.0","id":1,"method":"tools/list"}"#;
        let req = parse_request_impl(input).unwrap();
        
        assert_eq!(req.jsonrpc, "2.0");
        assert_eq!(req.id, RequestId::Number(1));
        assert_eq!(req.method, "tools/list");
        assert!(req.params.is_none());
    }

    #[test]
    fn test_parse_request_with_params() {
        let input = r#"{"jsonrpc":"2.0","id":"abc","method":"tools/call","params":{"name":"get_posts"}}"#;
        let req = parse_request_impl(input).unwrap();
        
        assert_eq!(req.id, RequestId::String("abc".to_string()));
        assert_eq!(req.method, "tools/call");
        
        let params = req.params.unwrap();
        assert_eq!(
            params.get("name").unwrap(),
            &Value::String("get_posts".to_string())
        );
    }

    #[test]
    fn test_parse_request_string_id() {
        let input = r#"{"jsonrpc":"2.0","id":"request-123","method":"initialize"}"#;
        let req = parse_request_impl(input).unwrap();
        
        assert_eq!(req.id, RequestId::String("request-123".to_string()));
    }

    #[test]
    fn test_parse_invalid_json() {
        let input = "not valid json";
        let err = parse_request_impl(input).unwrap_err();
        
        assert!(matches!(err, ParseError::InvalidJson(_)));
    }

    #[test]
    fn test_parse_wrong_version() {
        let input = r#"{"jsonrpc":"1.0","id":1,"method":"test"}"#;
        let err = parse_request_impl(input).unwrap_err();
        
        assert!(matches!(err, ParseError::InvalidVersion(_)));
    }

    #[test]
    fn test_parse_missing_method() {
        let input = r#"{"jsonrpc":"2.0","id":1}"#;
        let err = parse_request_impl(input).unwrap_err();
        
        assert!(matches!(err, ParseError::MissingField("method")));
    }

    #[test]
    fn test_parse_missing_id() {
        let input = r#"{"jsonrpc":"2.0","method":"test"}"#;
        let err = parse_request_impl(input).unwrap_err();
        
        assert!(matches!(err, ParseError::MissingField("id")));
    }

    #[test]
    fn test_parse_response() {
        let input = r#"{"jsonrpc":"2.0","id":1,"result":{"tools":[]}}"#;
        let resp = parse_response_impl(input).unwrap();
        
        assert_eq!(resp.jsonrpc, "2.0");
        assert_eq!(resp.id, RequestId::Number(1));
        assert!(resp.result.is_object());
    }

    #[test]
    fn test_is_valid_jsonrpc() {
        assert!(is_valid_jsonrpc(r#"{"jsonrpc":"2.0","id":1,"method":"test"}"#));
        assert!(!is_valid_jsonrpc(r#"{"jsonrpc":"1.0","id":1,"method":"test"}"#));
        assert!(!is_valid_jsonrpc("not json"));
        assert!(!is_valid_jsonrpc(r#"{"id":1,"method":"test"}"#));
    }

    #[test]
    fn test_parse_nested_params() {
        let input = r#"{
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "test",
                "arguments": {
                    "nested": {"deep": "value"},
                    "array": [1, 2, 3]
                }
            }
        }"#;
        
        let req = parse_request_impl(input).unwrap();
        let params = req.params.unwrap();
        let args = params.get("arguments").unwrap();
        
        assert!(args.is_object());
    }

    #[test]
    fn test_null_id() {
        let input = r#"{"jsonrpc":"2.0","id":null,"method":"notify"}"#;
        let req = parse_request_impl(input).unwrap();
        
        assert_eq!(req.id, RequestId::Null);
    }
}
