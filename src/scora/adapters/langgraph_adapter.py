"""Adapter for converting LangGraph traces to scora format.

LangGraph agents produce execution data in several forms:

1. **Callback/tracer data** — LangGraph uses LangChain's callback system
   internally.  If you export traces via LangSmith, use ``from_langchain``.

2. **State checkpoints** — LangGraph checkpoints contain the full
   message list (``messages`` key) with ``HumanMessage``, ``AIMessage``,
   ``ToolMessage`` objects (or their dict representations).

3. **Streaming events** — ``astream_events()`` produces a stream of
   ``{"event": ..., "data": ...}`` dicts.

This adapter handles all three, plus the common case of extracting
traces directly from the ``messages`` key of a LangGraph state.

Usage::

    from scora.adapters import from_langgraph
    from scora import run_evaluation

    # From LangGraph state (most common)
    final_state = await graph.ainvoke({"messages": [...]})
    trace = from_langgraph(final_state)

    # From streaming events
    events = [e async for e in graph.astream_events(input, version="v2")]
    trace = from_langgraph(events)

    result = run_evaluation(trace, skill="./SKILL.md")
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from ..models import Span, SpanType, ToolCall, Trace


def from_langgraph(
    data: dict[str, Any] | list[dict[str, Any] | Any],
    *,
    trace_id: str | None = None,
) -> Trace:
    """Convert LangGraph data into an scora Trace.

    Args:
        data: One of:
              - A LangGraph state dict (with ``messages`` key).
              - A list of LangChain message objects or dicts.
              - A list of streaming event dicts from ``astream_events``.
        trace_id: Override trace ID.

    Returns:
        A fully populated Trace with hierarchical spans.
    """
    if isinstance(data, dict):
        messages = data.get("messages")
        if messages is not None:
            return _from_messages(messages, trace_id)
        if data.get("event"):
            return _from_events([data], trace_id)
        return _from_messages([], trace_id)

    if isinstance(data, list) and data:
        first = data[0]
        first_dict = _to_dict(first)
        if "event" in first_dict:
            return _from_events(data, trace_id)
        return _from_messages(data, trace_id)

    return Trace(id=trace_id or "")


# ---------------------------------------------------------------------------
# From messages (LangGraph state["messages"])
# ---------------------------------------------------------------------------

def _from_messages(
    messages: list[Any],
    override_id: str | None,
) -> Trace:
    if not messages:
        return Trace(id=override_id or "")

    msg_dicts = [_to_dict(m) for m in messages]

    user_input = None
    model_output = None

    for m in msg_dicts:
        role = _get_role(m)
        if role == "human" and user_input is None:
            user_input = _get_content(m)
    for m in reversed(msg_dicts):
        role = _get_role(m)
        if role in ("ai", "assistant") and model_output is None:
            content = _get_content(m)
            if content:
                model_output = content
                break

    trace = Trace(
        id=override_id or "",
        input=user_input,
        output=model_output,
        started_at=datetime.now(timezone.utc),
        ended_at=datetime.now(timezone.utc),
    )

    for m in msg_dicts:
        spans = _message_to_spans(m)
        trace.spans.extend(spans)

    return trace


def _message_to_spans(msg: dict[str, Any]) -> list[Span]:
    """Convert a single message dict into zero or more spans."""
    role = _get_role(msg)
    spans: list[Span] = []

    if role in ("ai", "assistant"):
        tool_calls = msg.get("tool_calls") or []
        additional_kwargs = msg.get("additional_kwargs", {})
        if not tool_calls:
            tool_calls = additional_kwargs.get("tool_calls", [])

        child_spans: list[Span] = []
        for tc in tool_calls:
            tc_span = _convert_tool_call(tc)
            child_spans.append(tc_span)

        content = _get_content(msg)
        model = (
            msg.get("response_metadata", {}).get("model_name")
            or msg.get("response_metadata", {}).get("model")
            or ""
        )

        metadata: dict[str, Any] = {}
        if model:
            metadata["model"] = model
        usage = msg.get("usage_metadata") or msg.get("response_metadata", {}).get("token_usage")
        if usage:
            metadata["token_usage"] = usage

        span = Span(
            name=f"llm:{model or 'model'}",
            type=SpanType.LLM_CALL,
            input=msg.get("input"),
            output=content,
            metadata=metadata,
            children=child_spans,
            started_at=datetime.now(timezone.utc),
            ended_at=datetime.now(timezone.utc),
        )
        spans.append(span)

    elif role == "tool":
        name = msg.get("name", "tool")
        tool_call_id = msg.get("tool_call_id", "")
        content = _get_content(msg)
        error = None
        status = msg.get("status")
        if status == "error":
            error = content or "Tool error"

        span = Span(
            name=f"tool_result:{name}",
            type=SpanType.TOOL_CALL,
            output=content,
            error=error,
            tool_call=ToolCall(
                name=name,
                arguments={},
                result=content,
                error=error,
            ),
            metadata={"tool_call_id": tool_call_id} if tool_call_id else {},
            started_at=datetime.now(timezone.utc),
            ended_at=datetime.now(timezone.utc),
        )
        spans.append(span)

    return spans


def _convert_tool_call(tc: dict[str, Any]) -> Span:
    """Convert a LangChain-style tool call into a span."""
    name = tc.get("name", tc.get("function", {}).get("name", "unknown"))
    args = tc.get("args", tc.get("function", {}).get("arguments", {}))

    if isinstance(args, str):
        try:
            args = json.loads(args)
        except (json.JSONDecodeError, TypeError):
            args = {"raw": args}

    return Span(
        name=f"tool:{name}",
        type=SpanType.TOOL_CALL,
        input=args,
        tool_call=ToolCall(name=name, arguments=args if isinstance(args, dict) else {}),
        started_at=datetime.now(timezone.utc),
        ended_at=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# From streaming events  (astream_events v2)
# ---------------------------------------------------------------------------

def _from_events(
    events: list[dict[str, Any] | Any],
    override_id: str | None,
) -> Trace:
    event_dicts = [_to_dict(e) for e in events]

    user_input = None
    model_output = None
    spans: list[Span] = []

    active_tool_spans: dict[str, Span] = {}

    for ev in event_dicts:
        event_type = ev.get("event", "")
        data = ev.get("data", {})
        name = ev.get("name", "")
        run_id = ev.get("run_id", "")
        tags = ev.get("tags", [])

        if event_type == "on_chain_start" and not spans:
            inp = data.get("input")
            if isinstance(inp, dict):
                messages = inp.get("messages", [])
                if messages:
                    first = _to_dict(messages[0])
                    user_input = _get_content(first)

        elif event_type == "on_chat_model_end":
            output = data.get("output")
            if output:
                output_dict = _to_dict(output)
                content = _get_content(output_dict)
                if content:
                    model_output = content

                model = output_dict.get("response_metadata", {}).get("model_name", "")

                child_tcs = []
                for tc in output_dict.get("tool_calls", []):
                    child_tcs.append(_convert_tool_call(tc))

                metadata: dict[str, Any] = {}
                if model:
                    metadata["model"] = model
                usage = output_dict.get("usage_metadata")
                if usage:
                    metadata["token_usage"] = usage

                span = Span(
                    name=f"llm:{model or name or 'model'}",
                    type=SpanType.LLM_CALL,
                    output=content,
                    metadata=metadata,
                    children=child_tcs,
                )
                spans.append(span)

        elif event_type == "on_tool_start":
            inp = data.get("input")
            tool_span = Span(
                name=f"tool:{name}",
                type=SpanType.TOOL_CALL,
                input=inp,
                tool_call=ToolCall(
                    name=name,
                    arguments=inp if isinstance(inp, dict) else {},
                ),
                started_at=datetime.now(timezone.utc),
            )
            active_tool_spans[run_id] = tool_span

        elif event_type == "on_tool_end":
            tool_span = active_tool_spans.pop(run_id, None)
            output = data.get("output")
            output_content = _get_content(_to_dict(output)) if output else str(output)

            if tool_span:
                tool_span.output = output_content
                tool_span.ended_at = datetime.now(timezone.utc)
                if tool_span.tool_call:
                    tool_span.tool_call.result = output_content
                spans.append(tool_span)
            else:
                span = Span(
                    name=f"tool:{name}",
                    type=SpanType.TOOL_CALL,
                    output=output_content,
                    tool_call=ToolCall(name=name, result=output_content),
                )
                spans.append(span)

        elif event_type == "on_retriever_end":
            documents = data.get("output", [])
            span = Span(
                name=f"retriever:{name}",
                type=SpanType.RETRIEVAL,
                output=documents,
                tool_call=ToolCall(
                    name=name or "retriever",
                    arguments=data.get("input", {}),
                    result=documents,
                ),
            )
            spans.append(span)

    for leftover in active_tool_spans.values():
        leftover.ended_at = datetime.now(timezone.utc)
        spans.append(leftover)

    return Trace(
        id=override_id or "",
        input=user_input,
        output=model_output,
        spans=spans,
        started_at=datetime.now(timezone.utc),
        ended_at=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_role(msg: dict[str, Any]) -> str:
    """Extract the role, normalising LangChain message types."""
    role = msg.get("role", "")
    if role:
        return role.lower()

    msg_type = msg.get("type", "")
    type_map = {
        "human": "human",
        "HumanMessage": "human",
        "ai": "ai",
        "AIMessage": "ai",
        "AIMessageChunk": "ai",
        "tool": "tool",
        "ToolMessage": "tool",
        "system": "system",
        "SystemMessage": "system",
        "function": "function",
        "FunctionMessage": "function",
    }
    return type_map.get(msg_type, msg_type.lower())


def _get_content(msg: dict[str, Any]) -> str | None:
    """Extract text content from a message dict."""
    content = msg.get("content")
    if content is None:
        return None
    if isinstance(content, str):
        return content if content else None
    if isinstance(content, list):
        texts = []
        for block in content:
            if isinstance(block, str):
                texts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                texts.append(block.get("text", ""))
        return "\n".join(texts) if texts else None
    return str(content)


def _to_dict(obj: Any) -> dict[str, Any]:
    """Convert a LangChain message or object to a plain dict."""
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="python")
    if hasattr(obj, "dict"):
        return obj.dict()
    if hasattr(obj, "__dict__"):
        return vars(obj)
    return {"content": str(obj)}
