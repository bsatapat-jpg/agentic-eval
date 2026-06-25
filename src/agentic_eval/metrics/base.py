"""Base metric class and registry."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Sequence

from ..models import EvalResult, MetricResult, SkillSpec, Trace


class BaseMetric(ABC):
    """Abstract base class for all evaluation metrics.

    Subclass this to create custom metrics:

        class MyMetric(BaseMetric):
            name = "my_metric"
            description = "Checks something custom"

            def score(self, trajectory, skill_spec, expected_output=None):
                return MetricResult(metric_name=self.name, score=0.9, reason="...")
    """

    name: str = "base_metric"
    description: str = ""
    tier: int = 1  # 1=non-negotiable, 2=diagnostic, 3=efficiency

    @abstractmethod
    def score(
        self,
        trajectory: Trace,
        skill_spec: SkillSpec | None = None,
        expected_output: Any = None,
    ) -> MetricResult:
        """Evaluate the trajectory and return a MetricResult.

        Args:
            trajectory: The captured execution trace.
            skill_spec: Parsed SKILL.md specification (may be None).
            expected_output: Expected output for correctness checks.

        Returns:
            MetricResult with score in [0.0, 1.0].
        """
        ...


class MetricRegistry:
    """Registry for metric instances, supporting lookup by name."""

    def __init__(self) -> None:
        self._metrics: dict[str, BaseMetric] = {}

    def register(self, metric: BaseMetric) -> None:
        self._metrics[metric.name] = metric

    def get(self, name: str) -> BaseMetric | None:
        return self._metrics.get(name)

    def all(self) -> list[BaseMetric]:
        return list(self._metrics.values())

    def names(self) -> list[str]:
        return list(self._metrics.keys())

    def resolve(self, names: Sequence[str] | None = None) -> list[BaseMetric]:
        """Resolve a list of metric names to instances. None = all.

        Warns if any requested name is not found in the registry.
        """
        if names is None:
            return self.all()
        result = []
        for n in names:
            m = self._metrics.get(n)
            if m is not None:
                result.append(m)
            else:
                import logging
                logging.getLogger("agentic_eval").warning(
                    "Unknown metric '%s'. Available: %s",
                    n,
                    ", ".join(sorted(self._metrics.keys())),
                )
        return result
