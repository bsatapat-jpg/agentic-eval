"""Adapter for converting Langfuse traces/observations to skora format.

Langfuse organises data as *observations* (spans, generations, events) grouped
by a shared ``traceId``.  This adapter accepts both:

1. A list of observation dicts (the rows returned by the Observations API v2
   or ``langfuse.api.observations.get_many()``) — these are reconstructed into
   a hierarchical ``Trace`` using ``parentObservationId``.
2. A legacy trace dict (from ``GET /api/public/traces/{traceId}``) that
   contains top-level ``input``/``output`` and nested ``observations``.

Usage::

    from skora.adapters import from_langfuse
    from skora import run_evaluation

    # From a list of observation dicts / SDK objects
    trace = from_langfuse(observations)

    # From a legacy trace dict
    trace = from_langfuse(trace_dict)

    result = run_evaluation(trace, skill="./SKILL.md")
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..models import Span, SpanType, ToolCall, Trace


def from_langfuse(
    data: dict[str, Any] | list[dict[str, Any] | Any],
    *,
    trace_id: str | None = None,
) -> Trace:
    """Convert Langfuse data into an skora Trace.

    Args:
        data: Either a list of observation dicts/objects (v2 API style), or a
              single legacy trace dict with an ``observations`` key.
        trace_id: Override trace ID.  Defaults to the ``traceId`` found in the
                  data.

    Returns:
        A fully populated Trace with hierarchical spans.
    """
    if isinstance(data, dict):
        return _from_legacy_trace(data, trace_id)
    return _from_observations(list(data), trace_id)


# ---------------------------------------------------------------------------
# Legacy trace dict  (GET /api/public/traces/{traceId})
# ---------------------------------------------------------------------------

def _from_legacy_trace(trace_dict: dict[str, Any], override_id: str | None) -> Trace:
    observations = trace_dict.get("observations", [])

    trace = Trace(
        id=override_id or str(trace_dict.get("id", "")),
        input=trace_dict.get("input"),
        output=trace_dict.get("output"),
        started_at=_parse_time(trace_dict.get("createdAt") or trace_dict.get("timestamp")),
        ended_at=_parse_time(trace_dict.get("updatedAt")),
        metadata=trace_dict.get("metadata") or {},
    )

    if observations:
        trace.spans = _build_hierarchy([_to_dict(o) for o in observations])

    return trace


# ---------------------------------------------------------------------------
# Observation list  (Observations API v2 / SDK get_many)
# ---------------------------------------------------------------------------

def _from_observations(
    observations: list[dict[str, Any] | Any],
    override_id: str | None,
) -> Trace:
    if not observations:
        return Trace(id=override_id or "")

    obs_dicts = [_to_dict(o) for o in observations]

    tid = override_id or str(obs_dicts[0].get("traceId", obs_dicts[0].get("trace_id", "")))

    all_starts = [_parse_time(o.get("startTime") or o.get("start_time")) for o in obs_dicts]
    all_ends = [
        _parse_time(o.get("completionStartTime") or o.get("endTime") or o.get("end_time"))
        for o in obs_dicts
    ]

    root_input = None
    root_output = None
    for o in obs_dicts:
        if not (o.get("parentObservationId") or o.get("parent_observation_id")):
            root_input = root_input or o.get("input")
            root_output = root_output or o.get("output")

    trace = Trace(
        id=tid,
        input=root_input,
        output=root_output,
        spans=_build_hierarchy(obs_dicts),
        started_at=min(all_starts) if all_starts else datetime.now(timezone.utc),
        ended_at=max(all_ends) if all_ends else datetime.now(timezone.utc),
    )
    return trace


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _build_hierarchy(obs_dicts: list[dict[str, Any]]) -> list[Span]:
    """Reconstruct parent-child tree from flat observation list."""
    span_map: dict[str, Span] = {}
    children_map: dict[str, list[str]] = {}
    root_ids: list[str] = []

    for obs in obs_dicts:
        obs_id = str(obs.get("id", ""))
        parent_id = obs.get("parentObservationId") or obs.get("parent_observation_id") or ""
        span = _convert_observation(obs)
        span_map[obs_id] = span

        if parent_id:
            children_map.setdefault(str(parent_id), []).append(obs_id)
        else:
            root_ids.append(obs_id)

    for parent_id, child_ids in children_map.items():
        parent = span_map.get(parent_id)
        if parent:
            for cid in child_ids:
                child = span_map.get(cid)
                if child:
                    parent.children.append(child)

    return [span_map[rid] for rid in root_ids if rid in span_map]


def _convert_observation(obs: dict[str, Any]) -> Span:
    obs_type = (obs.get("type") or obs.get("observationType") or "").upper()
    name = obs.get("name") or ""
    span_type = _map_observation_type(obs_type, name)

    tool_call = None
    if span_type == SpanType.TOOL_CALL:
        tool_call = ToolCall(
            name=name,
            arguments=obs.get("input") if isinstance(obs.get("input"), dict) else {},
            result=obs.get("output"),
        )
    elif span_type == SpanType.RETRIEVAL:
        tool_call = ToolCall(
            name=name or "retrieval",
            arguments=obs.get("input") if isinstance(obs.get("input"), dict) else {},
            result=obs.get("output"),
        )

    error = None
    level = (obs.get("level") or "").upper()
    if level == "ERROR":
        error = obs.get("statusMessage") or obs.get("status_message") or "Error"

    metadata: dict[str, Any] = {}
    if obs.get("model"):
        metadata["model"] = obs["model"]
    if obs.get("modelParameters") or obs.get("model_parameters"):
        metadata["model_parameters"] = obs.get("modelParameters") or obs.get("model_parameters")
    usage = obs.get("usage") or obs.get("usageDetails") or obs.get("usage_details")
    if usage:
        metadata["token_usage"] = usage
    if obs.get("metadata"):
        if isinstance(obs["metadata"], dict):
            metadata.update(obs["metadata"])

    return Span(
        id=str(obs.get("id", "")),
        name=name,
        type=span_type,
        input=obs.get("input"),
        output=obs.get("output"),
        error=error,
        tool_call=tool_call,
        started_at=_parse_time(obs.get("startTime") or obs.get("start_time")),
        ended_at=_parse_time(
            obs.get("completionStartTime") or obs.get("endTime") or obs.get("end_time")
        ),
        metadata=metadata,
    )


_OBSERVATION_TYPE_MAP: dict[str, SpanType] = {
    "GENERATION": SpanType.LLM_CALL,
    "SPAN": SpanType.AGENT_STEP,
    "EVENT": SpanType.CUSTOM,
    "TOOL": SpanType.TOOL_CALL,
}


def _map_observation_type(obs_type: str, name: str) -> SpanType:
    if obs_type in _OBSERVATION_TYPE_MAP:
        return _OBSERVATION_TYPE_MAP[obs_type]

    name_lower = name.lower()
    if any(kw in name_lower for kw in ("tool", "function_call")):
        return SpanType.TOOL_CALL
    if any(kw in name_lower for kw in ("retriev", "search", "rag", "vector")):
        return SpanType.RETRIEVAL
    if any(kw in name_lower for kw in ("llm", "gpt", "claude", "gemini", "chat")):
        return SpanType.LLM_CALL
    if any(kw in name_lower for kw in ("agent", "chain", "workflow")):
        return SpanType.AGENT_STEP

    return SpanType.CUSTOM


def _to_dict(obj: Any) -> dict[str, Any]:
    """Convert SDK objects to plain dicts."""
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="python")
    if hasattr(obj, "__dict__"):
        return vars(obj)
    return {"value": obj}


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
