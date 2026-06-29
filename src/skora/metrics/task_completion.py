"""Task Completion metric -- does the skill actually work?"""

from __future__ import annotations

from typing import Any

from ..models import MetricResult, SkillSpec, Trace
from .base import BaseMetric


class TaskCompletionMetric(BaseMetric):
    """Measures whether the agent completed its task successfully.

    Scoring logic:
    - 1.0 if the trace has an output and no unrecovered errors
    - 0.5 if the trace has output but also has errors (partial completion)
    - 0.0 if the trace has no output or only errors

    For richer evaluation, use with an LLM judge by setting use_llm_judge=True.
    """

    name = "task_completion"
    description = "Binary per attempt: was the goal achieved?"
    tier = 1

    def __init__(self, use_llm_judge: bool = False) -> None:
        self.use_llm_judge = use_llm_judge

    def score(
        self,
        trajectory: Trace,
        skill_spec: SkillSpec | None = None,
        expected_output: Any = None,
    ) -> MetricResult:
        if self.use_llm_judge and skill_spec:
            return self._score_with_llm(trajectory, skill_spec, expected_output)
        return self._score_heuristic(trajectory, skill_spec, expected_output)

    def _score_heuristic(
        self,
        trajectory: Trace,
        skill_spec: SkillSpec | None,
        expected_output: Any,
    ) -> MetricResult:
        has_output = trajectory.output is not None and trajectory.output != ""
        errors = trajectory.errors
        has_errors = len(errors) > 0

        if expected_output is not None and has_output:
            if self._outputs_match(trajectory.output, expected_output):
                score = 1.0
                reason = "Output matches expected result"
            else:
                score = 0.3
                reason = "Output produced but does not match expected result"
        elif has_output and not has_errors:
            score = 1.0
            reason = "Task completed successfully with output and no errors"
        elif has_output and has_errors:
            score = 0.5
            reason = f"Task completed with output but encountered {len(errors)} error(s)"
        elif not has_output and has_errors:
            score = 0.0
            reason = f"Task failed with {len(errors)} error(s) and no output"
        else:
            score = 0.0
            reason = "No output produced"

        return MetricResult(
            metric_name=self.name,
            score=score,
            passed=score >= 0.5,
            reason=reason,
            details={
                "has_output": has_output,
                "error_count": len(errors),
                "output_type": type(trajectory.output).__name__ if has_output else None,
            },
        )

    def _score_with_llm(
        self,
        trajectory: Trace,
        skill_spec: SkillSpec,
        expected_output: Any,
    ) -> MetricResult:
        try:
            from ..judges.llm_judge import LLMJudge

            judge = LLMJudge()
            prompt = self._build_judge_prompt(trajectory, skill_spec, expected_output)
            result = judge.evaluate(prompt)
            return MetricResult(
                metric_name=self.name,
                score=result.score,
                passed=result.score >= 0.5,
                reason=result.reason,
                details={"judge_model": result.model},
            )
        except ImportError:
            return self._score_heuristic(trajectory, skill_spec, expected_output)

    def _build_judge_prompt(
        self, trajectory: Trace, skill_spec: SkillSpec, expected_output: Any
    ) -> str:
        return (
            f"Evaluate whether this agent completed the task defined by the skill.\n\n"
            f"Skill: {skill_spec.name}\n"
            f"Description: {skill_spec.description}\n"
            f"Agent Input: {trajectory.input}\n"
            f"Agent Output: {trajectory.output}\n"
            f"Expected Output: {expected_output}\n"
            f"Errors: {[s.error for s in trajectory.errors]}\n\n"
            f"Score from 0.0 (complete failure) to 1.0 (perfect completion)."
        )

    @staticmethod
    def _outputs_match(actual: Any, expected: Any) -> bool:
        if isinstance(actual, str) and isinstance(expected, str):
            return actual.strip().lower() == expected.strip().lower()
        return actual == expected
