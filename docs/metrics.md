# Metrics Reference

> 11 metrics across 3 tiers — from non-negotiable pass/fail to efficiency diagnostics.

Each metric scores from **0.0 to 1.0** and supports both heuristic scoring (fast, offline) and LLM-as-judge mode for deeper semantic evaluation.

<br>

## At a Glance

```
  TIER 1 — Non-Negotiable              TIER 2 — Diagnostic              TIER 3 — Efficiency
  ─────────────────────────             ──────────────────               ─────────────────────
  task_completion     15%               step_deviation       8%          action_economy    4%
  instruction_fidelity 15%              tool_selection       8%
  output_correctness  10%               tool_response_align  8%
  groundedness        10%               error_recovery       5%
  hallucination       10%               trajectory_optimal   7%
```

| Tier | Metric | Description | Weight |
|:---:|:---|:---|:---:|
| **1** | `task_completion` | Was the goal achieved? | 15% |
| **1** | `instruction_fidelity` | Did the agent follow the SKILL.md spec? | 15% |
| **1** | `output_correctness` | Is the result right, not just done? | 10% |
| **1** | `groundedness` | Is output grounded in tool/RAG/MCP evidence? | 10% |
| **1** | `hallucination` | Does output contain fabricated facts? | 10% |
| **2** | `step_deviation` | Diff between expected and actual action sequence | 8% |
| **2** | `tool_selection` | Percentage of tool calls matching prescribed tools | 8% |
| **2** | `tool_response_alignment` | Are MCP/RAG calls and responses relevant? | 8% |
| **2** | `error_recovery` | When a step fails, does the agent recover? | 5% |
| **2** | `trajectory_optimality` | Is the trajectory coherent and non-redundant? | 7% |
| **3** | `action_economy` | Actual steps / optimal steps ratio | 4% |

<br>

---

## Tier 1 — Non-Negotiable

> A failure in **any** Tier 1 metric results in a **FAIL** verdict, regardless of other scores.

<br>

### `task_completion`

Measures whether the agent completed its task successfully.

| Score | Meaning |
|:---:|:---|
| **1.0** | Output produced, no errors |
| **0.5** | Output produced but errors encountered |
| **0.3** | Output produced but doesn't match expected output |
| **0.0** | No output or only errors |

<br>

### `instruction_fidelity`

Measures how faithfully the agent follows the SKILL.md specification. Combines three sub-scores:

| Sub-score | What it checks |
|:---|:---|
| Step coverage | Were all required steps addressed? |
| Tool compliance | Did it use the prescribed tools? |
| Constraint adherence | Did it respect the constraints? *(requires LLM judge)* |

<br>

### `output_correctness`

Validates the agent's output against expected content, schema, or custom assertions. Supports exact match, substring match, word overlap, dict comparison, and JSON schema validation.

<br>

### `groundedness`

Measures whether the final output is faithful to evidence gathered from tool/RAG/MCP responses. This is the **core anti-hallucination metric** for tool-augmented agents.

| Sub-score | Weight | What it checks |
|:---|:---:|:---|
| Claim Coverage | 40% | Fraction of output claims traceable to tool responses |
| Entity Grounding | 40% | Named entities in output found in evidence |
| Evidence Utilization | 20% | How much gathered evidence was used |

```python
result = run_evaluation(trace, metrics=["groundedness"])
print(result.metric_results[0].details)
# {'evidence_sources': 3, 'claim_coverage': 0.85, 'entity_grounding': 0.92, ...}
```

<br>

### `hallucination`

Detects fabricated factual claims by extracting **verifiable facts** from the output and checking them against all evidence sources.

<details>
<summary><strong>Fact types extracted</strong></summary>

| Fact type | Examples | Severity |
|:---|:---|:---:|
| Currency amounts | $5M, $2.50 | Highest |
| Percentages | 99.9%, 50% | Highest |
| URLs | https://example.com | High |
| Dates | 2024-01-15, January 15 | Medium |
| Version strings | v2.1.0, 3.11.4 | Medium |
| File paths | /etc/config.yaml | Lower |

</details>

<br>

---

## Tier 2 — Diagnostic

> These metrics provide diagnostic insights but don't individually fail the evaluation.

<br>

### `step_deviation`

Computes the diff between the SKILL.md's defined steps and the actual execution path using **fuzzy-matched Longest Common Subsequence** (LCS).

<br>

### `tool_selection`

Evaluates tool selection using precision, recall, and F1:

| Sub-score | What it measures |
|:---|:---|
| **Precision** | What fraction of tools used were expected? |
| **Recall** | What fraction of expected tools were used? |
| **F1** | Harmonic mean of precision and recall |

<br>

### `tool_response_alignment`

Validates that tool calls and their responses are **aligned with the user's query**. Critical for MCP and RAG pipelines.

| Sub-score | Weight | What it checks |
|:---|:---:|:---|
| Argument Relevance | 35% | Do tool arguments relate to the user query? |
| Response Relevance | 40% | Does the tool response contain useful information? |
| Response Utilization | 25% | Was the response used in the final output? |

```python
result = run_evaluation(trace, metrics=["tool_response_alignment"])
for tool in result.metric_results[0].details["per_tool"]:
    print(f"{tool['tool']}: arg={tool['argument_relevance']:.0%} "
          f"resp={tool['response_relevance']:.0%} "
          f"used={tool['response_utilization']:.0%}")
```

<br>

### `error_recovery`

Measures the agent's ability to recover from errors:

| Signal | What it detects |
|:---|:---|
| Recovery rate | Errors followed by successful spans |
| Resilience | Final output produced despite errors |
| Spiral detection | Same error repeated 3+ times |
| Retry counting | Number of retry attempts |

<br>

### `trajectory_optimality`

Evaluates the quality of the execution trajectory as a plan:

| Sub-score | Weight | What it checks |
|:---|:---:|:---|
| Redundancy | 30% | Repeated identical tool calls |
| Result Utilization | 30% | Were tool results used downstream? |
| Logical Ordering | 20% | Read-before-write, validate-before-submit |
| Backtracking | 20% | Create-then-delete undo/redo patterns |

<br>

---

## Tier 3 — Efficiency

### `action_economy`

Measures efficiency as the ratio of optimal steps (from SKILL.md) to actual steps taken. Only counts tool calls and agent steps, not LLM calls.

<br>

---

## Advanced Usage

<details>
<summary><strong>Select specific metrics</strong></summary>

```python
result = run_evaluation(
    trace,
    metrics=["task_completion", "groundedness", "hallucination"],
)
```

</details>

<details>
<summary><strong>LLM-as-Judge mode</strong></summary>

Enable deeper semantic evaluation for any metric that supports it:

```python
result = run_evaluation(trace, skill="./SKILL.md", use_llm_judge=True)
```

Supported by: `task_completion`, `instruction_fidelity`, `groundedness`, `hallucination`, `tool_response_alignment`.

</details>

<details>
<summary><strong>Metric discovery</strong></summary>

```python
from agentic_eval import list_metrics

for m in list_metrics():
    print(f"[Tier {m['tier']}] {m['name']}: {m['description']}")
```

</details>

<br>

---

<p align="center">
  <a href="getting-started.md">Getting Started</a> · <a href="adapters.md">Adapters</a> · <a href="custom-metrics.md">Custom Metrics</a> · <a href="integration-guide.md">Integration Guide</a>
</p>
