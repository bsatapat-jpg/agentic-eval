"""Skill Adherence evaluator -- composite scoring pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..models import EvalResult, MetricResult, SkillSpec, Trace, Verdict
from ..metrics.base import BaseMetric
from ..metrics.task_completion import TaskCompletionMetric
from ..metrics.instruction_fidelity import InstructionFidelityMetric
from ..metrics.output_correctness import OutputCorrectnessMetric
from ..metrics.step_deviation import StepDeviationMetric
from ..metrics.tool_selection import ToolSelectionMetric
from ..metrics.error_recovery import ErrorRecoveryMetric
from ..metrics.action_economy import ActionEconomyMetric
from ..metrics.tool_response_alignment import ToolResponseAlignmentMetric
from ..metrics.grounding import GroundednessMetric
from ..metrics.trajectory_optimality import TrajectoryOptimalityMetric
from ..metrics.hallucination import HallucinationMetric
from ..skill_parser import parse_skill


class SkillAdherenceEvaluator:
    """Full skill adherence scoring pipeline.

    Combines all Tier 1 + Tier 2 + Tier 3 metrics into a single weighted
    grade. Provides a comprehensive EvalResult with detailed per-metric
    breakdown including trajectory-aware metrics for MCP/RAG validation.

    Usage:
        evaluator = SkillAdherenceEvaluator("./SKILL.md")
        result = evaluator.evaluate(trace, expected_output="...")
        print(result.overall_score)  # 0.0 - 1.0
        print(result.verdict)        # pass / fail / partial
    """

    DEFAULT_WEIGHTS = {
        # Tier 1: Non-negotiable
        "task_completion": 0.15,
        "instruction_fidelity": 0.15,
        "output_correctness": 0.10,
        "groundedness": 0.10,
        "hallucination": 0.10,
        # Tier 2: Diagnostic
        "step_deviation": 0.08,
        "tool_selection": 0.08,
        "tool_response_alignment": 0.08,
        "error_recovery": 0.05,
        "trajectory_optimality": 0.07,
        # Tier 3: Efficiency
        "action_economy": 0.04,
    }

    GRADE_THRESHOLDS = {
        "A": 0.90,
        "B": 0.80,
        "C": 0.70,
        "D": 0.60,
        "F": 0.0,
    }

    def __init__(
        self,
        skill: str | Path | SkillSpec | None = None,
        weights: dict[str, float] | None = None,
        thresholds: dict[str, float] | None = None,
        use_llm_judge: bool = False,
    ) -> None:
        if isinstance(skill, SkillSpec):
            self.skill_spec = skill
        elif skill is not None:
            self.skill_spec = parse_skill(skill)
        else:
            self.skill_spec = None

        self.weights = weights or self.DEFAULT_WEIGHTS.copy()
        self.thresholds = thresholds or {}
        self.use_llm_judge = use_llm_judge

        self._metrics: list[BaseMetric] = [
            TaskCompletionMetric(use_llm_judge=use_llm_judge),
            InstructionFidelityMetric(use_llm_judge=use_llm_judge),
            OutputCorrectnessMetric(),
            GroundednessMetric(use_llm_judge=use_llm_judge),
            HallucinationMetric(use_llm_judge=use_llm_judge),
            StepDeviationMetric(),
            ToolSelectionMetric(),
            ToolResponseAlignmentMetric(use_llm_judge=use_llm_judge),
            ErrorRecoveryMetric(),
            TrajectoryOptimalityMetric(),
            ActionEconomyMetric(),
        ]

    def evaluate(
        self,
        trajectory: Trace,
        expected_output: Any = None,
        skill_spec: SkillSpec | None = None,
    ) -> EvalResult:
        """Run all metrics and produce a comprehensive EvalResult."""
        spec = skill_spec or self.skill_spec

        metric_results: list[MetricResult] = []
        for metric in self._metrics:
            try:
                result = metric.score(
                    trajectory=trajectory,
                    skill_spec=spec,
                    expected_output=expected_output,
                )
                if metric.name in self.thresholds:
                    result.threshold = self.thresholds[metric.name]
                    result.passed = result.score >= self.thresholds[metric.name]
                metric_results.append(result)
            except Exception as exc:
                metric_results.append(
                    MetricResult(
                        metric_name=metric.name,
                        score=0.0,
                        passed=False,
                        reason=f"Metric error: {exc}",
                    )
                )

        overall = self._compute_weighted_score(metric_results)
        verdict = self._determine_verdict(metric_results, overall)
        grade = self._compute_grade(overall)

        return EvalResult(
            skill_name=spec.name if spec else "",
            skill_path=spec.file_path if spec else None,
            skill_version_hash=spec.version_hash if spec else "",
            verdict=verdict,
            overall_score=overall,
            metric_results=metric_results,
            trace=trajectory,
            metadata={"grade": grade, "weights": self.weights},
        )

    def _compute_weighted_score(self, results: list[MetricResult]) -> float:
        total_weight = 0.0
        weighted_sum = 0.0
        for mr in results:
            w = self.weights.get(mr.metric_name, 0.1)
            weighted_sum += mr.score * w
            total_weight += w
        return weighted_sum / total_weight if total_weight > 0 else 0.0

    def _determine_verdict(
        self, results: list[MetricResult], overall: float
    ) -> Verdict:
        tier1_names = {
            "task_completion", "instruction_fidelity", "output_correctness",
            "groundedness", "hallucination",
        }
        tier1_results = [r for r in results if r.metric_name in tier1_names]

        if any(not r.passed for r in tier1_results):
            return Verdict.FAIL
        if overall >= 0.7:
            return Verdict.PASS
        if overall >= 0.4:
            return Verdict.PARTIAL
        return Verdict.FAIL

    def _compute_grade(self, score: float) -> str:
        for grade, threshold in self.GRADE_THRESHOLDS.items():
            if score >= threshold:
                return grade
        return "F"
