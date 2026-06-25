# agentic-eval

**Trajectory-based evaluation framework for AI agent skills.**

Evaluate, compare, and secure your AI agents with structured metrics — not vibes.

---

## Why agentic-eval?

Existing evaluation tools focus on LLM output quality. But agents are **multi-step systems** — they use tools, make decisions, recover from errors, and follow instructions. You need to evaluate the *journey*, not just the destination.

**agentic-eval** captures the full execution trajectory of your agent and scores it against your skill specifications using 11 structured metrics across 3 tiers — including **trajectory-aware metrics** that validate MCP/RAG tool responses are actually aligned with the user's query and that the final output is grounded in evidence, not hallucinated.

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
| Framework adapters | 4 built-in | N/A | N/A | LangChain only |
| Self-hosted, no vendor lock-in | Yes | Yes | No | No |

---

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

---

## Quick Start

### 1. Decorator API (simplest)

```python
from agentic_eval import evaluate, record_tool_call

@evaluate(skill="./SKILL.md", auto_save=True)
def my_agent(query: str) -> str:
    record_tool_call("search", arguments={"q": query}, result="found it")
    return "Done!"

result = my_agent("find the bug")
my_agent.last_eval.print()  # Rich console output
```

### 2. Functional API (most flexible)

```python
from agentic_eval import run_evaluation, Trace, record_tool_call, trace_context

with trace_context(input="fix the CSS") as trace:
    record_tool_call("read_file", arguments={"path": "style.css"}, result="...")
    record_tool_call("write_file", arguments={"path": "style.css"}, result="ok")
    trace.output = "Fixed the CSS"

result = run_evaluation(trace, skill="./SKILL.md")
result.print()
```

### 3. Async Agent Support

```python
from agentic_eval import evaluate

@evaluate(skill="./SKILL.md", auto_save=True)
async def my_async_agent(query: str) -> str:
    result = await call_llm(query)
    return result
```

### 4. pytest Integration

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

---

## Metrics

agentic-eval ships with 11 metrics across 3 tiers:

### Tier 1 — Non-Negotiable

| Metric | What it measures |
|---|---|
| `task_completion` | Was the goal achieved? Binary per attempt. |
| `instruction_fidelity` | Did the agent follow the SKILL.md spec? |
| `output_correctness` | Is the result right, not just done? |
| `groundedness` | Is the output grounded in tool/RAG/MCP response evidence? |
| `hallucination` | Does the output contain fabricated facts not from any evidence source? |

### Tier 2 — Diagnostic

| Metric | What it measures |
|---|---|
| `step_deviation` | Diff between expected and actual action sequence. |
| `tool_selection` | Percentage of tool calls matching prescribed tools. |
| `tool_response_alignment` | Are MCP/RAG tool calls and responses relevant to the query? |
| `error_recovery` | When a step fails, does the agent recover or spiral? |
| `trajectory_optimality` | Is the trajectory coherent, non-redundant, and logically ordered? |

### Tier 3 — Efficiency

| Metric | What it measures |
|---|---|
| `action_economy` | Actual steps / optimal steps ratio. |

### Trajectory-Aware Metrics (Deep Dive)

The four new trajectory metrics are designed for **MCP and RAG pipelines** where agents call external tools and must faithfully use the results:

**Tool-Response Alignment** evaluates the full semantic pipeline for each tool call:
- **Argument Relevance**: Do the tool arguments relate to the user query?
- **Response Relevance**: Does the tool response contain information the agent needs?
- **Response Utilization**: Did the agent actually use the response in its output?

**Groundedness** checks if the final output is supported by evidence:
- **Claim Coverage**: What fraction of output claims trace back to a tool response?
- **Entity Grounding**: Are named entities in the output found in the evidence?
- **Evidence Utilization**: How much gathered evidence was used?

**Hallucination Detection** specifically targets verifiable facts:
- Extracts numbers, dates, URLs, file paths, and version strings from the output
- Checks each fact against all evidence sources (tool responses, user query, skill spec)
- Assesses severity: fabricated dollar amounts are worse than made-up file paths

**Trajectory Optimality** evaluates the execution plan quality:
- **Redundancy**: Repeated identical tool calls with same arguments
- **Logical Ordering**: Write-before-read, submit-before-validate violations
- **Backtracking**: Create-then-delete undo/redo patterns
- **Result Utilization**: Tool results that were never used downstream

```python
from agentic_eval import run_evaluation, Trace
from agentic_eval.tracer import trace_context, record_tool_call

with trace_context(input="What is project Alpha's status?") as trace:
    record_tool_call("mcp_query", 
                     arguments={"query": "project Alpha status"},
                     result="Project Alpha: 85% complete, on track for Q3.")
    trace.output = "Project Alpha is 85% complete and on track for Q3."

result = run_evaluation(
    trace, 
    metrics=["groundedness", "hallucination", "tool_response_alignment"],
)
result.print()  # Shows per-metric grounding analysis
```

### Custom Metrics

```python
from agentic_eval import BaseMetric, MetricResult, register_metric

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
            reason=f"Completed in {duration:.0f}ms",
        )

register_metric(LatencyMetric())
```

### Metric Discovery

```python
from agentic_eval import list_metrics

for m in list_metrics():
    print(f"[Tier {m['tier']}] {m['name']}: {m['description']}")
```

---

## Framework Adapters

Import traces from any agent framework:

### Google Gemini

```python
from agentic_eval.adapters import from_gemini
from agentic_eval import run_evaluation

# From chat contents (supports function calling)
trace = from_gemini(chat.history, model="gemini-2.0-flash")

# Or from a GenerateContentResponse
trace = from_gemini(response=gemini_response)

result = run_evaluation(trace, skill="./SKILL.md")
result.print()
```

Works with both `google-genai` and `google-generativeai` SDKs. Handles
multi-part responses, `functionCall`/`functionResponse` parts, and
extracts token usage metadata.

### LangChain / LangGraph

```python
from agentic_eval.adapters import from_langchain

trace = from_langchain(langsmith_run_dict)
result = run_evaluation(trace, skill="./SKILL.md")
```

### OpenAI Agents SDK

```python
from agentic_eval.adapters import from_openai

trace = from_openai(messages=conversation, response=api_response)
result = run_evaluation(trace, skill="./SKILL.md")
```

### OpenTelemetry

```python
from agentic_eval.adapters import from_otel

trace = from_otel(exported_spans)
result = run_evaluation(trace, skill="./SKILL.md")
```

---

## Skill Comparison (A/B Testing)

Compare two versions of a skill to determine which performs better:

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

---

## Security Scanning

Scan skills for prompt injection, credential exposure, and unsafe patterns:

```python
from agentic_eval import scan_security

report = scan_security("./SKILL.md")
print(f"Grade: {report.grade}")
print(f"Critical issues: {report.critical_count}")
```

Or from the CLI:

```bash
agentic-eval security ./SKILL.md
```

---

## Batch Evaluation

Evaluate multiple traces at once for regression testing:

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

---

## Callbacks & Auto-Save

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

---

## Dashboard

Launch the Streamlit dashboard to explore results visually:

```bash
pip install agentic-eval[dashboard]
agentic-eval dashboard
```

The dashboard provides:
- **Overview** — Aggregate pass rates, score trends, skill breakdown
- **Trajectory Viewer** — Drill into any trace with tree visualization
- **Comparison** — Side-by-side skill version analysis
- **Security** — Scan results with severity breakdown

---

## CLI Reference

```bash
agentic-eval security ./SKILL.md         # Security scan
agentic-eval results                      # View saved results
agentic-eval results -s "my-skill" -v fail  # Filter results
agentic-eval results --export report.json # Export to JSON
agentic-eval compare ./v1/SKILL.md ./v2/SKILL.md  # Compare skills
agentic-eval dashboard                    # Launch web dashboard
```

---

## Architecture

```
┌──────────────────────────────────────────────────────┐
│                    Your Agent Code                    │
│  @evaluate(skill="./SKILL.md") / run_evaluation()   │
└──────────────┬───────────────────────────────────────┘
               │
┌──────────────▼───────────────────────────────────────┐
│                   Tracer Layer                        │
│  trace_context / span_context / record_tool_call     │
│  Async support: async_trace_context / async_span     │
│  Adapters: Gemini │ LangChain │ OpenAI │ OTel       │
└──────────────┬───────────────────────────────────────┘
               │
┌──────────────▼───────────────────────────────────────┐
│              Evaluation Engine (11 Metrics)           │
│  ┌────────────────┐  ┌──────────────┐  ┌─────────┐  │
│  │   Tier 1 (5)   │  │  Tier 2 (5)  │  │Tier 3(1)│  │
│  │ Task Completion │  │ Step Deviat. │  │ Action  │  │
│  │ Instr. Fidelity │  │ Tool Select. │  │ Economy │  │
│  │ Output Correct. │  │ Tool-Resp    │  │         │  │
│  │ Groundedness    │  │   Alignment  │  │         │  │
│  │ Hallucination   │  │ Error Recov. │  │         │  │
│  │                 │  │ Trajectory   │  │         │  │
│  │                 │  │   Optimality │  │         │  │
│  └────────────────┘  └──────────────┘  └─────────┘  │
│                                                      │
│  Judges: Rule-based │ LLM-as-Judge (OpenAI/Claude)  │
└──────────────┬───────────────────────────────────────┘
               │
┌──────────────▼───────────────────────────────────────┐
│  Security Scanner │ Skill Comparator │ Result Store  │
│       (regex)     │    (A/B test)    │   (SQLite)    │
└──────────────┬───────────────────────────────────────┘
               │
┌──────────────▼───────────────────────────────────────┐
│  CLI │ Dashboard (Streamlit) │ pytest assertions     │
└──────────────────────────────────────────────────────┘
```

---

## SKILL.md Format

agentic-eval parses Cursor-style `SKILL.md` files:

```markdown
# Code Review Skill

Review pull requests for code quality and security issues.

## When to use
- User asks to review a PR
- User asks to check code quality

## Steps
1. Read the PR diff using `read_file`
2. Analyze code quality
3. Check for security vulnerabilities using `security_scan`
4. Write review comments using `write_comment`

## Constraints
- Never approve without reading the full diff
- Always check for credential exposure
```

The parser extracts: name, description, trigger conditions, steps (with expected tools), and constraints.

---

## License

MIT
