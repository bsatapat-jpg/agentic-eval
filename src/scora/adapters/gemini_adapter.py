"""Adapter for converting Google Gemini API traces to scora format.

Handles both the `google-genai` (new unified SDK) and `google-generativeai`
(older SDK) response formats, as well as raw REST API dicts.

Usage:
    from scora.adapters import from_gemini
    from scora import run_evaluation

    # From Gemini chat history (list of content dicts)
    trace = from_gemini(contents)

    # From a GenerateContentResponse object
    trace = from_gemini(response=gemini_response)

    # From chat history + final response
    trace = from_gemini(contents, response=gemini_response)

    result = run_evaluation(trace, skill="./SKILL.md")
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from ..models import Span, SpanType, ToolCall, Trace


def from_gemini(
    contents: list[dict[str, Any]] | None = None,
    response: Any = None,
    model: str | None = None,
) -> Trace:
    """Convert Gemini API contents/response into a Trace.

    Accepts three input patterns:

    1. ``contents`` only — chat history as list of content dicts
    2. ``response`` only — a GenerateContentResponse object or dict
    3. Both — history + final response (avoids double-counting the
       last model turn if it appears in both)

    Args:
        contents: List of Gemini content dicts with ``role`` and ``parts``.
            Roles are ``user``, ``model``, or ``function``.
        response: A Gemini ``GenerateContentResponse`` object (from either
            SDK) or its dict representation with ``candidates``.
        model: Model name for metadata (e.g. ``"gemini-2.0-flash"``).

    Returns:
        A Trace with spans for LLM calls, tool/function calls, and
        function responses.
    """
    normalized_contents = _normalize_contents(contents)
    response_dict = _normalize_response(response)

    if response_dict and not normalized_contents:
        normalized_contents = _contents_from_response(response_dict)
    elif response_dict and normalized_contents:
        resp_contents = _contents_from_response(response_dict)
        if resp_contents:
            last_model_in_history = None
            for c in reversed(normalized_contents):
                if c.get("role") == "model":
                    last_model_in_history = c
                    break
            last_resp = resp_contents[-1] if resp_contents else None
            if last_resp and last_resp != last_model_in_history:
                normalized_contents.extend(resp_contents)

    user_input = _extract_user_input(normalized_contents)
    model_output = _extract_model_output(normalized_contents)

    trace = Trace(
        input=user_input,
        output=model_output,
        started_at=datetime.now(timezone.utc),
        ended_at=datetime.now(timezone.utc),
        metadata={"model": model} if model else {},
    )

    for content in normalized_contents:
        role = content.get("role", "")
        parts = content.get("parts", [])

        if role == "model":
            span = _convert_model_turn(parts, model)
            trace.spans.append(span)

        elif role == "function":
            for part in parts:
                func_resp = part.get("functionResponse") or part.get("function_response")
                if func_resp:
                    span = _convert_function_response(func_resp)
                    trace.spans.append(span)

    if response_dict:
        usage = _extract_usage(response_dict)
        if usage:
            trace.metadata["token_usage"] = usage

    return trace


def _convert_model_turn(parts: list[dict[str, Any]], model: str | None) -> Span:
    """Convert a model turn (with potentially mixed text + function calls) into a span."""
    texts = []
    function_call_spans = []

    for part in parts:
        if "text" in part:
            texts.append(part["text"])

        func_call = part.get("functionCall") or part.get("function_call")
        if func_call:
            fc_span = _convert_function_call(func_call)
            function_call_spans.append(fc_span)

    text_output = "\n".join(texts) if texts else None

    span = Span(
        name=f"llm:{model or 'gemini'}",
        type=SpanType.LLM_CALL,
        output=text_output,
        started_at=datetime.now(timezone.utc),
        ended_at=datetime.now(timezone.utc),
        metadata={"model": model} if model else {},
        children=function_call_spans,
    )

    return span


def _convert_function_call(func_call: dict[str, Any]) -> Span:
    """Convert a Gemini functionCall part into a tool call span."""
    name = func_call.get("name", "unknown")
    args = func_call.get("args", {})

    if isinstance(args, str):
        try:
            args = json.loads(args)
        except (json.JSONDecodeError, TypeError):
            args = {"raw": args}

    return Span(
        name=f"tool:{name}",
        type=SpanType.TOOL_CALL,
        input=args,
        tool_call=ToolCall(name=name, arguments=args),
        started_at=datetime.now(timezone.utc),
        ended_at=datetime.now(timezone.utc),
    )


def _convert_function_response(func_resp: dict[str, Any]) -> Span:
    """Convert a Gemini functionResponse part into a span."""
    name = func_resp.get("name", "unknown")
    response_data = func_resp.get("response", {})

    return Span(
        name=f"tool_result:{name}",
        type=SpanType.TOOL_CALL,
        output=response_data,
        tool_call=ToolCall(name=name, arguments={}, result=response_data),
        started_at=datetime.now(timezone.utc),
        ended_at=datetime.now(timezone.utc),
    )


def _normalize_contents(
    contents: list[dict[str, Any]] | Any | None,
) -> list[dict[str, Any]]:
    """Normalize contents to a list of dicts, handling SDK objects."""
    if contents is None:
        return []

    if isinstance(contents, list):
        result = []
        for item in contents:
            if isinstance(item, dict):
                result.append(item)
            elif hasattr(item, "role") and hasattr(item, "parts"):
                result.append(_sdk_content_to_dict(item))
            else:
                result.append({"role": "user", "parts": [{"text": str(item)}]})
        return result

    return []


def _normalize_response(response: Any) -> dict[str, Any] | None:
    """Normalize a Gemini response to a dict, handling SDK objects."""
    if response is None:
        return None

    if isinstance(response, dict):
        return response

    if hasattr(response, "candidates"):
        return _sdk_response_to_dict(response)

    return None


def _sdk_content_to_dict(content: Any) -> dict[str, Any]:
    """Convert an SDK Content object to a dict."""
    parts = []
    for part in getattr(content, "parts", []):
        part_dict: dict[str, Any] = {}

        if hasattr(part, "text") and part.text:
            part_dict["text"] = part.text

        fc = getattr(part, "function_call", None) or getattr(part, "functionCall", None)
        if fc:
            name = getattr(fc, "name", "unknown")
            args = getattr(fc, "args", {})
            if hasattr(args, "items"):
                args = dict(args)
            part_dict["functionCall"] = {"name": name, "args": args}

        fr = getattr(part, "function_response", None) or getattr(part, "functionResponse", None)
        if fr:
            name = getattr(fr, "name", "unknown")
            resp = getattr(fr, "response", {})
            if hasattr(resp, "items"):
                resp = dict(resp)
            part_dict["functionResponse"] = {"name": name, "response": resp}

        if part_dict:
            parts.append(part_dict)

    return {
        "role": getattr(content, "role", "model"),
        "parts": parts,
    }


def _sdk_response_to_dict(response: Any) -> dict[str, Any]:
    """Convert an SDK GenerateContentResponse to a dict."""
    result: dict[str, Any] = {"candidates": []}

    for candidate in getattr(response, "candidates", []):
        content = getattr(candidate, "content", None)
        if content:
            result["candidates"].append({"content": _sdk_content_to_dict(content)})

    usage = getattr(response, "usage_metadata", None)
    if usage:
        result["usageMetadata"] = {
            "promptTokenCount": getattr(usage, "prompt_token_count", 0),
            "candidatesTokenCount": getattr(usage, "candidates_token_count", 0),
            "totalTokenCount": getattr(usage, "total_token_count", 0),
        }

    return result


def _contents_from_response(response_dict: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract content dicts from a response dict."""
    contents = []
    for candidate in response_dict.get("candidates", []):
        content = candidate.get("content", {})
        if content:
            contents.append(content)
    return contents


def _extract_user_input(contents: list[dict[str, Any]]) -> str | None:
    """Extract the first user message text."""
    for content in contents:
        if content.get("role") == "user":
            for part in content.get("parts", []):
                if "text" in part:
                    return part["text"]
    return None


def _extract_model_output(contents: list[dict[str, Any]]) -> str | None:
    """Extract the last model text output."""
    for content in reversed(contents):
        if content.get("role") == "model":
            texts = [p["text"] for p in content.get("parts", []) if "text" in p]
            if texts:
                return "\n".join(texts)
    return None


def _extract_usage(response_dict: dict[str, Any]) -> dict[str, int] | None:
    """Extract token usage from response metadata."""
    usage = response_dict.get("usageMetadata") or response_dict.get("usage_metadata")
    if not usage:
        return None

    return {
        "prompt_tokens": usage.get("promptTokenCount", 0) or usage.get("prompt_token_count", 0),
        "completion_tokens": usage.get("candidatesTokenCount", 0) or usage.get("candidates_token_count", 0),
        "total_tokens": usage.get("totalTokenCount", 0) or usage.get("total_token_count", 0),
    }
