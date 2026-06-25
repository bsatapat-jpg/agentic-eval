# Getting Started

## Installation

```bash
pip install agentic-eval
```

With optional features:

```bash
pip install agentic-eval[llm]        # LLM-as-judge (OpenAI/Anthropic)
pip install agentic-eval[dashboard]  # Streamlit dashboard
pip install agentic-eval[all]        # Everything
```

## Quick Start

### Decorator API (simplest)

Wrap your agent function with `@evaluate` — it captures the full execution trace and runs all 11 metrics automatically.

```python
from agentic_eval import evaluate, record_tool_call

@evaluate(skill="./SKILL.md", auto_save=True)
def my_agent(query: str) -> str:
    record_tool_call("search", arguments={"q": query}, result="found it")
    return "Done!"

result = my_agent("find the bug")
my_agent.last_eval.print()  # Rich console output
```

### Functional API (most flexible)

Use `trace_context` to manually capture traces, then evaluate them separately.

```python
from agentic_eval import run_evaluation, Trace, record_tool_call, trace_context

with trace_context(input="fix the CSS") as trace:
    record_tool_call("read_file", arguments={"path": "style.css"}, result="...")
    record_tool_call("write_file", arguments={"path": "style.css"}, result="ok")
    trace.output = "Fixed the CSS"

result = run_evaluation(trace, skill="./SKILL.md")
result.print()
```

### Async Agent Support

Both decorators detect async functions automatically — no extra configuration needed.

```python
from agentic_eval import evaluate

@evaluate(skill="./SKILL.md", auto_save=True)
async def my_async_agent(query: str) -> str:
    result = await call_llm(query)
    return result
```

### pytest Integration

Use `assert_skill` for test assertions with per-metric thresholds.

```python
from agentic_eval import assert_skill

def test_code_review_skill():
    result = my_agent("review this PR")
    assert_skill(
        actual=result,
        skill="./SKILL.md",
        thresholds={
            "task_completion": 1.0,
            "instruction_fidelity": 0.8,
            "tool_selection": 0.7,
        },
    )
```

### Batch Evaluation

Evaluate multiple traces at once for regression testing.

```python
from agentic_eval import batch_evaluate

results = batch_evaluate(
    traces=recorded_traces,
    skill="./SKILL.md",
    thresholds={"task_completion": 0.9},
    save=True,
)

pass_rate = sum(1 for r in results if r.verdict.value == "pass") / len(results)
print(f"Pass rate: {pass_rate:.0%}")
```

### Callbacks & Auto-Save

Hook into evaluation results for CI/CD notifications and automatic persistence.

```python
def on_eval_done(result):
    if result.verdict.value == "fail":
        notify_slack(f"Skill {result.skill_name} FAILED: {result.overall_score:.1%}")

@evaluate(
    skill="./SKILL.md",
    auto_save=True,                # Persist to SQLite automatically
    on_complete=on_eval_done,      # Callback after each evaluation
    thresholds={"task_completion": 1.0},
)
def my_agent(query: str) -> str:
    ...
```

## Next Steps

- [Metrics Reference](metrics.md) — All 11 metrics explained in detail
- [Framework Adapters](adapters.md) — Import traces from Gemini, LangChain, OpenAI, OTel
- [Custom Metrics](custom-metrics.md) — Build your own evaluation metrics
- [CLI Reference](cli.md) — Command-line interface
