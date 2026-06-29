"""Tests for the high-level API functions and new features."""

import asyncio
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scora import (
    EvalResult,
    MetricResult,
    Trace,
    Verdict,
    batch_evaluate,
    compare_skills,
    list_metrics,
    run_evaluation,
    scan_security,
)
from scora.models import Span, SpanType, ToolCall, SkillSpec


def _make_trace(output=None, tool_calls=None):
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
    return Trace(input="test", output=output, spans=spans, started_at=now, ended_at=now)


class TestRunEvaluation:
    def test_basic_evaluation(self):
        trace = _make_trace(output="done", tool_calls=["read_file"])
        result = run_evaluation(trace)
        assert isinstance(result, EvalResult)
        assert result.overall_score > 0

    def test_with_skill_spec(self):
        trace = _make_trace(output="done")
        spec = SkillSpec(name="test-skill", steps=[], expected_tools=[])
        result = run_evaluation(trace, skill=spec)
        assert result.skill_name == "test-skill"

    def test_with_expected_output(self):
        trace = _make_trace(output="hello world")
        result = run_evaluation(trace, expected_output="hello world")
        assert result.overall_score > 0.5

    def test_with_save(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")
            trace = _make_trace(output="done")
            result = run_evaluation(trace, save=True, db_path=db_path)
            assert Path(db_path).exists()


class TestBatchEvaluate:
    def test_evaluates_multiple_traces(self):
        traces = [
            _make_trace(output="done1"),
            _make_trace(output="done2"),
            _make_trace(output="done3"),
        ]
        results = batch_evaluate(traces)
        assert len(results) == 3
        assert all(isinstance(r, EvalResult) for r in results)

    def test_with_expected_outputs(self):
        traces = [
            _make_trace(output="hello"),
            _make_trace(output="world"),
        ]
        results = batch_evaluate(
            traces,
            expected_outputs=["hello", "world"],
        )
        assert len(results) == 2


class TestListMetrics:
    def test_returns_all_metrics(self):
        metrics = list_metrics()
        assert len(metrics) >= 7
        names = {m["name"] for m in metrics}
        assert "task_completion" in names
        assert "instruction_fidelity" in names
        assert "output_correctness" in names
        assert "step_deviation" in names
        assert "tool_selection" in names
        assert "error_recovery" in names
        assert "action_economy" in names

    def test_metric_has_description(self):
        metrics = list_metrics()
        for m in metrics:
            assert "name" in m
            assert "description" in m
            assert "tier" in m
            assert len(m["description"]) > 0


class TestScanSecurity:
    def test_scans_skill_content(self, tmp_path):
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text("# Safe Skill\n\nDo safe things.\n")
        report = scan_security(str(skill_file))
        assert report.grade in ("A", "B", "C", "D", "F")
        assert report.score >= 0.0


class TestCompareSkills:
    def test_compare_with_traces(self):
        spec_a = SkillSpec(name="v1", raw_content="# v1")
        spec_b = SkillSpec(name="v2", raw_content="# v2")

        traces_a = [_make_trace(output="done")]
        traces_b = [_make_trace(output="also done")]

        result = compare_skills(
            skill_a=spec_a,
            skill_b=spec_b,
            traces_a=traces_a,
            traces_b=traces_b,
        )
        assert result.verdict is not None
        assert isinstance(result.lift, float)
