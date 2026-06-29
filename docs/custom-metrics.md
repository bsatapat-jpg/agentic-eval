# Custom Metrics

> Extend scora with metrics that matter to **your** use case.

<br>

---

## Creating a Custom Metric

Subclass `BaseMetric`, implement `score()`, and register it:

```python
from scora import BaseMetric, MetricResult, register_metric

class LatencyMetric(BaseMetric):
    name = "latency"
    description = "Evaluates agent response time"
    tier = 3

    def score(self, trajectory, skill_spec=None, expected_output=None):
        duration = trajectory.duration_ms or 0
        score = max(0, 1.0 - (duration / 30000))
        return MetricResult(
            metric_name=self.name,
            score=score,
            passed=score >= 0.5,
            reason=f"Completed in {duration:.0f}ms",
            details={"duration_ms": duration},
        )

register_metric(LatencyMetric())
```

> Once registered, your metric is available everywhere — `run_evaluation()`, `@evaluate`, `assert_skill`, and the dashboard.

<br>

---

## The BaseMetric Interface

```python
class BaseMetric(ABC):
    name: str = "base_metric"       # Unique identifier
    description: str = ""           # Human-readable description
    tier: int = 1                   # 1 = non-negotiable, 2 = diagnostic, 3 = efficiency

    @abstractmethod
    def score(
        self,
        trajectory: Trace,
        skill_spec: SkillSpec | None = None,
        expected_output: Any = None,
    ) -> MetricResult:
        ...
```

<br>

## MetricResult Fields

| Field | Type | Description |
|:---|:---|:---|
| `metric_name` | `str` | Must match the metric's `name` |
| `score` | `float` | Score between 0.0 and 1.0 |
| `passed` | `bool` | Whether the metric passed its threshold |
| `reason` | `str` | Human-readable explanation |
| `details` | `dict` | Arbitrary structured data for debugging |
| `threshold` | `float \| None` | Pass/fail threshold (set by evaluator) |

<br>

---

## Using Custom Metrics

Once registered, custom metrics work everywhere:

```python
# In run_evaluation
result = run_evaluation(trace, metrics=["latency", "task_completion"])

# In @evaluate decorator
@evaluate(skill="./SKILL.md", metrics=["latency", "groundedness"])
def my_agent(query):
    ...

# In assert_skill
assert_skill(actual=result, thresholds={"latency": 0.8})
```

<br>

---

## Example: Token Cost Metric

```python
class TokenCostMetric(BaseMetric):
    name = "token_cost"
    description = "Evaluates token usage efficiency"
    tier = 3

    def __init__(self, max_tokens: int = 10000):
        self.max_tokens = max_tokens

    def score(self, trajectory, skill_spec=None, expected_output=None):
        total_tokens = 0
        for span in self._walk(trajectory.spans):
            usage = span.metadata.get("token_usage", {})
            total_tokens += usage.get("total_tokens", 0)

        score = max(0.0, 1.0 - total_tokens / self.max_tokens)
        return MetricResult(
            metric_name=self.name,
            score=score,
            passed=score >= 0.3,
            reason=f"Used {total_tokens} tokens (max: {self.max_tokens})",
            details={"total_tokens": total_tokens},
        )

    def _walk(self, spans):
        result = []
        for s in spans:
            result.append(s)
            result.extend(self._walk(s.children))
        return result

register_metric(TokenCostMetric())
```

<br>

---

## Custom Weights

Override default metric weights when evaluating:

```python
result = run_evaluation(
    trace,
    weights={
        "task_completion": 0.3,
        "latency": 0.2,
        "token_cost": 0.1,
        "groundedness": 0.2,
        "hallucination": 0.2,
    },
)
```

<br>

---

<p align="center">
  <a href="getting-started.md">Getting Started</a> · <a href="metrics.md">Metrics</a> · <a href="adapters.md">Adapters</a> · <a href="architecture.md">Architecture</a>
</p>
