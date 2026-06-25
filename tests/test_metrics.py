"""Tests for evaluation metrics."""

import pytest
from datetime import datetime, timezone

from agentic_eval.models import (
    MetricResult, SkillSpec, SkillStep, Span, SpanType,
    Trace, ToolCall,
)
from agentic_eval.metrics.task_completion import TaskCompletionMetric
from agentic_eval.metrics.instruction_fidelity import InstructionFidelityMetric
from agentic_eval.metrics.output_correctness import OutputCorrectnessMetric
from agentic_eval.metrics.step_deviation import StepDeviationMetric
from agentic_eval.metrics.tool_selection import ToolSelectionMetric
from agentic_eval.metrics.error_recovery import ErrorRecoveryMetric
from agentic_eval.metrics.action_economy import ActionEconomyMetric


def _make_trace(output=None, tool_calls=None, errors=None):
    """Helper to build test traces."""
    spans = []
    now = datetime.now(timezone.utc)

    for tc in (tool_calls or []):
        spans.append(Span(
            name=f"tool:{tc}",
            type=SpanType.TOOL_CALL,
            tool_call=ToolCall(name=tc, arguments={}, result="ok"),
            started_at=now,
            ended_at=now,
        ))

    for err in (errors or []):
        spans.append(Span(
            name="error",
            type=SpanType.ERROR,
            error=err,
            started_at=now,
            ended_at=now,
        ))

    return Trace(output=output, spans=spans, started_at=now, ended_at=now)


def _make_skill_spec(tools=None, steps=None, constraints=None):
    """Helper to build test skill specs."""
    step_objs = []
    for i, s in enumerate(steps or []):
        step_objs.append(SkillStep(
            order=i + 1,
            description=s if isinstance(s, str) else s["description"],
            expected_tools=s.get("tools", []) if isinstance(s, dict) else [],
        ))

    return SkillSpec(
        name="test-skill",
        expected_tools=tools or [],
        steps=step_objs,
        constraints=constraints or [],
    )


class TestTaskCompletion:
    def test_success_with_output(self):
        trace = _make_trace(output="done")
        m = TaskCompletionMetric()
        result = m.score(trace)
        assert result.score == 1.0
        assert result.passed

    def test_failure_no_output(self):
        trace = _make_trace(output=None)
        m = TaskCompletionMetric()
        result = m.score(trace)
        assert result.score == 0.0
        assert not result.passed

    def test_partial_with_errors(self):
        trace = _make_trace(output="partial", errors=["something went wrong"])
        m = TaskCompletionMetric()
        result = m.score(trace)
        assert result.score == 0.5

    def test_expected_output_match(self):
        trace = _make_trace(output="hello world")
        m = TaskCompletionMetric()
        result = m.score(trace, expected_output="Hello World")
        assert result.score == 1.0

    def test_expected_output_mismatch(self):
        trace = _make_trace(output="wrong answer")
        m = TaskCompletionMetric()
        result = m.score(trace, expected_output="correct answer")
        assert result.score < 0.5


class TestToolSelection:
    def test_perfect_selection(self):
        trace = _make_trace(tool_calls=["read_file", "write_file"])
        spec = _make_skill_spec(tools=["read_file", "write_file"])
        m = ToolSelectionMetric()
        result = m.score(trace, skill_spec=spec)
        assert result.score == 1.0

    def test_missing_tool(self):
        trace = _make_trace(tool_calls=["read_file"])
        spec = _make_skill_spec(tools=["read_file", "write_file"])
        m = ToolSelectionMetric()
        result = m.score(trace, skill_spec=spec)
        assert result.score < 1.0

    def test_extra_tool(self):
        trace = _make_trace(tool_calls=["read_file", "write_file", "delete_file"])
        spec = _make_skill_spec(tools=["read_file", "write_file"])
        m = ToolSelectionMetric()
        result = m.score(trace, skill_spec=spec)
        assert result.score < 1.0

    def test_no_expected_tools(self):
        trace = _make_trace(tool_calls=["anything"])
        spec = _make_skill_spec(tools=[])
        m = ToolSelectionMetric()
        result = m.score(trace, skill_spec=spec)
        assert result.score == 1.0


class TestErrorRecovery:
    def test_no_errors(self):
        trace = _make_trace(output="done")
        m = ErrorRecoveryMetric()
        result = m.score(trace)
        assert result.score == 1.0

    def test_recovery_after_error(self):
        trace = _make_trace(output="done", errors=["transient failure"])
        m = ErrorRecoveryMetric()
        result = m.score(trace)
        assert result.score > 0.5

    def test_unrecovered_errors(self):
        trace = _make_trace(output=None, errors=["fatal error"])
        m = ErrorRecoveryMetric()
        result = m.score(trace)
        assert result.score < 0.5


class TestOutputCorrectness:
    def test_exact_match(self):
        trace = _make_trace(output="hello world")
        m = OutputCorrectnessMetric()
        result = m.score(trace, expected_output="hello world")
        assert result.score == 1.0

    def test_no_expected(self):
        trace = _make_trace(output="something")
        m = OutputCorrectnessMetric()
        result = m.score(trace)
        assert result.score == 1.0

    def test_no_output(self):
        trace = _make_trace(output=None)
        m = OutputCorrectnessMetric()
        result = m.score(trace)
        assert result.score == 0.0


class TestActionEconomy:
    def test_optimal(self):
        trace = _make_trace(tool_calls=["a", "b", "c"])
        spec = _make_skill_spec(steps=["step1", "step2", "step3"])
        m = ActionEconomyMetric()
        result = m.score(trace, skill_spec=spec)
        assert result.score == 1.0

    def test_inefficient(self):
        trace = _make_trace(tool_calls=["a", "b", "c", "d", "e", "f"])
        spec = _make_skill_spec(steps=["step1", "step2", "step3"])
        m = ActionEconomyMetric()
        result = m.score(trace, skill_spec=spec)
        assert result.score == 0.5
