"""
Integration tests for REST-to-MCP adapter.

These tests hit the actual JSONPlaceholder API to verify
end-to-end functionality. They're slower but catch real issues.

Run with: pytest tests/test_integration.py -v

Note: Tests marked with @pytest.mark.external require network access
to jsonplaceholder.typicode.com. They will be skipped if the network
is unavailable.
"""

import os

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from rest_to_mcp.adapter import create_jsonplaceholder_adapter
from rest_to_mcp.models import JsonRpcRequest
from rest_to_mcp.server import app, lifespan


# Check if external network is available
def _check_network():
    try:
        resp = httpx.get("https://jsonplaceholder.typicode.com/posts/1", timeout=5)
        return resp.status_code == 200
    except Exception:
        return False


NETWORK_AVAILABLE = _check_network()
skip_without_network = pytest.mark.skipif(
    not NETWORK_AVAILABLE,
    reason="External network access to jsonplaceholder.typicode.com unavailable"
)


# -----------------------------------------------------------------------------
# Direct Adapter Tests (hits real JSONPlaceholder API)
# -----------------------------------------------------------------------------


@skip_without_network
class TestAdapterIntegration:
    """Integration tests using the adapter directly. Requires network access."""

    @pytest.fixture
    async def adapter(self):
        adapter = create_jsonplaceholder_adapter()
        yield adapter
        await adapter.close()

    @pytest.mark.asyncio
    async def test_get_posts(self, adapter):
        """Verify we can fetch posts from JSONPlaceholder."""
        result = await adapter._call_tool("get_posts", {})
        
        assert not result.isError
        assert len(result.content) == 1
        # JSONPlaceholder returns 100 posts
        assert '"userId"' in result.content[0].text
        assert '"title"' in result.content[0].text

    @pytest.mark.asyncio
    async def test_get_single_post(self, adapter):
        """Verify we can fetch a specific post."""
        result = await adapter._call_tool("get_post", {"id": "1"})
        
        assert not result.isError
        text = result.content[0].text
        assert '"id": 1' in text

    @pytest.mark.asyncio
    async def test_get_posts_filtered_by_user(self, adapter):
        """Verify query parameter filtering works."""
        result = await adapter._call_tool("get_posts", {"userId": "1"})
        
        assert not result.isError
        # All returned posts should be from user 1
        text = result.content[0].text
        assert '"userId": 1' in text

    @pytest.mark.asyncio
    async def test_get_comments_for_post(self, adapter):
        """Verify nested resource access works."""
        result = await adapter._call_tool("get_comments", {"postId": "1"})
        
        assert not result.isError
        text = result.content[0].text
        assert '"postId": 1' in text
        assert '"email"' in text

    @pytest.mark.asyncio
    async def test_get_users(self, adapter):
        """Verify user list endpoint works."""
        result = await adapter._call_tool("get_users", {})
        
        assert not result.isError
        text = result.content[0].text
        assert '"username"' in text
        assert '"email"' in text

    @pytest.mark.asyncio
    async def test_create_post(self, adapter):
        """Verify POST requests work (JSONPlaceholder fakes creation)."""
        result = await adapter._call_tool(
            "create_post",
            {
                "title": "Test Post",
                "body": "This is a test",
                "userId": "1",
            },
        )
        
        assert not result.isError
        text = result.content[0].text
        # JSONPlaceholder returns the created post with id: 101
        assert '"id": 101' in text
        assert '"title": "Test Post"' in text

    @pytest.mark.asyncio
    async def test_update_post(self, adapter):
        """Verify PUT requests work."""
        result = await adapter._call_tool(
            "update_post",
            {
                "id": "1",
                "title": "Updated Title",
                "body": "Updated body",
                "userId": "1",
            },
        )
        
        assert not result.isError
        text = result.content[0].text
        assert '"title": "Updated Title"' in text

    @pytest.mark.asyncio
    async def test_delete_post(self, adapter):
        """Verify DELETE requests work."""
        result = await adapter._call_tool("delete_post", {"id": "1"})
        
        # JSONPlaceholder returns empty object for deletes
        assert not result.isError


# -----------------------------------------------------------------------------
# Server Integration Tests
# -----------------------------------------------------------------------------


class TestServerIntegration:
    """Integration tests for the FastAPI server."""

    @pytest.fixture
    async def client(self):
        """Create test client for the FastAPI app with proper lifespan."""
        async with lifespan(app):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                yield client

    @pytest.mark.asyncio
    async def test_health_endpoint(self, client):
        """Verify health check works."""
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}

    @pytest.mark.asyncio
    async def test_mcp_initialize(self, client):
        """Verify MCP initialize method."""
        response = await client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize"},
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 1
        assert "protocolVersion" in data["result"]

    @pytest.mark.asyncio
    async def test_mcp_tools_list(self, client):
        """Verify MCP tools/list method."""
        response = await client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        )
        
        assert response.status_code == 200
        data = response.json()
        # 8 JSONPlaceholder + 2 Open-Meteo weather tools
        assert len(data["result"]["tools"]) == 10

    @skip_without_network
    @pytest.mark.asyncio
    async def test_mcp_tools_call(self, client):
        """Verify MCP tools/call method hits the real API."""
        response = await client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "get_post", "arguments": {"id": "1"}},
            },
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "content" in data["result"]
        assert '"id": 1' in data["result"]["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_mcp_invalid_json(self, client):
        """Verify graceful handling of invalid JSON."""
        response = await client.post(
            "/mcp",
            content="not valid json",
            headers={"Content-Type": "application/json"},
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == -32700  # PARSE_ERROR

    @pytest.mark.asyncio
    async def test_mcp_invalid_request(self, client):
        """Verify graceful handling of invalid JSON-RPC."""
        response = await client.post(
            "/mcp",
            json={"invalid": "request"},
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == -32600  # INVALID_REQUEST

    @pytest.mark.asyncio
    async def test_mcp_unknown_method(self, client):
        """Verify unknown method error."""
        response = await client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 4, "method": "unknown/method"},
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == -32601  # METHOD_NOT_FOUND
