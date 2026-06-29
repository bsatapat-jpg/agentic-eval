# Skill Comparison (A/B Testing)

> Ship skill updates with confidence — know exactly which version performs better and by how much.

Compare two versions of a skill across all 11 evaluation metrics with statistical lift analysis.

<br>

---

## With Pre-Recorded Traces

```python
from skora import compare_skills

result = compare_skills(
    skill_a="./skills/v1/SKILL.md",
    skill_b="./skills/v2/SKILL.md",
    traces_a=v1_traces,
    traces_b=v2_traces,
)

print(result.verdict)   # a_better / b_better / no_difference
print(f"Lift: {result.lift:+.2%}")

for m in result.per_metric:
    print(f"  {m.metric_name}: {m.score_a:.2f} → {m.score_b:.2f} ({m.delta:+.2f})")
```

<br>

## With Live Agent Execution

```python
result = compare_skills(
    skill_a="./skills/v1/SKILL.md",
    skill_b="./skills/v2/SKILL.md",
    agent_fn=my_agent,
    test_inputs=["query1", "query2", "query3"],
    expected_outputs=["expected1", "expected2", "expected3"],
    trials=5,   # Repeat each input 5 times for variance reduction
)
```

<br>

## From the CLI

```bash
skora compare ./v1/SKILL.md ./v2/SKILL.md
skora compare ./v1/SKILL.md ./v2/SKILL.md --format json
```

<br>

---

## How Comparison Works

```
  Skill A (v1)                    Skill B (v2)
  ────────────                    ────────────
  Evaluate against                Evaluate against
  same traces/inputs              same traces/inputs
       │                               │
       ▼                               ▼
  Per-metric averages             Per-metric averages
       │                               │
       └───────────┬───────────────────┘
                   │
              Lift = B - A
                   │
        ┌──────────┼──────────┐
        │          │          │
    lift ≤ -5%  -5% < lift  lift ≥ +5%
        │        < +5%        │
    a_better  no_difference  b_better
```

<br>

---

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

<br>

---

<p align="center">
  <a href="getting-started.md">Getting Started</a> · <a href="metrics.md">Metrics</a> · <a href="security.md">Security</a> · <a href="cli.md">CLI</a>
</p>
