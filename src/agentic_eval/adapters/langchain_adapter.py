"""Adapter for converting LangChain/LangGraph traces to agentic-eval format.

Usage:
    from langchain.callbacks import tracing_v2_enabled
    from agentic_eval.adapters import from_langchain

    # Option 1: From LangSmith run
    trace = from_langchain(run_dict)

    # Option 2: From LangChain callback data
    trace = from_langchain(callback_data)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..models import Span, SpanType, ToolCall, Trace


def from_langchain(run: dict[str, Any]) -> Trace:
    """Convert a LangChain run dict (LangSmith format) into a Trace.

    Accepts the format returned by LangSmith's GET /runs endpoint or
    the serialized output from LangChain's tracing callbacks.

    Args:
        run: A LangChain run dictionary with keys like 'inputs', 'outputs',
             'child_runs', 'run_type', 'name', 'start_time', 'end_time'.

    Returns:
        A fully populated Trace with nested spans.
    """
    trace = Trace(
        id=str(run.get("id", "")),
        input=run.get("inputs") or run.get("input"),
        output=run.get("outputs") or run.get("output"),
        started_at=_parse_time(run.get("start_time")),
        ended_at=_parse_time(run.get("end_time")),
        metadata=run.get("extra", {}),
    )

    for child in run.get("child_runs", []):
        span = _convert_run_to_span(child)
        trace.spans.append(span)

    return trace


def _convert_run_to_span(run: dict[str, Any]) -> Span:
    run_type = run.get("run_type", "")
    span_type = _map_run_type(run_type)

    tool_call = None
    if span_type == SpanType.TOOL_CALL:
        tool_call = ToolCall(
            name=run.get("name", ""),
            arguments=run.get("inputs", {}),
            result=run.get("outputs"),
            error=run.get("error"),
        )

    span = Span(
        id=str(run.get("id", "")),
        name=run.get("name", ""),
        type=span_type,
        input=run.get("inputs"),
        output=run.get("outputs"),
        error=run.get("error"),
        tool_call=tool_call,
        started_at=_parse_time(run.get("start_time")),
        ended_at=_parse_time(run.get("end_time")),
        metadata=run.get("extra", {}),
    )

    for child in run.get("child_runs", []):
        span.children.append(_convert_run_to_span(child))

    return span


def _map_run_type(run_type: str) -> SpanType:
    mapping = {
        "tool": SpanType.TOOL_CALL,
        "llm": SpanType.LLM_CALL,
        "chain": SpanType.AGENT_STEP,
        "retriever": SpanType.RETRIEVAL,
        "agent": SpanType.AGENT_STEP,
    }
    return mapping.get(run_type.lower(), SpanType.CUSTOM)


def _parse_time(val: Any) -> datetime:
    if val is None:
        return datetime.now(timezone.utc)
    if isinstance(val, datetime):
        return val
    if isinstance(val, str):
        try:
            return datetime.fromisoformat(val.replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.now(timezone.utc)
