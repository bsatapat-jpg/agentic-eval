"""Adapter for converting OpenAI Agents SDK traces to agentic-eval format.

Usage:
    from agentic_eval.adapters import from_openai

    # From OpenAI response with tool calls
    trace = from_openai(messages, response)

    # From a list of OpenAI message dicts
    trace = from_openai(conversation_messages)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..models import Span, SpanType, ToolCall, Trace


def from_openai(
    messages: list[dict[str, Any]],
    response: dict[str, Any] | None = None,
) -> Trace:
    """Convert OpenAI API messages/response into a Trace.

    Handles both ChatCompletion message lists and Agents SDK response formats.

    Args:
        messages: List of OpenAI message dicts with 'role', 'content', etc.
        response: Optional ChatCompletion response dict.

    Returns:
        A Trace with spans for each assistant turn, tool call, and function call.
    """
    user_input = _extract_user_input(messages)
    assistant_output = _extract_assistant_output(messages, response)

    trace = Trace(
        input=user_input,
        output=assistant_output,
        started_at=datetime.now(timezone.utc),
        ended_at=datetime.now(timezone.utc),
    )

    for msg in messages:
        role = msg.get("role", "")
        if role == "assistant":
            span = _convert_assistant_message(msg)
            trace.spans.append(span)

            for tc in msg.get("tool_calls", []):
                tool_span = _convert_tool_call(tc)
                span.children.append(tool_span)

        elif role == "tool":
            span = _convert_tool_result(msg)
            trace.spans.append(span)

        elif role == "function":
            span = _convert_function_call(msg)
            trace.spans.append(span)

    if response and "choices" in response:
        for choice in response["choices"]:
            msg = choice.get("message", {})
            for tc in msg.get("tool_calls", []):
                tool_span = _convert_tool_call(tc)
                trace.spans.append(tool_span)

    return trace


def _convert_assistant_message(msg: dict[str, Any]) -> Span:
    return Span(
        name="assistant",
        type=SpanType.LLM_CALL,
        output=msg.get("content"),
        started_at=datetime.now(timezone.utc),
        ended_at=datetime.now(timezone.utc),
        metadata={k: v for k, v in msg.items() if k not in ("role", "content", "tool_calls")},
    )


def _convert_tool_call(tc: dict[str, Any]) -> Span:
    func = tc.get("function", {})
    name = func.get("name", tc.get("name", "unknown"))
    arguments = func.get("arguments", {})

    if isinstance(arguments, str):
        import json
        try:
            arguments = json.loads(arguments)
        except (json.JSONDecodeError, TypeError):
            arguments = {"raw": arguments}

    return Span(
        name=f"tool:{name}",
        type=SpanType.TOOL_CALL,
        input=arguments,
        tool_call=ToolCall(name=name, arguments=arguments),
        started_at=datetime.now(timezone.utc),
        ended_at=datetime.now(timezone.utc),
        metadata={"tool_call_id": tc.get("id", "")},
    )


def _convert_tool_result(msg: dict[str, Any]) -> Span:
    return Span(
        name=f"tool_result:{msg.get('tool_call_id', '')}",
        type=SpanType.TOOL_CALL,
        output=msg.get("content"),
        started_at=datetime.now(timezone.utc),
        ended_at=datetime.now(timezone.utc),
    )


def _convert_function_call(msg: dict[str, Any]) -> Span:
    return Span(
        name=f"function:{msg.get('name', 'unknown')}",
        type=SpanType.TOOL_CALL,
        output=msg.get("content"),
        started_at=datetime.now(timezone.utc),
        ended_at=datetime.now(timezone.utc),
    )


def _extract_user_input(messages: list[dict[str, Any]]) -> str | None:
    for msg in messages:
        if msg.get("role") == "user":
            return msg.get("content")
    return None


def _extract_assistant_output(
    messages: list[dict[str, Any]], response: dict[str, Any] | None
) -> str | None:
    if response and "choices" in response:
        choices = response["choices"]
        if choices:
            return choices[0].get("message", {}).get("content")

    for msg in reversed(messages):
        if msg.get("role") == "assistant":
            return msg.get("content")
    return None
