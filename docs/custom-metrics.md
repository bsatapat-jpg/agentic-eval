# Custom Metrics

Extend agentic-eval with your own evaluation metrics.

## Creating a Custom Metric

Subclass `BaseMetric` and implement the `score` method:

```python
from agentic_eval import BaseMetric, MetricResult, register_metric

class LatencyMetric(BaseMetric):
    name = "latency"
    description = "Evaluates agent response time"
    tier = 3

    def score(self, trajectory, skill_spec=None, expected_output=None):
        duration = trajectory.duration_ms or 0
        score = max(0, 1.0 - (duration / 30000))  # Penalize > 30s
        return MetricResult(
            metric_name=self.name,
            score=score,
            passed=score >= 0.5,
            reason=f"Completed in {duration:.0f}ms",
            details={"duration_ms": duration},
        )

register_metric(LatencyMetric())
```

## BaseMetric Interface

```python
class BaseMetric(ABC):
    name: str = "base_metric"       # Unique metric identifier
    description: str = ""           # Human-readable description
    tier: int = 1                   # 1=non-negotiable, 2=diagnostic, 3=efficiency

    @abstractmethod
    def score(
        self,
        trajectory: Trace,
        skill_spec: SkillSpec | None = None,
        expected_output: Any = None,
    ) -> MetricResult:
        ...
```

## MetricResult Fields

| Field | Type | Description |
|---|---|---|
| `metric_name` | `str` | Must match the metric's `name` |
| `score` | `float` | Score between 0.0 and 1.0 |
| `passed` | `bool` | Whether the metric passed its threshold |
| `reason` | `str` | Human-readable explanation |
| `details` | `dict` | Arbitrary structured data for debugging |
| `threshold` | `float \| None` | Pass/fail threshold (set by evaluator) |

## Using Custom Metrics in Evaluation

Once registered, custom metrics are available everywhere:

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
