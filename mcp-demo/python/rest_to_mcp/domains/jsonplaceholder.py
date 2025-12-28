"""
JSONPlaceholder API Domain

Endpoints for the JSONPlaceholder fake REST API.
https://jsonplaceholder.typicode.com

This domain provides:
- Posts CRUD operations
- Comments retrieval
- Users retrieval
"""

from __future__ import annotations

from ..endpoints import HttpMethod, RestEndpoint


JSONPLACEHOLDER_ENDPOINTS: list[RestEndpoint] = [
    RestEndpoint(
        name="get_posts",
        path="/posts",
        method=HttpMethod.GET,
        description="Get all posts. Optionally filter by userId.",
        query_params=["userId"],
    ),
    RestEndpoint(
        name="get_post",
        path="/posts/{id}",
        method=HttpMethod.GET,
        description="Get a specific post by ID.",
        path_params=["id"],
    ),
    RestEndpoint(
        name="create_post",
        path="/posts",
        method=HttpMethod.POST,
        description="Create a new post with title, body, and userId.",
        body_params=["title", "body", "userId"],
    ),
    RestEndpoint(
        name="update_post",
        path="/posts/{id}",
        method=HttpMethod.PUT,
        description="Update an existing post.",
        path_params=["id"],
        body_params=["title", "body", "userId"],
    ),
    RestEndpoint(
        name="delete_post",
        path="/posts/{id}",
        method=HttpMethod.DELETE,
        description="Delete a post by ID.",
        path_params=["id"],
    ),
    RestEndpoint(
        name="get_comments",
        path="/posts/{postId}/comments",
        method=HttpMethod.GET,
        description="Get all comments for a specific post.",
        path_params=["postId"],
    ),
    RestEndpoint(
        name="get_users",
        path="/users",
        method=HttpMethod.GET,
        description="Get all users.",
    ),
    RestEndpoint(
        name="get_user",
        path="/users/{id}",
        method=HttpMethod.GET,
        description="Get a specific user by ID.",
        path_params=["id"],
    ),
]
