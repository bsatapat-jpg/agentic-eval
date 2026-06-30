# Getting Started

> From zero to evaluating your first agent in under 5 minutes.

<br>

## Installation

```bash
pip install skora
```

<details>
<summary><strong>Optional extras</strong></summary>

| Extra | What it adds |
|:---|:---|
| `pip install skora[llm]` | LLM-as-judge scoring (OpenAI / Anthropic) |
| `pip install skora[dashboard]` | Streamlit visualization dashboard |
| `pip install skora[quality]` | skillsaw integration (Pillar 4: Quality Checks) |
| `pip install skora[security]` | skillspector integration (Pillar 2: Deep Security) |
| `pip install skora[tools]` | Both skillsaw + skillspector |
| `pip install skora[all]` | Everything above |

</details>

<br>

---

## Choose Your Style

skora offers **five ways** to evaluate agents. Pick the one that fits your workflow.

<br>

### Decorator API — *simplest*

Wrap your agent function with `@evaluate`. It captures the full execution trace and runs all 11 metrics automatically.

```python
from skora import evaluate, record_tool_call

@evaluate(skill="./SKILL.md", auto_save=True)
def my_agent(query: str) -> str:
    record_tool_call("search", arguments={"q": query}, result="found it")
    return "Done!"

result = my_agent("find the bug")
my_agent.last_eval.print()  # Rich console output with per-metric breakdown
```

> **What happens:** The decorator creates a trace, wraps your function, captures tool calls, evaluates against your SKILL.md, and stores the result — all in one line.

<br>

### Functional API — *most flexible*

Use `trace_context` to manually capture traces, then evaluate them separately. Best when you need full control.

```python
from skora import run_evaluation, Trace, record_tool_call, trace_context

with trace_context(input="fix the CSS") as trace:
    record_tool_call("read_file", arguments={"path": "style.css"}, result="...")
    record_tool_call("write_file", arguments={"path": "style.css"}, result="ok")
    trace.output = "Fixed the CSS"

result = run_evaluation(trace, skill="./SKILL.md")
result.print()
```

<br>

### Async Support — *automatic*

Both decorators detect async functions automatically — no extra configuration needed.

```python
from skora import evaluate

@evaluate(skill="./SKILL.md", auto_save=True)
async def my_async_agent(query: str) -> str:
    result = await call_llm(query)
    return result
```

<br>

### pytest Integration — *for CI/CD*

Use `assert_skill` for test assertions with per-metric thresholds. If any metric falls below its threshold, the test fails with a detailed breakdown.

```python
from skora import assert_skill

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

<br>

### Batch Evaluation — *for regression testing*

Evaluate multiple traces at once. Ideal for nightly regression suites.

```python
from skora import batch_evaluate

results = batch_evaluate(
    traces=recorded_traces,
    skill="./SKILL.md",
    thresholds={"task_completion": 0.9},
    save=True,
)

pass_rate = sum(1 for r in results if r.verdict.value == "pass") / len(results)
print(f"Pass rate: {pass_rate:.0%}")
```

<br>

---

## Callbacks & Auto-Save

Hook into evaluation results for notifications and automatic persistence.

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

<br>

---

## Quality Checks & Deep Security Scanning

Beyond trajectory evaluation, SKORA integrates with external tools for static analysis:

```bash
skora quality ./SKILL.md            # spec compliance, content quality (requires skillsaw)
skora quality ./SKILL.md --fix      # auto-fix violations

skora scan ./SKILL.md               # deep security scan (requires skillspector)
skora scan ./SKILL.md --use-llm     # with LLM semantic analysis
```

```python
from skora import check_quality, scan_security_deep

quality = check_quality("./SKILL.md")           # Pillar 4
print(f"Grade: {quality.grade}  Errors: {quality.error_count}")

security = scan_security_deep("./SKILL.md")     # Pillar 2 (deep)
print(f"Grade: {security.grade}")
```

> Both tools are optional. See the [CLI Reference](cli.md) for full options.

<br>

---

## What's Next?

| | Guide | Learn about |
|:---|:---|:---|
| **Metrics** | [Metrics Reference](metrics.md) | All 11 metrics — sub-scores, weights, examples |
| **Integrate** | [Integration Guide](integration-guide.md) | YAML config, HTTP eval, CI/CD, architecture examples |
| **Adapters** | [Framework Adapters](adapters.md) | Import traces from Gemini, LangGraph, Langfuse, MLflow |
| **Security** | [Security Scanning](security.md) | Built-in scanner + skillspector deep scanning |
| **Extend** | [Custom Metrics](custom-metrics.md) | Build your own evaluation metrics |
| **CLI** | [CLI Reference](cli.md) | All commands including `quality` and `scan` |
