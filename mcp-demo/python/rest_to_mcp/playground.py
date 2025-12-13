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
    # Cross-API scenario: JSONPlaceholder + Open-Meteo
    # NOTE: Must be before user_profile to avoid "user N" matching first
    Scenario(
        id="user_weather",
        patterns=[
            r"(?:get|check|show)\s+(?:the\s+)?(?:weather|location)\s+(?:for|of)\s+user\s*(\d+)",
            r"(?:what(?:'s|\s+is)\s+the\s+)?weather\s+(?:at|for|where)\s+user\s*(\d+)",
            r"user\s*(\d+)(?:'s)?\s+(?:weather|location)",
            r"weather\s+(?:there\s+)?(?:for\s+)?user\s*(\d+)",
        ],
        description="Get user location and check the weather there (cross-API)",
        steps=[
            ScenarioStep(
                tool="get_user",
                args_template={"id": "$1"},
                label="Looking up user location",
            ),
            ScenarioStep(
                tool="get_weather",
                args_template={
                    "latitude": "$result.0.address.geo.lat",
                    "longitude": "$result.0.address.geo.lng",
                    "current_weather": "true",
                },
                label="Fetching weather at user's location",
            ),
        ],
        summary_template="Weather for {user_name}: {weather_temp}°C, {weather_condition}",
    ),
    Scenario(
        id="user_profile",
        patterns=[
            r"(?:get|show|fetch)\s+user\s*(\d+)\s*(?:profile)?$",
            r"user\s*(\d+)\s+(?:info|details|profile)$",
            r"(?:who\s+is\s+)?user\s*(\d+)$",
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
        summary_template="Found {tool_count} available tools:\n\n{tool_list}",
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


def extract_nested_value(data: Any, path: str) -> Any:
    """
    Extract a nested value from data using dot notation.

    Example: extract_nested_value(user, "address.geo.lat") -> "-68.6102"
    """
    parts = path.split(".")
    current = data
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit():
            idx = int(part)
            current = current[idx] if idx < len(current) else None
        else:
            return None
        if current is None:
            return None
    return current


def substitute_args(
    args_template: dict[str, str],
    captures: list[str],
    previous_results: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Replace template variables in args with actual values.

    Supports:
    - $1, $2, etc. - Regex capture groups
    - $result.N.path.to.value - Extract from Nth previous result (0-indexed)

    Args:
        args_template: Dictionary with template values
        captures: List of regex capture groups
        previous_results: List of results from previous steps (for cross-step data flow)

    Returns:
        Dictionary with substituted values
    """
    result: dict[str, Any] = {}
    previous_results = previous_results or []

    for key, value in args_template.items():
        if isinstance(value, str) and value.startswith("$"):
            # Handle result extraction: $result.0.address.geo.lat
            if value.startswith("$result."):
                path = value[8:]  # Remove "$result."
                parts = path.split(".", 1)
                if len(parts) >= 1 and parts[0].isdigit():
                    result_idx = int(parts[0])
                    if result_idx < len(previous_results):
                        result_data = previous_results[result_idx].get("parsed_data", {})
                        if len(parts) > 1:
                            result[key] = extract_nested_value(result_data, parts[1])
                        else:
                            result[key] = result_data
                    else:
                        result[key] = value  # Keep template if result not available
                else:
                    result[key] = value
            # Handle regex capture: $1, $2, etc.
            else:
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
    errors: list[str] = []

    for result in results:
        tool = result.get("tool", "")
        content = result.get("result", {})

        # Check for explicit errors in the result
        if isinstance(content, dict) and content.get("isError"):
            error_content = content.get("content", [{}])
            if error_content and isinstance(error_content[0], dict):
                error_text = error_content[0].get("text", "Unknown error")
                errors.append(f"{tool}: {error_text}")
            continue

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
            user_name = data.get("name")
            user_id = data.get("id")
            if not user_name or not user_id:
                # User not found - JSONPlaceholder returns empty {} for invalid IDs
                # Try to get the requested ID from the step args
                step_args = result.get("args", {})
                requested_id = step_args.get("id", "unknown")
                errors.append(
                    f"User {requested_id} does not exist in the database. "
                    f"JSONPlaceholder only has users 1-10. "
                    f"Try a valid user ID like 1, 2, or 3."
                )
                values["user_name"] = "Unknown"
            else:
                values["user_name"] = user_name
            values["user_email"] = data.get("email", "")

        elif tool == "get_post" and isinstance(data, dict):
            values["post_id"] = str(data.get("id", ""))
            values["post_title"] = data.get("title", "")[:50]

        elif tool == "get_posts" and isinstance(data, list):
            values["post_count"] = str(len(data))

        elif tool == "get_comments" and isinstance(data, list):
            values["comment_count"] = str(len(data))

        elif tool == "__tools_list__":
            # Handle tools/list response - build a human-readable list
            if isinstance(data, dict) and "tools" in data:
                tools = data["tools"]
                values["tool_count"] = str(len(tools))
                # Build formatted tool list
                tool_lines = []
                for t in tools:
                    name = t.get("name", "unknown")
                    desc = t.get("description", "No description")
                    # Truncate long descriptions
                    if len(desc) > 60:
                        desc = desc[:57] + "..."
                    tool_lines.append(f"  • {name}: {desc}")
                values["tool_list"] = "\n".join(tool_lines)
            else:
                values["tool_count"] = "multiple"
                values["tool_list"] = "  (unable to parse tool list)"

        elif tool == "get_weather" and isinstance(data, dict):
            # Handle Open-Meteo weather response
            current = data.get("current_weather", {})
            if current:
                values["weather_temp"] = str(current.get("temperature", "N/A"))
                # Map WMO weather codes to descriptions
                code = current.get("weathercode", 0)
                conditions = {
                    0: "Clear sky",
                    1: "Mainly clear",
                    2: "Partly cloudy",
                    3: "Overcast",
                    45: "Fog",
                    48: "Depositing rime fog",
                    51: "Light drizzle",
                    53: "Moderate drizzle",
                    55: "Dense drizzle",
                    61: "Slight rain",
                    63: "Moderate rain",
                    65: "Heavy rain",
                    71: "Slight snow",
                    73: "Moderate snow",
                    75: "Heavy snow",
                    80: "Slight showers",
                    81: "Moderate showers",
                    82: "Violent showers",
                    95: "Thunderstorm",
                }
                values["weather_condition"] = conditions.get(code, f"Code {code}")
                values["weather_wind"] = str(current.get("windspeed", "N/A"))

    # If there were errors, return a helpful error message
    if errors:
        error_msg = "⚠️ Request could not be completed:\n\n"
        for err in errors:
            error_msg += f"  • {err}\n"
        error_msg += "\nThis demonstrates graceful error handling. "
        error_msg += "In a real system, the agent would retry or ask for clarification."
        return error_msg

    # Substitute values into template
    try:
        return template.format(**values)
    except KeyError:
        # Fallback if template variables missing
        return f"Completed {scenario.description}"


# Example queries for the UI
EXAMPLE_QUERIES = [
    "Check weather for user 3",      # Cross-API: JSONPlaceholder → Open-Meteo
    "Get all posts by user 1",       # Multi-step: user lookup + posts
    "Show post 5 with comments",     # Multi-step: post + comments
    "List available tools",          # Tool discovery
    "Get weather for user 999",      # Error handling demo (user doesn't exist)
]
