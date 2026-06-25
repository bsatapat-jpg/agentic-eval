# Metrics Reference

agentic-eval ships with 11 metrics across 3 tiers. Each metric scores from 0.0 to 1.0 and supports both heuristic scoring (fast, offline) and LLM-as-judge mode for deeper semantic evaluation.

## Overview

| Tier | Metric | Description | Weight |
|---|---|---|---|
| 1 | `task_completion` | Was the goal achieved? | 15% |
| 1 | `instruction_fidelity` | Did the agent follow the SKILL.md spec? | 15% |
| 1 | `output_correctness` | Is the result right, not just done? | 10% |
| 1 | `groundedness` | Is output grounded in tool/RAG/MCP evidence? | 10% |
| 1 | `hallucination` | Does output contain fabricated facts? | 10% |
| 2 | `step_deviation` | Diff between expected and actual action sequence | 8% |
| 2 | `tool_selection` | Percentage of tool calls matching prescribed tools | 8% |
| 2 | `tool_response_alignment` | Are MCP/RAG calls and responses relevant? | 8% |
| 2 | `error_recovery` | When a step fails, does the agent recover? | 5% |
| 2 | `trajectory_optimality` | Is the trajectory coherent and non-redundant? | 7% |
| 3 | `action_economy` | Actual steps / optimal steps ratio | 4% |

## Tier 1 — Non-Negotiable

These metrics must pass for an overall PASS verdict. A failure in any Tier 1 metric results in a FAIL verdict regardless of other scores.

### `task_completion`

Measures whether the agent completed its task successfully.

- **1.0** — Output produced, no errors
- **0.5** — Output produced but errors encountered
- **0.3** — Output produced but doesn't match expected output
- **0.0** — No output or only errors

### `instruction_fidelity`

Measures how faithfully the agent follows the SKILL.md specification. Combines:

- **Step coverage**: Were all required steps addressed?
- **Tool compliance**: Did it use the prescribed tools?
- **Constraint adherence**: Did it respect the constraints? (requires LLM judge)

### `output_correctness`

Validates the agent's output against expected content, schema, or custom assertions. Supports exact match, substring match, word overlap, dict comparison, and JSON schema validation.

### `groundedness`

Measures whether the final output is faithful to evidence gathered from tool/RAG/MCP responses. This is the core anti-hallucination metric for tool-augmented agents.

**Sub-scores:**

| Sub-score | What it checks |
|---|---|
| Claim Coverage (40%) | Fraction of output claims traceable to tool responses |
| Entity Grounding (40%) | Named entities in output found in evidence |
| Evidence Utilization (20%) | How much gathered evidence was used |

```python
# Evaluate just groundedness
result = run_evaluation(trace, metrics=["groundedness"])
print(result.metric_results[0].details)
# {'evidence_sources': 3, 'claim_coverage': 0.85, 'entity_grounding': 0.92, ...}
```

### `hallucination`

Detects fabricated factual claims by extracting verifiable facts from the output and checking them against all evidence sources.

**Fact types extracted:**
- Dates (2024-01-15, January 15, 2024)
- Numbers and percentages (50,000 users, 99.9%)
- Currency amounts ($5M, $2.50)
- URLs (https://...)
- File paths (/etc/config.yaml)
- Version strings (v2.1.0)

**Severity weighting:**
- Currency amounts and percentages: highest severity
- URLs: high severity
- Dates and version strings: medium severity
- File paths: lower severity

## Tier 2 — Diagnostic

These metrics provide diagnostic insights but don't individually fail the evaluation.

### `step_deviation`

Computes the diff between the SKILL.md's defined steps and the actual execution path using fuzzy-matched Longest Common Subsequence (LCS).

### `tool_selection`

Evaluates tool selection using precision, recall, and F1:

- **Precision**: What fraction of tools used were expected?
- **Recall**: What fraction of expected tools were used?
- **F1**: Harmonic mean of precision and recall

### `tool_response_alignment`

Validates that tool calls and their responses are aligned with the user's query. Critical for MCP and RAG pipelines.

**Sub-scores:**

| Sub-score | Weight | What it checks |
|---|---|---|
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

### `error_recovery`

Measures the agent's ability to recover from errors:

- Recovery rate (errors followed by successful spans)
- Final output despite errors
- Spiral detection (same error repeated 3+ times)
- Retry counting

### `trajectory_optimality`

Evaluates the quality of the execution trajectory as a plan:

| Sub-score | Weight | What it checks |
|---|---|---|
| Redundancy | 30% | Repeated identical tool calls |
| Result Utilization | 30% | Were tool results used downstream? |
| Logical Ordering | 20% | Read-before-write, validate-before-submit |
| Backtracking | 20% | Create-then-delete undo/redo patterns |

## Tier 3 — Efficiency

### `action_economy`

Measures efficiency as the ratio of optimal steps (from SKILL.md) to actual steps taken. Only counts tool calls and agent steps, not LLM calls.

## Selecting Specific Metrics

You can run a subset of metrics:

```python
result = run_evaluation(
    trace,
    metrics=["task_completion", "groundedness", "hallucination"],
)
```

## LLM-as-Judge Mode

Enable deeper semantic evaluation for any metric that supports it:

```python
result = run_evaluation(trace, skill="./SKILL.md", use_llm_judge=True)
```

LLM judge is supported by: `task_completion`, `instruction_fidelity`, `groundedness`, `hallucination`, `tool_response_alignment`.

## Metric Discovery

```python
from agentic_eval import list_metrics

for m in list_metrics():
    print(f"[Tier {m['tier']}] {m['name']}: {m['description']}")
```
