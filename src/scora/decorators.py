"""Decorator-based API for evaluating agent skills.

Supports both sync and async agent functions, with optional auto-save
and callback hooks for CI/CD integration.
"""

from __future__ import annotations

import asyncio
import copy
import functools
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Sequence

from .models import EvalResult, SkillSpec, Trace, Verdict
from .skill_parser import parse_skill
from .tracer import get_current_trace, trace_context, async_trace_context

logger = logging.getLogger("scora")

_SKILL_CACHE_MAX = 128


@lru_cache(maxsize=_SKILL_CACHE_MAX)
def _cached_parse_skill(cache_key: str) -> SkillSpec:
    return parse_skill(cache_key)


def trace_skill(
    skill: str | Path | SkillSpec | None = None,
    metadata: dict[str, Any] | None = None,
) -> Callable:
    """Decorator that wraps a function with trajectory tracing.

    Captures the full execution as a Trace and attaches the parsed
    SkillSpec. Does NOT run evaluation metrics -- use @evaluate for that.

    Works with both sync and async functions.

    Args:
        skill: Path to SKILL.md, raw content, or pre-parsed SkillSpec.
        metadata: Extra metadata to attach to the trace.

    Usage:
        @trace_skill(skill="./SKILL.md")
        def my_agent(query: str) -> str:
            ...

        @trace_skill(skill="./SKILL.md")
        async def my_async_agent(query: str) -> str:
            ...
    """

    def decorator(fn: Callable) -> Callable:
        skill_spec = _resolve_skill(skill)

        if asyncio.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                trace_meta = _build_trace_meta(skill_spec, metadata)
                fn_input = _capture_input(args, kwargs)

                async with async_trace_context(input=fn_input, metadata=trace_meta) as trace:
                    result = await fn(*args, **kwargs)
                    trace.output = result

                async_wrapper._last_trace = trace
                async_wrapper._last_skill_spec = skill_spec
                return result

            async_wrapper._last_trace = None
            async_wrapper._last_skill_spec = None
            return async_wrapper
        else:
            @functools.wraps(fn)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                trace_meta = _build_trace_meta(skill_spec, metadata)
                fn_input = _capture_input(args, kwargs)

                with trace_context(input=fn_input, metadata=trace_meta) as trace:
                    result = fn(*args, **kwargs)
                    trace.output = result

                wrapper._last_trace = trace
                wrapper._last_skill_spec = skill_spec
                return result

            wrapper._last_trace = None
            wrapper._last_skill_spec = None
            return wrapper

    return decorator


def evaluate(
    skill: str | Path | SkillSpec | None = None,
    metrics: Sequence[str] | None = None,
    expected_tools: list[str] | None = None,
    expected_output: Any = None,
    thresholds: dict[str, float] | None = None,
    weights: dict[str, float] | None = None,
    metadata: dict[str, Any] | None = None,
    use_llm_judge: bool = False,
    auto_save: bool = False,
    db_path: str = "./scora_results.db",
    on_complete: Callable[[EvalResult], None] | None = None,
) -> Callable:
    """Decorator that traces execution AND runs evaluation metrics.

    Uses the same SkillAdherenceEvaluator engine as run_evaluation()
    and assert_skill(), ensuring consistent weighted scoring and verdicts
    regardless of which API entry point you use.

    Works with both sync and async functions.

    Args:
        skill: Path to SKILL.md, raw content, or pre-parsed SkillSpec.
        metrics: List of metric names to run. None = all registered.
        expected_tools: Tools the agent is expected to use.
        expected_output: Expected output for correctness checks.
        thresholds: Per-metric pass/fail thresholds {metric_name: float}.
        weights: Custom metric weights for overall scoring.
        metadata: Extra metadata.
        use_llm_judge: Use LLM-as-judge for qualitative metrics.
        auto_save: Persist results to the database automatically.
        db_path: Database path (used when auto_save=True).
        on_complete: Callback invoked with the EvalResult after evaluation.

    Usage:
        @evaluate(
            skill="./SKILL.md",
            metrics=["task_completion", "instruction_fidelity"],
            auto_save=True,
        )
        def my_agent(query: str) -> str:
            ...

        result = my_agent("do something")
        eval_result = my_agent.last_eval
    """

    def decorator(fn: Callable) -> Callable:
        skill_spec = _resolve_skill(skill)

        def _run_eval(trace: Trace, spec: SkillSpec | None) -> EvalResult:
            from .evaluators.skill_adherence import SkillAdherenceEvaluator

            eval_spec = spec
            if eval_spec and expected_tools:
                eval_spec = copy.deepcopy(eval_spec)
                eval_spec.expected_tools = list(
                    set(eval_spec.expected_tools) | set(expected_tools)
                )

            evaluator = SkillAdherenceEvaluator(
                skill=eval_spec,
                weights=weights,
                thresholds=thresholds,
                use_llm_judge=use_llm_judge,
            )

            if metrics is not None:
                _validate_metric_names(metrics)
                evaluator._metrics = [
                    m for m in evaluator._metrics if m.name in set(metrics)
                ]

            eval_result = evaluator.evaluate(trace, expected_output=expected_output)

            if auto_save:
                from .store import ResultStore
                with ResultStore(db_path) as store:
                    store.save(eval_result)

            if on_complete:
                on_complete(eval_result)

            return eval_result

        if asyncio.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                trace_meta = _build_trace_meta(skill_spec, metadata)
                fn_input = _capture_input(args, kwargs)

                async with async_trace_context(input=fn_input, metadata=trace_meta) as trace:
                    try:
                        result = await fn(*args, **kwargs)
                        trace.output = result
                    except Exception as exc:
                        trace.output = None
                        from .tracer import record_error
                        record_error(exc)
                        eval_result = _run_eval(trace, skill_spec)
                        async_wrapper.last_eval = eval_result
                        async_wrapper._last_trace = trace
                        async_wrapper._last_skill_spec = skill_spec
                        raise

                eval_result = _run_eval(trace, skill_spec)
                async_wrapper.last_eval = eval_result
                async_wrapper._last_trace = trace
                async_wrapper._last_skill_spec = skill_spec
                return result

            async_wrapper.last_eval = None
            async_wrapper._last_trace = None
            async_wrapper._last_skill_spec = None
            return async_wrapper
        else:
            @functools.wraps(fn)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                trace_meta = _build_trace_meta(skill_spec, metadata)
                fn_input = _capture_input(args, kwargs)

                with trace_context(input=fn_input, metadata=trace_meta) as trace:
                    try:
                        result = fn(*args, **kwargs)
                        trace.output = result
                    except Exception as exc:
                        trace.output = None
                        from .tracer import record_error
                        record_error(exc)
                        eval_result = _run_eval(trace, skill_spec)
                        wrapper.last_eval = eval_result
                        wrapper._last_trace = trace
                        wrapper._last_skill_spec = skill_spec
                        raise

                eval_result = _run_eval(trace, skill_spec)
                wrapper.last_eval = eval_result
                wrapper._last_trace = trace
                wrapper._last_skill_spec = skill_spec
                return result

            wrapper.last_eval = None
            wrapper._last_trace = None
            wrapper._last_skill_spec = None
            return wrapper

    return decorator


def _validate_metric_names(names: Sequence[str]) -> None:
    """Warn if any requested metric names don't exist in the registry."""
    from .metrics import get_registry

    registry = get_registry()
    known = set(registry.names())
    for name in names:
        if name not in known:
            logger.warning(
                "Unknown metric '%s' requested. Available: %s",
                name,
                ", ".join(sorted(known)),
            )


def _resolve_skill(skill: str | Path | SkillSpec | None) -> SkillSpec | None:
    """Resolve a skill argument into a SkillSpec, with LRU caching for paths/strings."""
    if skill is None:
        return None
    if isinstance(skill, SkillSpec):
        return skill

    cache_key = str(skill)
    return _cached_parse_skill(cache_key)


def _build_trace_meta(
    skill_spec: SkillSpec | None, extra: dict[str, Any] | None
) -> dict[str, Any]:
    return {
        "skill_name": skill_spec.name if skill_spec else "",
        "skill_hash": skill_spec.version_hash if skill_spec else "",
        **(extra or {}),
    }


def _capture_input(args: tuple, kwargs: dict) -> Any:
    """Capture function input for the trace."""
    if args and not kwargs:
        return args[0] if len(args) == 1 else list(args)
    if kwargs and not args:
        return kwargs
    return {"args": list(args), "kwargs": kwargs}
