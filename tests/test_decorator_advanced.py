"""Tests for advanced decorator features: exception handling, unified scoring, callbacks."""

import tempfile
from pathlib import Path

import pytest

from agentic_eval import evaluate, EvalResult, Verdict
from agentic_eval.tracer import record_tool_call


class TestEvaluateExceptionHandling:
    def test_last_eval_updated_on_exception(self):
        @evaluate(metrics=["task_completion"])
        def failing_agent(x):
            raise RuntimeError("agent crashed")

        with pytest.raises(RuntimeError, match="agent crashed"):
            failing_agent("test")

        assert failing_agent.last_eval is not None
        assert failing_agent.last_eval.verdict == Verdict.FAIL

    def test_exception_recorded_in_trace(self):
        @evaluate(metrics=["task_completion", "error_recovery"])
        def failing_agent(x):
            raise ValueError("bad input")

        with pytest.raises(ValueError):
            failing_agent("test")

        trace = failing_agent._last_trace
        assert trace is not None
        assert len(trace.errors) >= 1


class TestUnifiedScoring:
    def test_uses_weighted_scoring(self):
        @evaluate(
            metrics=["task_completion", "output_correctness"],
            expected_output="hello",
        )
        def my_agent(x):
            return "hello"

        my_agent("test")
        result = my_agent.last_eval
        assert result is not None
        assert "grade" in result.metadata


class TestCallbackHook:
    def test_on_complete_called(self):
        received = []

        @evaluate(
            metrics=["task_completion"],
            on_complete=lambda r: received.append(r),
        )
        def my_agent(x):
            return "done"

        my_agent("test")
        assert len(received) == 1
        assert isinstance(received[0], EvalResult)

    def test_on_complete_called_on_exception(self):
        received = []

        @evaluate(
            metrics=["task_completion"],
            on_complete=lambda r: received.append(r),
        )
        def failing_agent(x):
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError):
            failing_agent("test")

        assert len(received) == 1
        assert received[0].verdict == Verdict.FAIL


class TestAutoSave:
    def test_auto_save_persists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")

            @evaluate(
                metrics=["task_completion"],
                auto_save=True,
                db_path=db_path,
            )
            def my_agent(x):
                return "done"

            my_agent("test")
            assert Path(db_path).exists()

            from agentic_eval.store import ResultStore
            with ResultStore(db_path) as store:
                results = store.query()
                assert len(results) == 1
