"""Regression tests for bugs found during comprehensive audit.

Each test targets a specific bug fix to prevent regressions.
"""

import json
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from agentic_eval.models import (
    ComparisonResult,
    EvalResult,
    MetricResult,
    SecurityFinding,
    SecurityReport,
    Severity,
    SkillSpec,
    SkillStep,
    Span,
    SpanType,
    ToolCall,
    Trace,
    Verdict,
)


# ────────────────────────────────────────────────────
# BUG 1: SecurityEvaluator.scan_skill crashes on long strings
# ────────────────────────────────────────────────────

class TestSecurityEvaluatorLongStrings:
    """The SecurityEvaluator was passing raw markdown to Path(), which
    raises OSError on strings > 260 chars or with newlines."""

    def test_scan_long_inline_markdown(self):
        from agentic_eval.evaluators.security import SecurityEvaluator

        long_content = "# My Skill\n\n" + "This is a test. " * 100
        assert len(long_content) > 260

        evaluator = SecurityEvaluator()
        report = evaluator.scan_skill(long_content)
        assert report.skill_path == "<inline>"
        assert isinstance(report.score, float)

    def test_scan_multiline_markdown(self):
        from agentic_eval.evaluators.security import SecurityEvaluator

        content = "# Skill\n\nLine 1\nLine 2\nLine 3"
        evaluator = SecurityEvaluator()
        report = evaluator.scan_skill(content)
        assert report.skill_path == "<inline>"

    def test_scan_actual_file_still_works(self, tmp_path):
        from agentic_eval.evaluators.security import SecurityEvaluator

        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text("# Test Skill\n\nA test skill.\n")

        evaluator = SecurityEvaluator()
        report = evaluator.scan_skill(str(skill_file))
        assert str(tmp_path) in report.skill_path


# ────────────────────────────────────────────────────
# BUG 2: store.save() crashes on non-serializable metadata
# ────────────────────────────────────────────────────

class TestStoreSerializationSafety:
    """json.dumps without default=str would crash on datetime or
    custom objects in metadata."""

    def test_save_with_datetime_metadata(self, tmp_path):
        from agentic_eval.store import ResultStore

        db = tmp_path / "test.db"
        with ResultStore(db) as store:
            result = EvalResult(
                skill_name="test",
                verdict=Verdict.PASS,
                overall_score=0.9,
                metadata={"timestamp": datetime.now(timezone.utc), "path": Path("/tmp")},
            )
            saved_id = store.save(result)
            assert saved_id == result.id

            rows = store.query(skill_name="test")
            assert len(rows) == 1

    def test_save_security_report_with_complex_data(self, tmp_path):
        from agentic_eval.store import ResultStore

        db = tmp_path / "test.db"
        with ResultStore(db) as store:
            report = SecurityReport(
                skill_path="/test",
                skill_name="test",
                score=0.8,
                grade="B",
                findings=[
                    SecurityFinding(
                        severity=Severity.WARNING,
                        category="test",
                        description="test finding",
                    )
                ],
            )
            store.save_security_report(report)

            reports = store.get_security_reports()
            assert len(reports) == 1


# ────────────────────────────────────────────────────
# BUG 3: Trace.duration_ms can be negative
# ────────────────────────────────────────────────────

class TestTraceDurationClamping:
    """If ended_at < started_at (clock skew, bad data), duration
    should be clamped to 0, not negative."""

    def test_negative_duration_clamped_to_zero(self):
        now = datetime.now(timezone.utc)
        trace = Trace(
            started_at=now,
            ended_at=now - timedelta(seconds=5),
        )
        assert trace.duration_ms == 0.0

    def test_positive_duration_works_normally(self):
        now = datetime.now(timezone.utc)
        trace = Trace(
            started_at=now,
            ended_at=now + timedelta(seconds=2),
        )
        assert trace.duration_ms == pytest.approx(2000.0, abs=10)


# ────────────────────────────────────────────────────
# BUG 4: action_economy counts llm_call spans as action steps
# ────────────────────────────────────────────────────

class TestActionEconomyLLMNotCounted:
    """LLM calls should not inflate the actual step count when
    compared to the optimal (which counts tool/agent steps only)."""

    def test_llm_calls_not_counted_as_steps(self):
        from agentic_eval.metrics.action_economy import ActionEconomyMetric

        now = datetime.now(timezone.utc)
        spans = [
            Span(name="tool:read", type=SpanType.TOOL_CALL,
                 tool_call=ToolCall(name="read", arguments={}),
                 started_at=now, ended_at=now),
            Span(name="llm:gpt-4", type=SpanType.LLM_CALL,
                 started_at=now, ended_at=now),
            Span(name="tool:write", type=SpanType.TOOL_CALL,
                 tool_call=ToolCall(name="write", arguments={}),
                 started_at=now, ended_at=now),
            Span(name="llm:gpt-4", type=SpanType.LLM_CALL,
                 started_at=now, ended_at=now),
        ]
        trace = Trace(spans=spans, started_at=now, ended_at=now)
        spec = SkillSpec(
            name="test",
            steps=[
                SkillStep(order=1, description="read file"),
                SkillStep(order=2, description="write file"),
            ],
        )

        metric = ActionEconomyMetric()
        result = metric.score(trace, skill_spec=spec)
        assert result.score == 1.0, (
            f"LLM calls inflated step count: {result.details}"
        )


# ────────────────────────────────────────────────────
# BUG 5: record_llm_call puts model=None in metadata
# ────────────────────────────────────────────────────

class TestRecordLLMCallMetadata:
    """When model is None, it should not appear in metadata."""

    def test_no_model_key_when_none(self):
        from agentic_eval.tracer import record_llm_call, trace_context

        with trace_context() as t:
            span = record_llm_call(input="hi", output="hello")
            assert "model" not in span.metadata

    def test_model_key_present_when_set(self):
        from agentic_eval.tracer import record_llm_call, trace_context

        with trace_context() as t:
            span = record_llm_call(input="hi", output="hello", model="gpt-4")
            assert span.metadata["model"] == "gpt-4"


# ────────────────────────────────────────────────────
# BUG 6: api.run_evaluation ignores metrics parameter
# ────────────────────────────────────────────────────

class TestRunEvaluationMetricsFilter:
    """The metrics parameter was accepted but never used, so all
    metrics ran regardless of what was requested."""

    def test_metrics_filter_applied(self):
        from agentic_eval.api import run_evaluation

        trace = Trace(input="test", output="result")
        result = run_evaluation(trace, metrics=["task_completion"])

        metric_names = {mr.metric_name for mr in result.metric_results}
        assert metric_names == {"task_completion"}, (
            f"Expected only task_completion, got: {metric_names}"
        )

    def test_metrics_filter_multiple(self):
        from agentic_eval.api import run_evaluation

        trace = Trace(input="test", output="result")
        result = run_evaluation(
            trace, metrics=["task_completion", "output_correctness"]
        )

        metric_names = {mr.metric_name for mr in result.metric_results}
        assert metric_names == {"task_completion", "output_correctness"}

    def test_metrics_none_runs_all(self):
        from agentic_eval.api import run_evaluation

        trace = Trace(input="test", output="result")
        result = run_evaluation(trace, metrics=None)

        assert len(result.metric_results) == 11


# ────────────────────────────────────────────────────
# BUG 7: ResultStore not safe after close / double-close
# ────────────────────────────────────────────────────

class TestStoreCloseGuard:
    """Closing the store twice should not raise, and _conn should
    be None after close."""

    def test_double_close_no_error(self, tmp_path):
        from agentic_eval.store import ResultStore

        store = ResultStore(tmp_path / "test.db")
        store.close()
        store.close()

    def test_conn_none_after_close(self, tmp_path):
        from agentic_eval.store import ResultStore

        store = ResultStore(tmp_path / "test.db")
        store.close()
        assert store._conn is None


# ────────────────────────────────────────────────────
# BUG 8: ResultStore init leaks connection on schema failure
# ────────────────────────────────────────────────────

class TestStoreInitCleanup:
    """If _init_schema fails, the connection should be closed, not leaked."""

    def test_init_failure_cleans_up(self, tmp_path):
        from agentic_eval.store import ResultStore

        db = tmp_path / "test.db"

        conn = sqlite3.connect(str(db))
        conn.execute("CREATE TABLE eval_results (bad_schema INTEGER)")
        conn.commit()
        conn.close()

        with pytest.raises(sqlite3.OperationalError):
            ResultStore(db)


# ────────────────────────────────────────────────────
# BUG 9: OutputCorrectnessMetric uses lowercase `callable`
# ────────────────────────────────────────────────────

class TestOutputCorrectnessTypeHint:
    """The assertions parameter should accept Callable objects."""

    def test_custom_assertion_callable(self):
        from agentic_eval.metrics.output_correctness import OutputCorrectnessMetric

        def check_length(output):
            return len(output) > 3

        metric = OutputCorrectnessMetric(assertions=[check_length])
        trace = Trace(output="hello world")
        result = metric.score(trace, expected_output="hello world")
        assert result.score >= 0.5


# ────────────────────────────────────────────────────
# BUG 10: Decorator skill cache grows unboundedly
# ────────────────────────────────────────────────────

class TestDecoratorSkillCacheBounded:
    """The skill cache should use LRU eviction, not grow forever."""

    def test_lru_cache_used(self):
        from agentic_eval.decorators import _cached_parse_skill

        assert hasattr(_cached_parse_skill, "cache_info"), (
            "_cached_parse_skill should be an lru_cache-wrapped function"
        )
        info = _cached_parse_skill.cache_info()
        assert info.maxsize is not None and info.maxsize > 0


# ────────────────────────────────────────────────────
# Edge cases for metrics with empty traces
# ────────────────────────────────────────────────────

class TestMetricsEmptyTraces:
    """Metrics should handle completely empty traces gracefully."""

    def test_task_completion_empty_string_output(self):
        from agentic_eval.metrics.task_completion import TaskCompletionMetric

        trace = Trace(output="")
        result = TaskCompletionMetric().score(trace)
        assert result.score == 0.0

    def test_step_deviation_no_spans(self):
        from agentic_eval.metrics.step_deviation import StepDeviationMetric

        trace = Trace()
        spec = SkillSpec(
            name="test",
            steps=[SkillStep(order=1, description="do something")],
        )
        result = StepDeviationMetric().score(trace, skill_spec=spec)
        assert result.score == 0.0

    def test_tool_selection_no_tools_no_spec(self):
        from agentic_eval.metrics.tool_selection import ToolSelectionMetric

        trace = Trace()
        result = ToolSelectionMetric().score(trace)
        assert result.score == 1.0

    def test_error_recovery_empty_trace(self):
        from agentic_eval.metrics.error_recovery import ErrorRecoveryMetric

        trace = Trace()
        result = ErrorRecoveryMetric().score(trace)
        assert result.score == 1.0

    def test_action_economy_zero_optimal(self):
        from agentic_eval.metrics.action_economy import ActionEconomyMetric

        trace = Trace()
        result = ActionEconomyMetric(optimal_steps=0).score(trace)
        assert result.score == 1.0

    def test_instruction_fidelity_no_spec(self):
        from agentic_eval.metrics.instruction_fidelity import InstructionFidelityMetric

        trace = Trace(output="result")
        result = InstructionFidelityMetric().score(trace, skill_spec=None)
        assert result.score == 0.0
        assert not result.passed

    def test_output_correctness_none_output(self):
        from agentic_eval.metrics.output_correctness import OutputCorrectnessMetric

        trace = Trace(output=None)
        result = OutputCorrectnessMetric().score(trace, expected_output="expected")
        assert result.score == 0.0


# ────────────────────────────────────────────────────
# Adapter robustness: malformed inputs
# ────────────────────────────────────────────────────

class TestAdapterMalformedInputs:
    """Adapters should not crash on empty, None, or malformed data."""

    def test_langchain_empty_run(self):
        from agentic_eval.adapters.langchain_adapter import from_langchain

        trace = from_langchain({})
        assert isinstance(trace, Trace)

    def test_langchain_missing_child_runs(self):
        from agentic_eval.adapters.langchain_adapter import from_langchain

        trace = from_langchain({"inputs": "hello", "outputs": "world"})
        assert trace.input == "hello"
        assert trace.output == "world"

    def test_openai_empty_messages(self):
        from agentic_eval.adapters.openai_adapter import from_openai

        trace = from_openai([])
        assert isinstance(trace, Trace)
        assert trace.input is None

    def test_openai_tool_call_with_string_arguments(self):
        from agentic_eval.adapters.openai_adapter import from_openai

        messages = [
            {"role": "assistant", "content": "I'll help", "tool_calls": [
                {"id": "1", "function": {"name": "search", "arguments": '{"q": "test"}'}}
            ]},
        ]
        trace = from_openai(messages)
        tool_calls = trace.tool_calls
        assert len(tool_calls) == 1
        assert tool_calls[0].arguments == {"q": "test"}

    def test_otel_empty_spans(self):
        from agentic_eval.adapters.otel_adapter import from_otel

        trace = from_otel([])
        assert isinstance(trace, Trace)
        assert len(trace.spans) == 0

    def test_gemini_none_contents(self):
        from agentic_eval.adapters.gemini_adapter import from_gemini

        trace = from_gemini(contents=None, response=None)
        assert isinstance(trace, Trace)

    def test_gemini_empty_contents(self):
        from agentic_eval.adapters.gemini_adapter import from_gemini

        trace = from_gemini(contents=[])
        assert isinstance(trace, Trace)

    def test_gemini_contents_with_missing_parts(self):
        from agentic_eval.adapters.gemini_adapter import from_gemini

        contents = [{"role": "user", "parts": []}, {"role": "model", "parts": []}]
        trace = from_gemini(contents=contents)
        assert isinstance(trace, Trace)


# ────────────────────────────────────────────────────
# Evaluator edge cases
# ────────────────────────────────────────────────────

class TestEvaluatorEdgeCases:
    """SkillAdherenceEvaluator should handle edge cases gracefully."""

    def test_evaluate_with_no_skill_no_trace(self):
        from agentic_eval.evaluators.skill_adherence import SkillAdherenceEvaluator

        evaluator = SkillAdherenceEvaluator()
        trace = Trace()
        result = evaluator.evaluate(trace)
        assert isinstance(result, EvalResult)
        assert result.overall_score >= 0.0

    def test_evaluate_custom_weights_sum_to_nonone(self):
        from agentic_eval.evaluators.skill_adherence import SkillAdherenceEvaluator

        evaluator = SkillAdherenceEvaluator(
            weights={"task_completion": 10.0, "output_correctness": 5.0}
        )
        trace = Trace(output="result")
        result = evaluator.evaluate(trace)
        assert 0.0 <= result.overall_score <= 1.0

    def test_metric_exception_handled(self):
        from agentic_eval.evaluators.skill_adherence import SkillAdherenceEvaluator
        from agentic_eval.metrics.base import BaseMetric

        class BrokenMetric(BaseMetric):
            name = "broken"
            description = "Always throws"

            def score(self, trajectory, skill_spec=None, expected_output=None):
                raise RuntimeError("intentional failure")

        evaluator = SkillAdherenceEvaluator()
        evaluator._metrics.append(BrokenMetric())
        trace = Trace(output="result")
        result = evaluator.evaluate(trace)
        broken_results = [m for m in result.metric_results if m.metric_name == "broken"]
        assert len(broken_results) == 1
        assert broken_results[0].score == 0.0
        assert "Metric error" in broken_results[0].reason


# ────────────────────────────────────────────────────
# Assertions edge cases
# ────────────────────────────────────────────────────

class TestAssertionsEdgeCases:

    def test_assert_skill_no_trace_creates_one(self):
        from agentic_eval.assertions import assert_skill

        spec = SkillSpec(name="test", expected_tools=[])
        result = assert_skill(actual="hello", expected="hello", skill=spec)
        assert isinstance(result, EvalResult)

    def test_assert_skill_raises_on_failure(self):
        from agentic_eval.assertions import SkillAssertionError, assert_skill

        with pytest.raises(SkillAssertionError) as exc_info:
            assert_skill(
                actual=None,
                thresholds={"task_completion": 1.0},
            )
        assert exc_info.value.eval_result is not None


# ────────────────────────────────────────────────────
# Store export safety
# ────────────────────────────────────────────────────

class TestStoreExportSafety:

    def test_export_empty_db(self, tmp_path):
        from agentic_eval.store import ResultStore

        db = tmp_path / "test.db"
        output = tmp_path / "export.json"
        with ResultStore(db) as store:
            store.export_json(output)

        data = json.loads(output.read_text())
        assert "eval_results" in data
        assert "stats" in data

    def test_query_pagination(self, tmp_path):
        from agentic_eval.store import ResultStore

        db = tmp_path / "test.db"
        with ResultStore(db) as store:
            for i in range(5):
                store.save(EvalResult(
                    skill_name="test",
                    verdict=Verdict.PASS,
                    overall_score=float(i) / 10,
                ))
            page1 = store.query(limit=2, offset=0)
            page2 = store.query(limit=2, offset=2)
            assert len(page1) == 2
            assert len(page2) == 2
            assert page1[0]["id"] != page2[0]["id"]
