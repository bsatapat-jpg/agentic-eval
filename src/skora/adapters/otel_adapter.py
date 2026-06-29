"""Adapter for converting OpenTelemetry spans to skora format.

Usage:
    from skora.adapters import from_otel

    # From OTel span dicts (e.g., exported JSON)
    trace = from_otel(otel_spans)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..models import Span, SpanType, ToolCall, Trace


def from_otel(
    spans: list[dict[str, Any]],
    trace_id: str | None = None,
) -> Trace:
    """Convert a list of OpenTelemetry span dicts into a Trace.

    Expects spans in the OTel JSON export format with keys like
    'traceId', 'spanId', 'parentSpanId', 'name', 'attributes',
    'startTimeUnixNano', 'endTimeUnixNano'.

    Args:
        spans: List of OTel span dicts.
        trace_id: Override trace ID. Defaults to the first span's traceId.

    Returns:
        A hierarchically structured Trace.
    """
    if not spans:
        return Trace()

    tid = trace_id or spans[0].get("traceId", "")
    span_map: dict[str, Span] = {}
    children_map: dict[str, list[str]] = {}
    root_span_ids: list[str] = []

    for otel_span in spans:
        span_id = otel_span.get("spanId", "")
        parent_id = otel_span.get("parentSpanId", "")
        converted = _convert_otel_span(otel_span)
        span_map[span_id] = converted

        if parent_id:
            children_map.setdefault(parent_id, []).append(span_id)
        else:
            root_span_ids.append(span_id)

    for parent_id, child_ids in children_map.items():
        parent = span_map.get(parent_id)
        if parent:
            for child_id in child_ids:
                child = span_map.get(child_id)
                if child:
                    parent.children.append(child)

    root_spans = [span_map[sid] for sid in root_span_ids if sid in span_map]

    all_starts = [s.started_at for s in span_map.values() if s.started_at]
    all_ends = [s.ended_at for s in span_map.values() if s.ended_at]

    return Trace(
        id=tid,
        spans=root_spans,
        started_at=min(all_starts) if all_starts else datetime.now(timezone.utc),
        ended_at=max(all_ends) if all_ends else datetime.now(timezone.utc),
    )


def _convert_otel_span(otel_span: dict[str, Any]) -> Span:
    attrs = otel_span.get("attributes", {})
    name = otel_span.get("name", "")
    span_type = _infer_span_type(name, attrs)

    tool_call = None
    if span_type == SpanType.TOOL_CALL:
        tool_name = attrs.get("tool.name") or name
        tool_call = ToolCall(
            name=tool_name,
            arguments=attrs.get("tool.parameters", {}),
            result=attrs.get("tool.result"),
        )

    status = otel_span.get("status", {})
    error = None
    if status.get("statusCode") == 2:
        error = status.get("message", "Error")

    return Span(
        id=otel_span.get("spanId", ""),
        name=name,
        type=span_type,
        input=attrs.get("input") or attrs.get("gen_ai.prompt"),
        output=attrs.get("output") or attrs.get("gen_ai.completion"),
        error=error,
        tool_call=tool_call,
        started_at=_nano_to_datetime(otel_span.get("startTimeUnixNano")),
        ended_at=_nano_to_datetime(otel_span.get("endTimeUnixNano")),
        metadata={k: v for k, v in attrs.items()
                  if not k.startswith(("input", "output", "tool.", "gen_ai."))},
    )


def _infer_span_type(name: str, attrs: dict[str, Any]) -> SpanType:
    name_lower = name.lower()

    if attrs.get("tool.name") or "tool" in name_lower:
        return SpanType.TOOL_CALL
    if attrs.get("gen_ai.system") or attrs.get("llm.system") or "llm" in name_lower:
        return SpanType.LLM_CALL
    if "retriev" in name_lower or "search" in name_lower:
        return SpanType.RETRIEVAL
    if "agent" in name_lower or "chain" in name_lower:
        return SpanType.AGENT_STEP

    return SpanType.CUSTOM


def _nano_to_datetime(nanos: int | str | None) -> datetime:
    if nanos is None:
        return datetime.now(timezone.utc)
    nanos = int(nanos)
    return datetime.fromtimestamp(nanos / 1e9, tz=timezone.utc)
