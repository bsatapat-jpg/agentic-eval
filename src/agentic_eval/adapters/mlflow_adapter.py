"""Adapter for converting MLflow traces/spans to agentic-eval format.

MLflow traces consist of ``TraceInfo`` (metadata) and ``TraceData`` (a list of
``Span`` objects).  Spans use the OpenTelemetry-compatible schema with fields
like ``span_id``, ``parent_id``, ``inputs``, ``outputs``, ``attributes``, and
a ``span_type`` (``TOOL``, ``RETRIEVER``, ``LLM``, ``CHAT_MODEL``, ``AGENT``,
etc.).

This adapter accepts:

1. An MLflow ``Trace`` object (has ``.info`` and ``.data.spans``).
2. A dict with ``info`` and ``data`` keys (serialised trace).
3. A plain list of span dicts (exported JSON / ``trace.data.spans``).

Usage::

    from agentic_eval.adapters import from_mlflow
    from agentic_eval import run_evaluation

    import mlflow
    trace = mlflow.get_trace("<trace_id>")
    eval_trace = from_mlflow(trace)

    result = run_evaluation(eval_trace, skill="./SKILL.md")
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..models import Span, SpanType, ToolCall, Trace


def from_mlflow(
    data: Any,
    *,
    trace_id: str | None = None,
) -> Trace:
    """Convert MLflow trace data into an agentic-eval Trace.

    Args:
        data: One of:
              - An MLflow ``Trace`` object (``data.spans`` is a list of Span).
              - A dict with ``info`` (TraceInfo) and ``data`` (TraceData) keys.
              - A plain list of span dicts.
        trace_id: Override trace ID.

    Returns:
        A fully populated Trace with hierarchical spans.
    """
    if isinstance(data, list):
        return _from_span_list([_span_to_dict(s) for s in data], trace_id)

    if isinstance(data, dict):
        return _from_trace_dict(data, trace_id)

    # MLflow Trace object (has .info and .data)
    if hasattr(data, "data") and hasattr(data, "info"):
        return _from_trace_object(data, trace_id)

    # Fallback: try treating it as a list-like of spans
    if hasattr(data, "__iter__"):
        return _from_span_list([_span_to_dict(s) for s in data], trace_id)

    return Trace(id=trace_id or "")


# ---------------------------------------------------------------------------
# MLflow Trace object  (trace.info + trace.data.spans)
# ---------------------------------------------------------------------------

def _from_trace_object(trace_obj: Any, override_id: str | None) -> Trace:
    info = trace_obj.info
    spans_raw = trace_obj.data.spans if hasattr(trace_obj.data, "spans") else []
    span_dicts = [_span_to_dict(s) for s in spans_raw]

    tid = override_id or getattr(info, "trace_id", None) or getattr(info, "request_id", "") or ""

    root_input, root_output = _extract_root_io(span_dicts)

    started = _ns_to_datetime(
        getattr(info, "timestamp_ms", None),
        ms=True,
    ) if hasattr(info, "timestamp_ms") else datetime.now(timezone.utc)

    execution_time_ms = getattr(info, "execution_time_ms", None)
    ended = (
        datetime.fromtimestamp(
            (getattr(info, "timestamp_ms", 0) + execution_time_ms) / 1000,
            tz=timezone.utc,
        )
        if execution_time_ms is not None and hasattr(info, "timestamp_ms")
        else None
    )

    metadata: dict[str, Any] = {}
    if hasattr(info, "tags"):
        tags = info.tags
        if isinstance(tags, dict):
            metadata["tags"] = tags
    if hasattr(info, "experiment_id"):
        metadata["experiment_id"] = info.experiment_id

    return Trace(
        id=str(tid),
        input=root_input,
        output=root_output,
        spans=_build_hierarchy(span_dicts),
        started_at=started,
        ended_at=ended,
        metadata=metadata,
    )


# ---------------------------------------------------------------------------
# Serialised trace dict  {info: {...}, data: {spans: [...]}}
# ---------------------------------------------------------------------------

def _from_trace_dict(trace_dict: dict[str, Any], override_id: str | None) -> Trace:
    info = trace_dict.get("info", {})
    data = trace_dict.get("data", {})
    span_dicts = [_span_to_dict(s) for s in data.get("spans", [])]

    tid = (
        override_id
        or info.get("trace_id")
        or info.get("request_id")
        or trace_dict.get("trace_id")
        or ""
    )

    root_input, root_output = _extract_root_io(span_dicts)

    started = _ns_to_datetime(info.get("timestamp_ms"), ms=True)
    execution_time_ms = info.get("execution_time_ms")
    ended = (
        datetime.fromtimestamp(
            (info.get("timestamp_ms", 0) + execution_time_ms) / 1000,
            tz=timezone.utc,
        )
        if execution_time_ms is not None and info.get("timestamp_ms") is not None
        else None
    )

    return Trace(
        id=str(tid),
        input=root_input,
        output=root_output,
        spans=_build_hierarchy(span_dicts),
        started_at=started,
        ended_at=ended,
        metadata=info.get("tags") or {},
    )


# ---------------------------------------------------------------------------
# Plain span list
# ---------------------------------------------------------------------------

def _from_span_list(span_dicts: list[dict[str, Any]], override_id: str | None) -> Trace:
    if not span_dicts:
        return Trace(id=override_id or "")

    tid = override_id or str(span_dicts[0].get("trace_id", ""))
    root_input, root_output = _extract_root_io(span_dicts)

    all_starts = [_ns_to_datetime(s.get("start_time_ns")) for s in span_dicts]
    all_ends = [_ns_to_datetime(s.get("end_time_ns")) for s in span_dicts]

    return Trace(
        id=tid,
        input=root_input,
        output=root_output,
        spans=_build_hierarchy(span_dicts),
        started_at=min(all_starts) if all_starts else datetime.now(timezone.utc),
        ended_at=max(all_ends) if all_ends else datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _extract_root_io(span_dicts: list[dict[str, Any]]) -> tuple[Any, Any]:
    """Find the root span(s) and extract their combined I/O."""
    root_input = None
    root_output = None
    for s in span_dicts:
        if not s.get("parent_id"):
            root_input = root_input or s.get("inputs")
            root_output = root_output or s.get("outputs")
    return root_input, root_output


def _build_hierarchy(span_dicts: list[dict[str, Any]]) -> list[Span]:
    """Reconstruct parent-child tree from flat span list."""
    span_map: dict[str, Span] = {}
    children_map: dict[str, list[str]] = {}
    root_ids: list[str] = []

    for sd in span_dicts:
        sid = str(sd.get("span_id", sd.get("id", "")))
        parent_id = sd.get("parent_id") or ""
        span = _convert_span(sd)
        span_map[sid] = span

        if parent_id:
            children_map.setdefault(str(parent_id), []).append(sid)
        else:
            root_ids.append(sid)

    for pid, cids in children_map.items():
        parent = span_map.get(pid)
        if parent:
            for cid in cids:
                child = span_map.get(cid)
                if child:
                    parent.children.append(child)

    return [span_map[rid] for rid in root_ids if rid in span_map]


def _convert_span(sd: dict[str, Any]) -> Span:
    raw_type = str(sd.get("span_type", sd.get("type", "UNKNOWN"))).upper()
    name = sd.get("name", "")
    span_type = _map_span_type(raw_type, name)

    inputs = sd.get("inputs")
    outputs = sd.get("outputs")
    attributes = sd.get("attributes", {})

    tool_call = None
    if span_type == SpanType.TOOL_CALL:
        tool_call = ToolCall(
            name=name,
            arguments=inputs if isinstance(inputs, dict) else {},
            result=outputs,
        )
    elif span_type == SpanType.RETRIEVAL:
        tool_call = ToolCall(
            name=name or "retriever",
            arguments=inputs if isinstance(inputs, dict) else {},
            result=outputs,
        )

    error = None
    status = sd.get("status", {})
    if isinstance(status, dict):
        status_code = str(status.get("status_code", status.get("statusCode", ""))).upper()
        if status_code == "ERROR":
            error = status.get("description") or status.get("message") or "Error"
    elif isinstance(status, str) and status.upper() == "ERROR":
        error = "Error"

    events = sd.get("events", [])
    if not error and events:
        for ev in events:
            ev_dict = _to_dict(ev)
            if ev_dict.get("name") == "exception":
                exc_attrs = ev_dict.get("attributes", {})
                error = exc_attrs.get("exception.message") or "Exception"
                break

    metadata: dict[str, Any] = {}
    if attributes:
        metadata.update(attributes)
    model = attributes.get("mlflow.chat.model") or attributes.get("model")
    if model:
        metadata["model"] = model

    return Span(
        id=str(sd.get("span_id", sd.get("id", ""))),
        name=name,
        type=span_type,
        input=inputs,
        output=outputs,
        error=error,
        tool_call=tool_call,
        started_at=_ns_to_datetime(sd.get("start_time_ns")),
        ended_at=_ns_to_datetime(sd.get("end_time_ns")),
        metadata=metadata,
    )


_MLFLOW_TYPE_MAP: dict[str, SpanType] = {
    "TOOL": SpanType.TOOL_CALL,
    "RETRIEVER": SpanType.RETRIEVAL,
    "LLM": SpanType.LLM_CALL,
    "CHAT_MODEL": SpanType.LLM_CALL,
    "AGENT": SpanType.AGENT_STEP,
    "CHAIN": SpanType.AGENT_STEP,
    "WORKFLOW": SpanType.AGENT_STEP,
    "TASK": SpanType.AGENT_STEP,
    "EMBEDDING": SpanType.LLM_CALL,
    "PARSER": SpanType.CUSTOM,
    "RERANKER": SpanType.CUSTOM,
    "MEMORY": SpanType.CUSTOM,
    "GUARDRAIL": SpanType.CUSTOM,
    "EVALUATOR": SpanType.CUSTOM,
}


def _map_span_type(raw_type: str, name: str) -> SpanType:
    if raw_type in _MLFLOW_TYPE_MAP:
        return _MLFLOW_TYPE_MAP[raw_type]

    name_lower = name.lower()
    if "tool" in name_lower:
        return SpanType.TOOL_CALL
    if any(kw in name_lower for kw in ("retriev", "search", "rag", "vector")):
        return SpanType.RETRIEVAL
    if any(kw in name_lower for kw in ("llm", "gpt", "claude", "gemini", "chat")):
        return SpanType.LLM_CALL
    if any(kw in name_lower for kw in ("agent", "chain", "workflow")):
        return SpanType.AGENT_STEP

    return SpanType.CUSTOM


def _span_to_dict(span: Any) -> dict[str, Any]:
    """Convert an MLflow Span object or dict to a plain dict."""
    if isinstance(span, dict):
        return span
    if hasattr(span, "to_dict"):
        return span.to_dict()
    if hasattr(span, "model_dump"):
        return span.model_dump(mode="python")
    if hasattr(span, "__dict__"):
        d: dict[str, Any] = {}
        for attr in (
            "span_id", "trace_id", "parent_id", "name", "span_type",
            "start_time_ns", "end_time_ns", "inputs", "outputs",
            "attributes", "events", "status",
        ):
            if hasattr(span, attr):
                d[attr] = getattr(span, attr)
        return d
    return {"value": span}


def _to_dict(obj: Any) -> dict[str, Any]:
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="python")
    if hasattr(obj, "__dict__"):
        return vars(obj)
    return {}


def _ns_to_datetime(val: Any, *, ms: bool = False) -> datetime:
    if val is None:
        return datetime.now(timezone.utc)
    try:
        val = int(val)
    except (TypeError, ValueError):
        return datetime.now(timezone.utc)
    divisor = 1e3 if ms else 1e9
    return datetime.fromtimestamp(val / divisor, tz=timezone.utc)
