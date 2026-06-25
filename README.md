# agentic-eval

**Trajectory-based evaluation framework for AI agent skills.**

Evaluate, compare, and secure your AI agents with structured metrics — not vibes.

---

## Why agentic-eval?

Existing evaluation tools focus on LLM output quality. But agents are **multi-step systems** — they use tools, make decisions, recover from errors, and follow instructions. You need to evaluate the *journey*, not just the destination.

**agentic-eval** captures the full execution trajectory of your agent and scores it against your skill specifications using 11 structured metrics across 3 tiers — including trajectory-aware metrics that validate MCP/RAG tool responses, detect hallucinations, and verify output groundedness.

| Feature | agentic-eval | DeepEval | AgentOps | LangSmith |
|---|---|---|---|---|
| Trajectory-based scoring | Yes (11 metrics) | No | Partial | Partial |
| MCP/RAG response validation | Yes | No | No | No |
| Hallucination detection | Yes | Yes | No | No |
| Groundedness scoring | Yes | Yes | No | Partial |
| SKILL.md parsing | Yes | No | No | No |
| Decorator API (sync + async) | Yes | Yes | No | No |
| Security scanning | Yes | No | No | No |
| A/B skill comparison | Yes | No | No | No |
| Framework adapters | 6 built-in | N/A | N/A | LangChain only |
| Self-hosted, no vendor lock-in | Yes | Yes | No | No |

---

## Installation

```bash
pip install agentic-eval
pip install agentic-eval[all]  # LLM judge + dashboard
```

---

## Quick Start

```python
from agentic_eval import evaluate, record_tool_call

@evaluate(skill="./SKILL.md", auto_save=True)
def my_agent(query: str) -> str:
    record_tool_call("search", arguments={"q": query}, result="found it")
    return "Done!"

result = my_agent("find the bug")
my_agent.last_eval.print()
```

```python
from agentic_eval import run_evaluation, trace_context, record_tool_call

with trace_context(input="fix the CSS") as trace:
    record_tool_call("read_file", arguments={"path": "style.css"}, result="...")
    record_tool_call("write_file", arguments={"path": "style.css"}, result="ok")
    trace.output = "Fixed the CSS"

result = run_evaluation(trace, skill="./SKILL.md")
result.print()
```

---

## Metrics (11 total)

| Tier | Metric | What it measures |
|---|---|---|
| 1 | `task_completion` | Was the goal achieved? |
| 1 | `instruction_fidelity` | Did the agent follow the SKILL.md spec? |
| 1 | `output_correctness` | Is the result right, not just done? |
| 1 | `groundedness` | Is output grounded in tool/RAG/MCP evidence? |
| 1 | `hallucination` | Does output contain fabricated facts? |
| 2 | `step_deviation` | Diff between expected and actual steps |
| 2 | `tool_selection` | Were the right tools used? |
| 2 | `tool_response_alignment` | Are MCP/RAG calls relevant to the query? |
| 2 | `error_recovery` | Does the agent recover from failures? |
| 2 | `trajectory_optimality` | Is the trajectory coherent and non-redundant? |
| 3 | `action_economy` | Actual steps / optimal steps ratio |

---

## Documentation

| Guide | Description |
|---|---|
| [Getting Started](docs/getting-started.md) | Installation, quick start, async, pytest, batch, callbacks |
| [Metrics Reference](docs/metrics.md) | All 11 metrics with sub-scores, weights, and examples |
| [Framework Adapters](docs/adapters.md) | Gemini, LangChain, Langfuse, MLflow, OpenAI, OTel |
| [SKILL.md Format](docs/skill-format.md) | How to write and structure skill specifications |
| [Security Scanning](docs/security.md) | Vulnerability detection, grading, CI integration |
| [Skill Comparison](docs/comparison.md) | A/B testing between skill versions |
| [Custom Metrics](docs/custom-metrics.md) | Build and register your own metrics |
| [CLI Reference](docs/cli.md) | Command-line interface |
| [Dashboard](docs/dashboard.md) | Streamlit visualization dashboard |
| [Architecture](docs/architecture.md) | System design, package structure, design decisions |

---

## License

MIT
