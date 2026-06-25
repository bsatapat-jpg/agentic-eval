# Skill Comparison (A/B Testing)

Compare two versions of a skill to determine which performs better across all evaluation metrics.

## With Pre-Recorded Traces

```python
from agentic_eval import compare_skills

result = compare_skills(
    skill_a="./skills/v1/SKILL.md",
    skill_b="./skills/v2/SKILL.md",
    traces_a=v1_traces,
    traces_b=v2_traces,
)

print(result.verdict)  # a_better / b_better / no_difference
print(f"Lift: {result.lift:+.2%}")

for m in result.per_metric:
    print(f"  {m.metric_name}: {m.score_a:.2f} -> {m.score_b:.2f} ({m.delta:+.2f})")
```

## With Live Agent Execution

```python
result = compare_skills(
    skill_a="./skills/v1/SKILL.md",
    skill_b="./skills/v2/SKILL.md",
    agent_fn=my_agent,
    test_inputs=["query1", "query2", "query3"],
    expected_outputs=["expected1", "expected2", "expected3"],
    trials=5,  # Repeat each input 5 times for variance reduction
)
```

## From the CLI

```bash
agentic-eval compare ./v1/SKILL.md ./v2/SKILL.md
agentic-eval compare ./v1/SKILL.md ./v2/SKILL.md --format json
```

## How Comparison Works

1. Both skills are evaluated against the same traces/inputs
2. Per-metric averages are computed for each skill
3. Overall score lift is calculated: `lift = score_b - score_a`
4. Verdict is determined:
   - `b_better` — lift >= 5%
   - `a_better` — lift <= -5%
   - `no_difference` — lift between -5% and +5%

## Persisting Results

```python
result = compare_skills(
    skill_a="./v1/SKILL.md",
    skill_b="./v2/SKILL.md",
    traces_a=v1_traces,
    traces_b=v2_traces,
    save=True,
    db_path="./results.db",
)
```
