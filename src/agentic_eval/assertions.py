"""pytest integration -- assert_skill() and golden case loading."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import EvalResult, SkillSpec, Trace, Verdict
from .evaluators.skill_adherence import SkillAdherenceEvaluator
from .skill_parser import parse_skill
from .tracer import trace_context


class SkillAssertionError(AssertionError):
    """Raised when a skill evaluation fails assertion thresholds.

    Carries the full EvalResult so test frameworks can inspect
    exactly which metrics failed and why.
    """

    def __init__(self, eval_result: EvalResult, message: str) -> None:
        self.eval_result = eval_result
        super().__init__(message)


def assert_skill(
    actual: Any = None,
    expected: Any = None,
    skill: str | Path | SkillSpec | None = None,
    trace: Trace | None = None,
    thresholds: dict[str, float] | None = None,
    weights: dict[str, float] | None = None,
    use_llm_judge: bool = False,
) -> EvalResult:
    """Assert that a skill evaluation meets threshold requirements.

    For use in pytest tests:

        def test_my_skill():
            result = my_agent("do something")
            assert_skill(
                actual=result,
                skill="./SKILL.md",
                thresholds={"task_completion": 1.0, "instruction_fidelity": 0.8}
            )

    Args:
        actual: The agent's actual output.
        expected: Expected output for comparison.
        skill: SKILL.md path or SkillSpec.
        trace: Pre-captured trace (if using @trace_skill decorator).
        thresholds: Per-metric minimum scores {metric_name: float}.
        weights: Custom metric weights.
        use_llm_judge: Whether to use LLM-as-judge for evaluation.

    Returns:
        EvalResult on success.

    Raises:
        SkillAssertionError: If any metric falls below its threshold.
    """
    if trace is None:
        trace = Trace(input=actual, output=actual)

    skill_spec = None
    if skill is not None:
        if isinstance(skill, SkillSpec):
            skill_spec = skill
        else:
            skill_spec = parse_skill(skill)

    evaluator = SkillAdherenceEvaluator(
        skill=skill_spec,
        weights=weights,
        thresholds=thresholds,
        use_llm_judge=use_llm_judge,
    )

    result = evaluator.evaluate(trace, expected_output=expected)

    if thresholds:
        failures: list[str] = []
        for metric_name, threshold in thresholds.items():
            for mr in result.metric_results:
                if mr.metric_name == metric_name and mr.score < threshold:
                    failures.append(
                        f"{metric_name}: {mr.score:.3f} < {threshold:.3f} ({mr.reason})"
                    )

        if failures:
            msg = (
                f"Skill evaluation failed {len(failures)} threshold(s):\n"
                + "\n".join(f"  - {f}" for f in failures)
                + f"\n\nOverall score: {result.overall_score:.3f}"
                + f"\nVerdict: {result.verdict.value}"
            )
            raise SkillAssertionError(result, msg)

    elif result.verdict == Verdict.FAIL:
        failed_metrics = [mr for mr in result.metric_results if not mr.passed]
        msg = (
            f"Skill evaluation failed:\n"
            + "\n".join(
                f"  - {mr.metric_name}: {mr.score:.3f} ({mr.reason})"
                for mr in failed_metrics
            )
            + f"\n\nOverall score: {result.overall_score:.3f}"
        )
        raise SkillAssertionError(result, msg)

    return result


def load_golden_cases(path: str | Path) -> list[dict[str, Any]]:
    """Load golden test cases from a JSON file.

    Expected format:
        [
            {"input": "...", "expected": "...", "metadata": {}},
            ...
        ]

    Returns:
        List of test case dicts suitable for pytest.mark.parametrize.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Golden cases file not found: {path}")

    data = json.loads(p.read_text(encoding="utf-8"))

    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "cases" in data:
        return data["cases"]
    if isinstance(data, dict) and "test_cases" in data:
        return data["test_cases"]

    raise ValueError(f"Unexpected format in {path}: expected list or dict with 'cases' key")
