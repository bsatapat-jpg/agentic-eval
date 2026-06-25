"""High-level convenience API for agentic-eval.

These functions provide the simplest possible interface for common
evaluation tasks. Import them directly:

    from agentic_eval import run_evaluation, compare_skills, list_metrics, batch_evaluate
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Sequence

from .models import (
    ComparisonResult,
    EvalResult,
    MetricResult,
    SkillSpec,
    Trace,
    Verdict,
)
from .skill_parser import parse_skill


def run_evaluation(
    trace: Trace,
    skill: str | Path | SkillSpec | None = None,
    metrics: Sequence[str] | None = None,
    expected_output: Any = None,
    thresholds: dict[str, float] | None = None,
    weights: dict[str, float] | None = None,
    use_llm_judge: bool = False,
    save: bool = False,
    db_path: str = "./agentic_eval_results.db",
) -> EvalResult:
    """Evaluate a single trace against a skill specification.

    This is the simplest way to evaluate an agent trace:

        from agentic_eval import run_evaluation, Trace

        trace = Trace(input="query", output="response")
        result = run_evaluation(trace, skill="./SKILL.md")
        result.print()

    Args:
        trace: The agent execution trace to evaluate.
        skill: Path to SKILL.md, raw content string, or pre-parsed SkillSpec.
        metrics: Metric names to run. None runs all registered metrics.
        expected_output: Expected output for correctness comparison.
        thresholds: Per-metric pass/fail thresholds.
        weights: Custom metric weights for overall scoring.
        use_llm_judge: Use LLM-as-judge for qualitative metrics.
        save: Persist the result to the database.
        db_path: Database path (used when save=True).

    Returns:
        EvalResult with scores, verdict, and per-metric breakdown.
    """
    from .evaluators.skill_adherence import SkillAdherenceEvaluator

    skill_spec = _resolve_skill(skill)

    evaluator = SkillAdherenceEvaluator(
        skill=skill_spec,
        weights=weights,
        thresholds=thresholds,
        use_llm_judge=use_llm_judge,
    )

    if metrics is not None:
        metric_set = set(metrics)
        evaluator._metrics = [m for m in evaluator._metrics if m.name in metric_set]

    result = evaluator.evaluate(trace, expected_output=expected_output)

    if save:
        from .store import ResultStore
        with ResultStore(db_path) as store:
            store.save(result)

    return result


def compare_skills(
    skill_a: str | Path | SkillSpec,
    skill_b: str | Path | SkillSpec,
    agent_fn: Callable | None = None,
    test_inputs: list[Any] | None = None,
    expected_outputs: list[Any] | None = None,
    traces_a: list[Trace] | None = None,
    traces_b: list[Trace] | None = None,
    trials: int = 1,
    weights: dict[str, float] | None = None,
    save: bool = False,
    db_path: str = "./agentic_eval_results.db",
) -> ComparisonResult:
    """Compare two skill versions side-by-side.

    Provide either pre-recorded traces or an agent function + test inputs:

        # With pre-recorded traces
        result = compare_skills(
            "./skills/v1/SKILL.md",
            "./skills/v2/SKILL.md",
            traces_a=v1_traces,
            traces_b=v2_traces,
        )

        # With live agent execution
        result = compare_skills(
            "./skills/v1/SKILL.md",
            "./skills/v2/SKILL.md",
            agent_fn=my_agent,
            test_inputs=["query1", "query2"],
            trials=5,
        )
        print(result.verdict)  # a_better / b_better / no_difference

    Args:
        skill_a: Baseline skill version.
        skill_b: Candidate skill version.
        agent_fn: Agent function (decorated with @trace_skill).
        test_inputs: Inputs to test with.
        expected_outputs: Expected outputs per test input.
        traces_a: Pre-recorded traces for skill A.
        traces_b: Pre-recorded traces for skill B.
        trials: Repetitions per test input (for variance reduction).
        weights: Metric weights for scoring.
        save: Persist results to the database.
        db_path: Database path.

    Returns:
        ComparisonResult with verdict, lift, and per-metric breakdown.
    """
    from .evaluators.comparator import SkillComparator

    comparator = SkillComparator()
    result = comparator.compare(
        skill_a=skill_a,
        skill_b=skill_b,
        agent_fn=agent_fn,
        test_inputs=test_inputs,
        expected_outputs=expected_outputs,
        traces_a=traces_a,
        traces_b=traces_b,
        trials=trials,
        weights=weights,
    )

    if save:
        from .store import ResultStore
        with ResultStore(db_path) as store:
            store.save_comparison(result)

    return result


def batch_evaluate(
    traces: list[Trace],
    skill: str | Path | SkillSpec | None = None,
    expected_outputs: list[Any] | None = None,
    metrics: Sequence[str] | None = None,
    thresholds: dict[str, float] | None = None,
    weights: dict[str, float] | None = None,
    use_llm_judge: bool = False,
    save: bool = False,
    db_path: str = "./agentic_eval_results.db",
) -> list[EvalResult]:
    """Evaluate multiple traces in batch. Ideal for regression testing.

        results = batch_evaluate(
            traces=recorded_traces,
            skill="./SKILL.md",
            thresholds={"task_completion": 0.9},
            save=True,
        )
        pass_rate = sum(1 for r in results if r.verdict == Verdict.PASS) / len(results)

    Args:
        traces: List of agent execution traces.
        skill: Skill specification to evaluate against.
        expected_outputs: Expected outputs aligned with traces list.
        metrics: Metric names to run.
        thresholds: Per-metric pass/fail thresholds.
        weights: Custom metric weights.
        use_llm_judge: Use LLM-as-judge.
        save: Persist results.
        db_path: Database path.

    Returns:
        List of EvalResult, one per trace.
    """
    results: list[EvalResult] = []
    for i, trace in enumerate(traces):
        expected = expected_outputs[i] if expected_outputs and i < len(expected_outputs) else None
        result = run_evaluation(
            trace=trace,
            skill=skill,
            metrics=metrics,
            expected_output=expected,
            thresholds=thresholds,
            weights=weights,
            use_llm_judge=use_llm_judge,
            save=save,
            db_path=db_path,
        )
        results.append(result)
    return results


def list_metrics() -> list[dict[str, Any]]:
    """Discover all registered metrics and their descriptions.

        for m in list_metrics():
            print(f"{m['name']} (Tier {m['tier']}): {m['description']}")

    Returns:
        List of dicts with name, description, tier for each metric.
    """
    from .metrics import get_registry

    registry = get_registry()
    return [
        {
            "name": m.name,
            "description": m.description,
            "tier": m.tier,
        }
        for m in registry.all()
    ]


def scan_security(
    skill: str | Path,
    save: bool = False,
    db_path: str = "./agentic_eval_results.db",
):
    """Scan a SKILL.md file for security vulnerabilities.

        report = scan_security("./SKILL.md")
        print(f"Grade: {report.grade}, Critical: {report.critical_count}")

    Args:
        skill: Path to SKILL.md file.
        save: Persist the report to the database.
        db_path: Database path.

    Returns:
        SecurityReport with findings, grade, and score.
    """
    from .evaluators.security import SecurityEvaluator

    evaluator = SecurityEvaluator()
    report = evaluator.scan_skill(str(skill))

    if save:
        from .store import ResultStore
        with ResultStore(db_path) as store:
            store.save_security_report(report)

    return report


def _resolve_skill(skill: str | Path | SkillSpec | None) -> SkillSpec | None:
    if skill is None:
        return None
    if isinstance(skill, SkillSpec):
        return skill
    return parse_skill(skill)
