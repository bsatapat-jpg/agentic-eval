"""Trajectory tracer -- captures agent execution as structured traces.

Supports both sync and async execution patterns via context managers,
decorators, and manual recording functions.
"""

from __future__ import annotations

import asyncio
import contextvars
import time
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Generator

from .models import Span, SpanType, Trace, ToolCall

_current_trace: contextvars.ContextVar[Trace | None] = contextvars.ContextVar(
    "_current_trace", default=None
)
_current_span: contextvars.ContextVar[Span | None] = contextvars.ContextVar(
    "_current_span", default=None
)


def get_current_trace() -> Trace | None:
    return _current_trace.get()


def get_current_span() -> Span | None:
    return _current_span.get()


@contextmanager
def trace_context(
    input: Any = None,
    metadata: dict[str, Any] | None = None,
) -> Generator[Trace, None, None]:
    """Context manager that creates and manages a Trace.

    Usage:
        with trace_context(input="user query") as t:
            with span_context("step1", SpanType.TOOL_CALL) as s:
                ...
        # t now contains all spans
    """
    t = Trace(
        input=input,
        started_at=datetime.now(timezone.utc),
        metadata=metadata or {},
    )
    token = _current_trace.set(t)
    try:
        yield t
    finally:
        t.ended_at = datetime.now(timezone.utc)
        _current_trace.reset(token)


@asynccontextmanager
async def async_trace_context(
    input: Any = None,
    metadata: dict[str, Any] | None = None,
) -> AsyncGenerator[Trace, None]:
    """Async context manager for tracing async agent execution."""
    t = Trace(
        input=input,
        started_at=datetime.now(timezone.utc),
        metadata=metadata or {},
    )
    token = _current_trace.set(t)
    try:
        yield t
    finally:
        t.ended_at = datetime.now(timezone.utc)
        _current_trace.reset(token)


@contextmanager
def span_context(
    name: str = "",
    span_type: SpanType = SpanType.CUSTOM,
    input: Any = None,
    metadata: dict[str, Any] | None = None,
) -> Generator[Span, None, None]:
    """Context manager that creates and manages a Span within the current Trace.

    Spans nest automatically -- if called inside another span_context,
    the new span becomes a child of the outer span.
    """
    span = Span(
        name=name,
        type=span_type,
        input=input,
        started_at=datetime.now(timezone.utc),
        metadata=metadata or {},
    )

    parent_span = _current_span.get()
    trace = _current_trace.get()
    span_token = _current_span.set(span)

    try:
        yield span
    except Exception as exc:
        span.error = str(exc)
        raise
    finally:
        span.ended_at = datetime.now(timezone.utc)
        _attach_span(span, parent_span, trace)
        _current_span.reset(span_token)


@asynccontextmanager
async def async_span_context(
    name: str = "",
    span_type: SpanType = SpanType.CUSTOM,
    input: Any = None,
    metadata: dict[str, Any] | None = None,
) -> AsyncGenerator[Span, None]:
    """Async context manager for spans within an async trace."""
    span = Span(
        name=name,
        type=span_type,
        input=input,
        started_at=datetime.now(timezone.utc),
        metadata=metadata or {},
    )

    parent_span = _current_span.get()
    trace = _current_trace.get()
    span_token = _current_span.set(span)

    try:
        yield span
    except Exception as exc:
        span.error = str(exc)
        raise
    finally:
        span.ended_at = datetime.now(timezone.utc)
        _attach_span(span, parent_span, trace)
        _current_span.reset(span_token)


def _attach_span(span: Span, parent_span: Span | None, trace: Trace | None) -> None:
    """Attach a span to its parent span or trace."""
    if parent_span is not None:
        parent_span.children.append(span)
    elif trace is not None:
        trace.spans.append(span)
    else:
        import logging
        logging.getLogger("scora").warning(
            "record_%s('%s') called outside trace_context — span discarded. "
            "Wrap your code in `with trace_context() as t:` to capture spans.",
            span.type.value,
            span.name,
        )


def record_tool_call(
    name: str,
    arguments: dict[str, Any] | None = None,
    result: Any = None,
    error: str | None = None,
    duration_ms: float | None = None,
) -> Span:
    """Record a tool call in the current trace. Returns the created span."""
    tc = ToolCall(
        name=name,
        arguments=arguments or {},
        result=result,
        error=error,
        duration_ms=duration_ms,
    )
    span = Span(
        name=f"tool:{name}",
        type=SpanType.TOOL_CALL,
        input=arguments,
        output=result,
        error=error,
        tool_call=tc,
        started_at=datetime.now(timezone.utc),
        ended_at=datetime.now(timezone.utc),
    )

    _attach_span(span, _current_span.get(), _current_trace.get())
    return span


def record_llm_call(
    input: Any = None,
    output: Any = None,
    model: str | None = None,
    token_usage: dict[str, int] | None = None,
    metadata: dict[str, Any] | None = None,
) -> Span:
    """Record an LLM call in the current trace. Returns the created span."""
    meta = {**(metadata or {})}
    if model is not None:
        meta["model"] = model
    if token_usage:
        meta["token_usage"] = token_usage

    span = Span(
        name=f"llm:{model or 'unknown'}",
        type=SpanType.LLM_CALL,
        input=input,
        output=output,
        started_at=datetime.now(timezone.utc),
        ended_at=datetime.now(timezone.utc),
        metadata=meta,
    )

    _attach_span(span, _current_span.get(), _current_trace.get())
    return span


def record_error(error: str | Exception, metadata: dict[str, Any] | None = None) -> Span:
    """Record an error in the current trace. Returns the created span."""
    span = Span(
        name="error",
        type=SpanType.ERROR,
        error=str(error),
        started_at=datetime.now(timezone.utc),
        ended_at=datetime.now(timezone.utc),
        metadata=metadata or {},
    )

    _attach_span(span, _current_span.get(), _current_trace.get())
    return span
