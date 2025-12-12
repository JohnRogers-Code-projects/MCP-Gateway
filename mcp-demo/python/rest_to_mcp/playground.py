"""
Agent Playground - Simulated multi-tool orchestration.

Demonstrates how an LLM agent would chain multiple MCP tool calls
to answer complex queries, without requiring actual LLM inference.
Uses pattern matching to map natural language to predefined scenarios.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass
class ScenarioStep:
    """A single step in a scenario execution."""

    tool: str
    args_template: dict[str, str]
    label: str


@dataclass
class Scenario:
    """A predefined multi-tool workflow."""

    id: str
    patterns: list[str]
    description: str
    steps: list[ScenarioStep]
    summary_template: str


# Pre-defined scenarios demonstrating multi-tool orchestration
SCENARIOS: list[Scenario] = [
    Scenario(
        id="user_posts",
        patterns=[
            r"(?:get|show|fetch|list)\s+(?:all\s+)?posts\s+(?:by|from|for)\s+user\s*(\d+)",
            r"user\s*(\d+)(?:'s)?\s+posts",
            r"posts\s+(?:of|from)\s+user\s*(\d+)",
        ],
        description="Get all posts by a specific user",
        steps=[
            ScenarioStep(
                tool="get_user",
                args_template={"id": "$1"},
                label="Looking up user profile",
            ),
            ScenarioStep(
                tool="get_posts",
                args_template={"userId": "$1"},
                label="Fetching user's posts",
            ),
        ],
        summary_template="Found posts by user {user_name}",
    ),
    Scenario(
        id="post_with_comments",
        patterns=[
            r"(?:get|show)\s+post\s*(\d+)\s+(?:with|and)\s+(?:its\s+)?comments",
            r"post\s*(\d+)\s+(?:and\s+)?comments",
            r"comments\s+(?:on|for)\s+post\s*(\d+)",
        ],
        description="Get a post with its comments",
        steps=[
            ScenarioStep(
                tool="get_post",
                args_template={"id": "$1"},
                label="Fetching post details",
            ),
            ScenarioStep(
                tool="get_comments",
                args_template={"postId": "$1"},
                label="Loading comments",
            ),
        ],
        summary_template="Retrieved post with {comment_count} comments",
    ),
    Scenario(
        id="user_profile",
        patterns=[
            r"(?:get|show|fetch)\s+user\s*(\d+)\s*(?:profile)?",
            r"user\s*(\d+)\s+(?:info|details|profile)",
            r"(?:who\s+is\s+)?user\s*(\d+)",
        ],
        description="Get user profile details",
        steps=[
            ScenarioStep(
                tool="get_user",
                args_template={"id": "$1"},
                label="Fetching user profile",
            ),
        ],
        summary_template="Retrieved profile for {user_name}",
    ),
    Scenario(
        id="list_tools",
        patterns=[
            r"(?:what|which)\s+tools\s+(?:are\s+)?(?:available|do you have)",
            r"list\s+(?:all\s+)?(?:available\s+)?tools",
            r"available\s+tools",
            r"show\s+(?:me\s+)?(?:the\s+)?tools",
        ],
        description="List all available MCP tools",
        steps=[
            ScenarioStep(
                tool="__tools_list__",  # Special marker for tools/list
                args_template={},
                label="Discovering available tools",
            ),
        ],
        summary_template="Found {tool_count} available tools",
    ),
    Scenario(
        id="single_post",
        patterns=[
            r"(?:get|show|fetch)\s+post\s*(\d+)",
            r"post\s*(?:number\s*)?(\d+)",
        ],
        description="Get a single post by ID",
        steps=[
            ScenarioStep(
                tool="get_post",
                args_template={"id": "$1"},
                label="Fetching post",
            ),
        ],
        summary_template="Retrieved post #{post_id}",
    ),
]


def match_scenario(user_input: str) -> tuple[Scenario | None, list[str]]:
    """
    Match user input to a scenario using regex patterns.

    Returns:
        Tuple of (matched scenario or None, list of captured groups)
    """
    normalized = user_input.lower().strip()

    for scenario in SCENARIOS:
        for pattern in scenario.patterns:
            match = re.search(pattern, normalized, re.IGNORECASE)
            if match:
                captures = list(match.groups())
                return scenario, captures

    return None, []


def substitute_args(args_template: dict[str, str], captures: list[str]) -> dict[str, Any]:
    """
    Replace $1, $2, etc. in args template with captured values.

    Args:
        args_template: Dictionary with values like "$1", "$2"
        captures: List of regex capture groups

    Returns:
        Dictionary with substituted values
    """
    result: dict[str, Any] = {}
    for key, value in args_template.items():
        if isinstance(value, str) and value.startswith("$"):
            try:
                idx = int(value[1:]) - 1
                result[key] = captures[idx] if idx < len(captures) else value
            except (ValueError, IndexError):
                result[key] = value
        else:
            result[key] = value
    return result


def build_summary(scenario: Scenario, results: list[dict[str, Any]]) -> str:
    """
    Build a summary message from scenario results.

    Args:
        scenario: The executed scenario
        results: List of tool results

    Returns:
        Human-readable summary string
    """
    template = scenario.summary_template

    # Extract useful values from results
    values: dict[str, str] = {}

    for result in results:
        tool = result.get("tool", "")
        content = result.get("result", {})

        # Handle different content structures
        if isinstance(content, dict):
            # Direct content (when result is already parsed)
            if "content" in content:
                content_list = content.get("content", [])
                if content_list and isinstance(content_list[0], dict):
                    text = content_list[0].get("text", "")
                    try:
                        import json
                        data = json.loads(text)
                    except (json.JSONDecodeError, TypeError):
                        data = {}
                else:
                    data = {}
            else:
                data = content
        else:
            data = {}

        # Extract values based on tool type
        if tool == "get_user" and isinstance(data, dict):
            values["user_name"] = data.get("name", "Unknown User")
            values["user_email"] = data.get("email", "")

        elif tool == "get_post" and isinstance(data, dict):
            values["post_id"] = str(data.get("id", ""))
            values["post_title"] = data.get("title", "")[:50]

        elif tool == "get_posts" and isinstance(data, list):
            values["post_count"] = str(len(data))

        elif tool == "get_comments" and isinstance(data, list):
            values["comment_count"] = str(len(data))

        elif tool == "__tools_list__":
            # Handle tools/list response
            if isinstance(data, dict) and "tools" in data:
                values["tool_count"] = str(len(data["tools"]))
            else:
                values["tool_count"] = "multiple"

    # Substitute values into template
    try:
        return template.format(**values)
    except KeyError:
        # Fallback if template variables missing
        return f"Completed {scenario.description}"


# Example queries for the UI
EXAMPLE_QUERIES = [
    "Get all posts by user 1",
    "Show post 5 with comments",
    "Get user 2 profile",
    "List available tools",
]
