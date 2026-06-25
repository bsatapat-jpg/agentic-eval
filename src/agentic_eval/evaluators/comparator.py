"""Skill Comparator -- A/B testing between skill versions."""

from __future__ import annotations

import statistics
from pathlib import Path
from typing import Any, Callable

from ..models import (
    ComparisonMetricResult,
    ComparisonResult,
    ComparisonVerdict,
    EvalResult,
    SkillSpec,
    Trace,
)
from ..skill_parser import parse_skill
from .skill_adherence import SkillAdherenceEvaluator


class SkillComparator:
    """Compare two skill versions by running them through the same test cases.

    Usage:
        comparator = SkillComparator()
        result = comparator.compare(
            skill_a="./skills/v1/SKILL.md",
            skill_b="./skills/v2/SKILL.md",
            agent_fn=my_agent,
            test_inputs=["query1", "query2", "query3"],
            trials=5,
        )
        print(result.verdict)  # a_better / b_better / no_difference
        print(result.lift)     # score delta
    """

    SIGNIFICANT_LIFT = 0.05

    def compare(
        self,
        skill_a: str | Path | SkillSpec,
        skill_b: str | Path | SkillSpec,
        agent_fn: Callable | None = None,
        test_inputs: list[Any] | None = None,
        expected_outputs: list[Any] | None = None,
        traces_a: list[Trace] | None = None,
        traces_b: list[Trace] | None = None,
        trials: int = 1,
        weights: dict[str, float] | None = None,
    ) -> ComparisonResult:
        """Compare two skill versions.

        Provide either:
        - agent_fn + test_inputs: will run the agent with each skill and capture traces
        - traces_a + traces_b: pre-recorded traces to evaluate

        Args:
            skill_a: First skill version (baseline).
            skill_b: Second skill version (candidate).
            agent_fn: Agent function to run (decorated with @trace_skill).
            test_inputs: Inputs to test with.
            expected_outputs: Expected outputs per test input.
            traces_a: Pre-recorded traces for skill A.
            traces_b: Pre-recorded traces for skill B.
            trials: Number of times to repeat each test input.
            weights: Metric weights for scoring.

        Returns:
            ComparisonResult with verdict and per-metric breakdown.
        """
        spec_a = self._resolve_skill(skill_a)
        spec_b = self._resolve_skill(skill_b)

        eval_a = SkillAdherenceEvaluator(skill=spec_a, weights=weights)
        eval_b = SkillAdherenceEvaluator(skill=spec_b, weights=weights)

        if traces_a and traces_b:
            results_a = self._evaluate_traces(eval_a, traces_a, expected_outputs)
            results_b = self._evaluate_traces(eval_b, traces_b, expected_outputs)
        elif agent_fn and test_inputs:
            results_a = self._run_and_evaluate(
                eval_a, spec_a, agent_fn, test_inputs, expected_outputs, trials
            )
            results_b = self._run_and_evaluate(
                eval_b, spec_b, agent_fn, test_inputs, expected_outputs, trials
            )
        else:
            raise ValueError(
                "Provide either (agent_fn + test_inputs) or (traces_a + traces_b)"
            )

        return self._build_comparison(spec_a, spec_b, results_a, results_b)

    def _resolve_skill(self, skill: str | Path | SkillSpec) -> SkillSpec:
        if isinstance(skill, SkillSpec):
            return skill
        return parse_skill(skill)

    def _evaluate_traces(
        self,
        evaluator: SkillAdherenceEvaluator,
        traces: list[Trace],
        expected_outputs: list[Any] | None,
    ) -> list[EvalResult]:
        results: list[EvalResult] = []
        for i, trace in enumerate(traces):
            expected = expected_outputs[i] if expected_outputs and i < len(expected_outputs) else None
            result = evaluator.evaluate(trace, expected_output=expected)
            results.append(result)
        return results

    def _run_and_evaluate(
        self,
        evaluator: SkillAdherenceEvaluator,
        skill_spec: SkillSpec,
        agent_fn: Callable,
        test_inputs: list[Any],
        expected_outputs: list[Any] | None,
        trials: int,
    ) -> list[EvalResult]:
        from ..tracer import trace_context

        results: list[EvalResult] = []

        for trial in range(trials):
            for i, inp in enumerate(test_inputs):
                expected = (
                    expected_outputs[i]
                    if expected_outputs and i < len(expected_outputs)
                    else None
                )

                with trace_context(input=inp) as trace:
                    try:
                        output = agent_fn(inp)
                        trace.output = output
                    except Exception as exc:
                        trace.output = None
                        from ..tracer import record_error
                        record_error(exc)

                result = evaluator.evaluate(trace, expected_output=expected)
                results.append(result)

        return results

    def _build_comparison(
        self,
        spec_a: SkillSpec,
        spec_b: SkillSpec,
        results_a: list[EvalResult],
        results_b: list[EvalResult],
    ) -> ComparisonResult:
        score_a = (
            statistics.mean([r.overall_score for r in results_a]) if results_a else 0.0
        )
        score_b = (
            statistics.mean([r.overall_score for r in results_b]) if results_b else 0.0
        )
        lift = score_b - score_a

        per_metric = self._compute_per_metric(results_a, results_b)

        if lift >= self.SIGNIFICANT_LIFT:
            verdict = ComparisonVerdict.B_BETTER
        elif lift <= -self.SIGNIFICANT_LIFT:
            verdict = ComparisonVerdict.A_BETTER
        else:
            verdict = ComparisonVerdict.NO_DIFFERENCE

        return ComparisonResult(
            skill_a_path=spec_a.file_path or "",
            skill_b_path=spec_b.file_path or "",
            skill_a_hash=spec_a.version_hash,
            skill_b_hash=spec_b.version_hash,
            verdict=verdict,
            lift=round(lift, 4),
            per_metric=per_metric,
            trials=len(results_a),
            eval_results_a=results_a,
            eval_results_b=results_b,
        )

    def _compute_per_metric(
        self, results_a: list[EvalResult], results_b: list[EvalResult]
    ) -> list[ComparisonMetricResult]:
        metric_scores_a: dict[str, list[float]] = {}
        metric_scores_b: dict[str, list[float]] = {}

        for r in results_a:
            for mr in r.metric_results:
                metric_scores_a.setdefault(mr.metric_name, []).append(mr.score)

        for r in results_b:
            for mr in r.metric_results:
                metric_scores_b.setdefault(mr.metric_name, []).append(mr.score)

        all_metrics = set(metric_scores_a.keys()) | set(metric_scores_b.keys())
        per_metric: list[ComparisonMetricResult] = []

        for name in sorted(all_metrics):
            avg_a = statistics.mean(metric_scores_a.get(name, [0.0]))
            avg_b = statistics.mean(metric_scores_b.get(name, [0.0]))
            delta = avg_b - avg_a
            winner = ""
            if delta > 0.01:
                winner = "b"
            elif delta < -0.01:
                winner = "a"

            per_metric.append(
                ComparisonMetricResult(
                    metric_name=name,
                    score_a=round(avg_a, 4),
                    score_b=round(avg_b, 4),
                    delta=round(delta, 4),
                    winner=winner,
                )
            )

        return per_metric
