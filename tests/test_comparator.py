"""Tests for skill comparator."""

import pytest
from datetime import datetime, timezone

from scora.models import (
    ComparisonVerdict, SkillSpec, SkillStep,
    Span, SpanType, Trace, ToolCall,
)
from scora.evaluators.comparator import SkillComparator


def _make_trace(output=None, tool_calls=None):
    spans = []
    now = datetime.now(timezone.utc)
    for tc in (tool_calls or []):
        spans.append(Span(
            name=f"tool:{tc}", type=SpanType.TOOL_CALL,
            tool_call=ToolCall(name=tc, arguments={}, result="ok"),
            started_at=now, ended_at=now,
        ))
    return Trace(output=output, spans=spans, started_at=now, ended_at=now)


class TestSkillComparator:
    def test_compare_with_traces(self):
        spec_a = SkillSpec(name="v1", expected_tools=["read_file"])
        spec_b = SkillSpec(name="v2", expected_tools=["read_file", "analyze"])

        traces_a = [_make_trace(output="result_a", tool_calls=["read_file"])]
        traces_b = [_make_trace(output="result_b", tool_calls=["read_file", "analyze"])]

        comparator = SkillComparator()
        result = comparator.compare(
            skill_a=spec_a, skill_b=spec_b,
            traces_a=traces_a, traces_b=traces_b,
        )

        assert result.verdict in [
            ComparisonVerdict.A_BETTER,
            ComparisonVerdict.B_BETTER,
            ComparisonVerdict.NO_DIFFERENCE,
        ]
        assert len(result.per_metric) > 0

    def test_compare_with_agent_fn(self):
        spec_a = SkillSpec(name="v1")
        spec_b = SkillSpec(name="v2")

        def agent(inp):
            return f"processed: {inp}"

        comparator = SkillComparator()
        result = comparator.compare(
            skill_a=spec_a, skill_b=spec_b,
            agent_fn=agent,
            test_inputs=["input1", "input2"],
            trials=1,
        )

        assert result.trials > 0
        assert len(result.eval_results_a) > 0
        assert len(result.eval_results_b) > 0

    def test_no_inputs_raises(self):
        spec_a = SkillSpec(name="v1")
        spec_b = SkillSpec(name="v2")

        comparator = SkillComparator()
        with pytest.raises(ValueError, match="Provide either"):
            comparator.compare(skill_a=spec_a, skill_b=spec_b)
