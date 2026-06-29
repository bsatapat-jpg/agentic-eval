"""Instruction Fidelity metric -- does the agent follow the SKILL.md spec?"""

from __future__ import annotations

from typing import Any

from ..models import MetricResult, SkillSpec, Trace
from .base import BaseMetric


class InstructionFidelityMetric(BaseMetric):
    """Measures how faithfully the agent follows the SKILL.md specification.

    Compares the agent's actual actions against the skill's defined workflow steps.
    Uses a combination of:
    - Step coverage: were all required steps addressed?
    - Tool compliance: did it use the prescribed tools?
    - Constraint adherence: did it respect the constraints?
    """

    name = "instruction_fidelity"
    description = "Does the agent follow the SKILL.md spec?"
    tier = 1

    def __init__(self, use_llm_judge: bool = False) -> None:
        self.use_llm_judge = use_llm_judge

    def score(
        self,
        trajectory: Trace,
        skill_spec: SkillSpec | None = None,
        expected_output: Any = None,
    ) -> MetricResult:
        if skill_spec is None:
            return MetricResult(
                metric_name=self.name,
                score=0.0,
                passed=False,
                reason="No skill spec provided -- cannot evaluate instruction fidelity",
            )

        if self.use_llm_judge:
            return self._score_with_llm(trajectory, skill_spec)

        return self._score_heuristic(trajectory, skill_spec)

    def _score_heuristic(
        self,
        trajectory: Trace,
        skill_spec: SkillSpec,
    ) -> MetricResult:
        scores: list[float] = []
        details: dict[str, Any] = {}

        step_score, step_details = self._evaluate_step_coverage(trajectory, skill_spec)
        scores.append(step_score)
        details["step_coverage"] = step_details

        tool_score, tool_details = self._evaluate_tool_compliance(trajectory, skill_spec)
        scores.append(tool_score)
        details["tool_compliance"] = tool_details

        if skill_spec.constraints:
            constraint_score, constraint_details = self._evaluate_constraints(
                trajectory, skill_spec
            )
            scores.append(constraint_score)
            details["constraint_adherence"] = constraint_details

        overall = sum(scores) / len(scores) if scores else 0.0

        return MetricResult(
            metric_name=self.name,
            score=overall,
            passed=overall >= 0.5,
            reason=self._generate_reason(overall, details),
            details=details,
        )

    def _evaluate_step_coverage(
        self, trajectory: Trace, skill_spec: SkillSpec
    ) -> tuple[float, dict]:
        if not skill_spec.steps:
            return 1.0, {"message": "No steps defined in skill spec"}

        tool_names_used = {tc.name for tc in trajectory.tool_calls}
        span_names = {s.name for s in self._flat_spans(trajectory)}
        all_actions = tool_names_used | span_names

        required_steps = [s for s in skill_spec.steps if s.required]
        if not required_steps:
            return 1.0, {"message": "No required steps defined"}

        covered = 0
        step_results: list[dict] = []
        for step in required_steps:
            step_covered = self._is_step_covered(step, all_actions, trajectory)
            if step_covered:
                covered += 1
            step_results.append({
                "step": step.description,
                "covered": step_covered,
                "order": step.order,
            })

        coverage = covered / len(required_steps)
        return coverage, {
            "total_required": len(required_steps),
            "covered": covered,
            "steps": step_results,
        }

    def _is_step_covered(self, step, all_actions: set[str], trajectory: Trace) -> bool:
        if step.expected_tools:
            return any(tool in all_actions for tool in step.expected_tools)

        keywords = set(step.description.lower().split())
        stop_words = {"the", "a", "an", "is", "to", "and", "or", "of", "in", "for", "with"}
        keywords -= stop_words

        for action in all_actions:
            action_lower = action.lower().replace("_", " ").replace("-", " ")
            if any(kw in action_lower for kw in keywords if len(kw) > 3):
                return True

        if trajectory.output:
            output_str = str(trajectory.output).lower()
            matches = sum(1 for kw in keywords if kw in output_str and len(kw) > 3)
            if matches >= min(2, len(keywords)):
                return True

        return False

    def _evaluate_tool_compliance(
        self, trajectory: Trace, skill_spec: SkillSpec
    ) -> tuple[float, dict]:
        if not skill_spec.expected_tools:
            return 1.0, {"message": "No expected tools defined in skill spec"}

        tools_used = {tc.name for tc in trajectory.tool_calls}
        expected = set(skill_spec.expected_tools)

        if not tools_used:
            return 0.0, {
                "expected": list(expected),
                "used": [],
                "message": "No tools were used",
            }

        used_expected = tools_used & expected
        unexpected = tools_used - expected

        coverage = len(used_expected) / len(expected) if expected else 1.0
        penalty = min(len(unexpected) * 0.1, 0.3)
        score = max(0.0, coverage - penalty)

        return score, {
            "expected": list(expected),
            "used": list(tools_used),
            "matched": list(used_expected),
            "unexpected": list(unexpected),
            "coverage": coverage,
        }

    def _evaluate_constraints(
        self, trajectory: Trace, skill_spec: SkillSpec
    ) -> tuple[float, dict]:
        return 1.0, {
            "message": "Constraint checking requires LLM judge for semantic analysis",
            "constraints": skill_spec.constraints,
        }

    def _flat_spans(self, trajectory: Trace) -> list:
        result = []
        for span in trajectory.spans:
            result.append(span)
            self._collect_children(span, result)
        return result

    def _collect_children(self, span, result: list) -> None:
        for child in span.children:
            result.append(child)
            self._collect_children(child, result)

    def _generate_reason(self, overall: float, details: dict) -> str:
        parts: list[str] = []
        if "step_coverage" in details:
            sc = details["step_coverage"]
            if "covered" in sc:
                parts.append(
                    f"Step coverage: {sc['covered']}/{sc['total_required']}"
                )
        if "tool_compliance" in details:
            tc = details["tool_compliance"]
            if "matched" in tc:
                parts.append(
                    f"Tool compliance: {len(tc['matched'])}/{len(tc['expected'])} expected tools used"
                )
        if overall >= 0.8:
            verdict = "High fidelity to skill spec"
        elif overall >= 0.5:
            verdict = "Moderate fidelity to skill spec"
        else:
            verdict = "Low fidelity to skill spec"

        return f"{verdict}. {'; '.join(parts)}" if parts else verdict

    def _score_with_llm(self, trajectory: Trace, skill_spec: SkillSpec) -> MetricResult:
        try:
            from ..judges.llm_judge import LLMJudge

            judge = LLMJudge()
            prompt = (
                f"Evaluate how faithfully this agent followed the skill specification.\n\n"
                f"SKILL SPECIFICATION:\n{skill_spec.raw_content[:3000]}\n\n"
                f"AGENT TRAJECTORY:\n"
                f"Input: {trajectory.input}\n"
                f"Tool calls: {[tc.name for tc in trajectory.tool_calls]}\n"
                f"Output: {trajectory.output}\n\n"
                f"Score from 0.0 (completely ignored spec) to 1.0 (perfect adherence)."
            )
            result = judge.evaluate(prompt)
            return MetricResult(
                metric_name=self.name,
                score=result.score,
                passed=result.score >= 0.5,
                reason=result.reason,
                details={"judge_model": result.model},
            )
        except ImportError:
            return self._score_heuristic(trajectory, skill_spec)
