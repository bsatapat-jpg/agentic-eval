"""Tests for async tracer and decorator support."""

import asyncio

import pytest

from skora import evaluate, trace_skill, Trace
from skora.tracer import (
    async_trace_context,
    async_span_context,
    record_tool_call,
    SpanType,
)


@pytest.fixture
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


class TestAsyncTraceContext:
    def test_creates_trace(self, event_loop):
        async def _run():
            async with async_trace_context(input="hello") as t:
                assert isinstance(t, Trace)
                assert t.input == "hello"
            assert t.ended_at is not None
            return t

        t = event_loop.run_until_complete(_run())
        assert t.output is None

    def test_with_spans(self, event_loop):
        async def _run():
            async with async_trace_context(input="q") as t:
                async with async_span_context("step1", SpanType.TOOL_CALL) as s:
                    s.output = "done"
                record_tool_call("test_tool", result="ok")
                t.output = "result"
            return t

        t = event_loop.run_until_complete(_run())
        assert len(t.spans) == 2
        assert t.output == "result"


class TestAsyncTraceSkillDecorator:
    def test_async_trace(self, event_loop):
        @trace_skill()
        async def my_fn(x):
            record_tool_call("tool", result=x)
            return x * 2

        result = event_loop.run_until_complete(my_fn(5))
        assert result == 10
        assert my_fn._last_trace is not None
        assert my_fn._last_trace.output == 10


class TestAsyncEvaluateDecorator:
    def test_async_eval(self, event_loop):
        @evaluate(metrics=["task_completion"])
        async def my_fn(x):
            return f"result: {x}"

        result = event_loop.run_until_complete(my_fn("test"))
        assert result == "result: test"
        assert my_fn.last_eval is not None
        assert my_fn.last_eval.overall_score > 0
