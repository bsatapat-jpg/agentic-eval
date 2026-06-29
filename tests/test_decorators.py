"""Tests for decorators and tracer."""

import pytest

from skora import evaluate, trace_skill, Trace
from skora.tracer import trace_context, span_context, record_tool_call, SpanType


class TestTraceContext:
    def test_creates_trace(self):
        with trace_context(input="hello") as t:
            assert isinstance(t, Trace)
            assert t.input == "hello"

    def test_records_output(self):
        with trace_context() as t:
            t.output = "result"
        assert t.output == "result"
        assert t.ended_at is not None

    def test_nested_spans(self):
        with trace_context() as t:
            with span_context("step1", SpanType.TOOL_CALL) as s1:
                s1.output = "done1"
            with span_context("step2", SpanType.AGENT_STEP) as s2:
                s2.output = "done2"

        assert len(t.spans) == 2
        assert t.spans[0].name == "step1"
        assert t.spans[1].name == "step2"

    def test_child_spans(self):
        with trace_context() as t:
            with span_context("parent") as parent:
                with span_context("child") as child:
                    child.output = "child_done"
                parent.output = "parent_done"

        assert len(t.spans) == 1
        assert t.spans[0].name == "parent"
        assert len(t.spans[0].children) == 1
        assert t.spans[0].children[0].name == "child"

    def test_record_tool_call(self):
        with trace_context() as t:
            record_tool_call("read_file", {"path": "test.py"}, result="content")

        assert len(t.spans) == 1
        assert t.spans[0].tool_call is not None
        assert t.spans[0].tool_call.name == "read_file"

    def test_tool_calls_property(self):
        with trace_context() as t:
            record_tool_call("tool_a", result="a")
            record_tool_call("tool_b", result="b")

        assert len(t.tool_calls) == 2
        assert t.tool_calls[0].name == "tool_a"


class TestTraceSkillDecorator:
    def test_captures_trace(self):
        @trace_skill()
        def my_fn(x):
            record_tool_call("test_tool", {"x": x}, result=x * 2)
            return x * 2

        result = my_fn(5)
        assert result == 10
        assert my_fn._last_trace is not None
        assert my_fn._last_trace.output == 10

    def test_with_skill_content(self):
        skill_md = "---\nname: test\n---\n# Test\nA test skill."

        @trace_skill(skill=skill_md)
        def my_fn(x):
            return x

        my_fn("hello")
        assert my_fn._last_skill_spec is not None
        assert my_fn._last_skill_spec.name == "test"


class TestEvaluateDecorator:
    def test_produces_eval_result(self):
        @evaluate(metrics=["task_completion"])
        def my_fn(x):
            return f"result: {x}"

        result = my_fn("test")
        assert result == "result: test"
        assert my_fn.last_eval is not None
        assert my_fn.last_eval.overall_score > 0

    def test_with_expected_output(self):
        @evaluate(
            metrics=["task_completion", "output_correctness"],
            expected_output="hello world",
        )
        def my_fn(x):
            return "hello world"

        my_fn("test")
        assert my_fn.last_eval.overall_score == 1.0

    def test_with_thresholds(self):
        @evaluate(
            metrics=["task_completion"],
            thresholds={"task_completion": 0.9},
        )
        def my_fn(x):
            return x

        my_fn("test")
        assert my_fn.last_eval is not None
