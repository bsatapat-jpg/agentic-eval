"""Metrics registry and built-in metrics for skora."""

from __future__ import annotations

from .base import BaseMetric, MetricRegistry

_registry = MetricRegistry()


def get_registry() -> MetricRegistry:
    return _registry


def register_metric(metric: BaseMetric) -> None:
    _registry.register(metric)


def _auto_register() -> None:
    """Register all built-in metrics."""
    from .task_completion import TaskCompletionMetric
    from .instruction_fidelity import InstructionFidelityMetric
    from .output_correctness import OutputCorrectnessMetric
    from .step_deviation import StepDeviationMetric
    from .tool_selection import ToolSelectionMetric
    from .error_recovery import ErrorRecoveryMetric
    from .action_economy import ActionEconomyMetric
    from .tool_response_alignment import ToolResponseAlignmentMetric
    from .grounding import GroundednessMetric
    from .trajectory_optimality import TrajectoryOptimalityMetric
    from .hallucination import HallucinationMetric

    for cls in [
        TaskCompletionMetric,
        InstructionFidelityMetric,
        OutputCorrectnessMetric,
        StepDeviationMetric,
        ToolSelectionMetric,
        ErrorRecoveryMetric,
        ActionEconomyMetric,
        ToolResponseAlignmentMetric,
        GroundednessMetric,
        TrajectoryOptimalityMetric,
        HallucinationMetric,
    ]:
        _registry.register(cls())


_auto_register()
