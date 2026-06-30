<p align="center">
  <h1 align="center">SKORA</h1>
  <p align="center">
    <strong>Skill Knowledge, Observability, Rating & Analysis</strong>
  </p>
  <p align="center">
    Evaluate the journey, not just the destination.
  </p>
  <p align="center">
    <a href="#installation"><img src="https://img.shields.io/badge/python-3.10%E2%80%933.14-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.10–3.14"></a>
    <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green?style=for-the-badge" alt="MIT License"></a>
    <a href="#metrics"><img src="https://img.shields.io/badge/metrics-11-blueviolet?style=for-the-badge" alt="11 Metrics"></a>
    <a href="#adapters"><img src="https://img.shields.io/badge/adapters-7-orange?style=for-the-badge" alt="7 Adapters"></a>
  </p>
</p>

<br>

> Existing evaluation tools focus on LLM output quality. But agents are **multi-step systems** — they call tools, make decisions, recover from errors, and follow skill specifications. You need to evaluate the *entire trajectory*, not just the final answer.

**SKORA** captures the full execution trace of your agent — every tool call, every LLM decision, every retrieval step — and scores it against your skill specs using **11 structured metrics** across 3 tiers.

<br>

## Highlights

```
  Trajectory Scoring        MCP/RAG Validation       Hallucination Detection
  ──────────────────        ──────────────────       ───────────────────────
  11 metrics across         Validates tool args,     Extracts dates, numbers,
  3 tiers evaluate the      response relevance,      URLs, versions from output
  full execution path       and utilization           and checks every fact

  Groundedness              Security Scanning        A/B Skill Comparison
  ────────────────          ─────────────────        ────────────────────
  Checks if output is       Detects prompt           Compare skill versions
  backed by evidence        injection, credential    with statistical lift
  from tool responses       exposure, unsafe code    and per-metric breakdown
```

<br>

## 4 Pillars of Evaluation

SKORA implements a **Standardized Skill Evaluation Framework** — four complementary dimensions that together answer *"is this skill production-ready?"*

```
  ┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────┐
  │  Pillar 1            │  │  Pillar 2            │  │  Pillar 3            │  │  Pillar 4            │
  │  Skill Adherence     │  │  Security             │  │  Skill Comparison    │  │  Quality Checks      │
  │─────────────────────│  │─────────────────────│  │─────────────────────│  │─────────────────────│
  │  Does the agent      │  │  Is the skill robust  │  │  Is version B better │  │  Does the skill meet │
  │  follow SKILL.md?    │  │  against attacks?     │  │  than version A?     │  │  format & content    │
  │                      │  │                       │  │                      │  │  standards?          │
  │  ✔ 11 metrics        │  │  ✔ Built-in scanner   │  │  ✔ A/B comparison    │  │  ✔ skillsaw (40+     │
  │  ✔ 3 tiers           │  │  ✔ skillspector deep  │  │  ✔ Statistical lift  │  │    rules, auto-fix)  │
  │  ✔ Trajectory eval   │  │    scan (68 patterns) │  │  ✔ Ground truth eval │  │  ✔ Spec compliance   │
  └─────────────────────┘  └─────────────────────┘  └─────────────────────┘  └─────────────────────┘
```

| Pillar | What it answers | SKORA feature | External tool |
|:---|:---|:---|:---|
| **1 — Skill Adherence** | Does the agent follow the SKILL.md spec? | `run_evaluation()`, 11 metrics across 3 tiers | — |
| **2 — Security** | Is the skill safe from adversarial inputs? | `scan_security()` (built-in), `scan_security_deep()` | [skillspector](https://github.com/NVIDIA/SkillSpector) (68 patterns) |
| **3 — Skill Comparison** | Is version B better than A? | `compare_skills()` with statistical lift | — |
| **4 — Quality Checks** | Does the skill meet structural standards? | `check_quality()` | [skillsaw](https://pypi.org/project/skillsaw/) (40+ rules, auto-fix) |

> **Unified evaluation:** `evaluate_skill_full()` runs all 4 pillars in one call and returns a combined `FullEvalReport`.

<br>

## How it compares

| Feature | SKORA | DeepEval | AgentOps | LangSmith |
|:---|:---:|:---:|:---:|:---:|
| Trajectory-based scoring (11 metrics) | **Yes** | No | Partial | Partial |
| MCP / RAG response validation | **Yes** | No | No | No |
| Hallucination detection | **Yes** | Yes | No | No |
| Groundedness scoring | **Yes** | Yes | No | Partial |
| SKILL.md parsing | **Yes** | No | No | No |
| Decorator API (sync + async) | **Yes** | Yes | No | No |
| Security scanning (built-in + [skillspector](https://github.com/NVIDIA/SkillSpector)) | **Yes** | No | No | No |
| Quality checks ([skillsaw](https://pypi.org/project/skillsaw/) integration) | **Yes** | No | No | No |
| A/B skill comparison | **Yes** | No | No | No |
| Framework adapters | **7** | N/A | N/A | 1 |
| Config-driven CI/CD (YAML) | **Yes** | No | No | Partial |
| Live agent HTTP evaluation | **Yes** | No | No | No |
| Self-hosted, no vendor lock-in | **Yes** | Yes | No | No |

<br>

## Installation

```bash
pip install skora
```

<details>
<summary><strong>Optional extras</strong></summary>

```bash
pip install skora[llm]        # LLM-as-judge scoring (OpenAI / Anthropic)
pip install skora[dashboard]  # Streamlit visualization dashboard
pip install skora[quality]    # skillsaw integration (Pillar 4: Quality Checks)
pip install skora[security]   # skillspector integration (Pillar 2: Deep Security)
pip install skora[tools]      # Both skillsaw + skillspector
pip install skora[all]        # Everything
```
</details>

<details>
<summary><strong>External tool installation (optional)</strong></summary>

SKORA works standalone, but integrates with external tools for deeper analysis:

```bash
# Pillar 4 — Quality Checks (skillsaw)
pip install skillsaw                                          # 40+ rules, auto-fix

# Pillar 2 — Deep Security Scanning (NVIDIA SkillSpector)
git clone https://github.com/NVIDIA/SkillSpector.git
cd SkillSpector && pip install -e .                           # 68 patterns, 17 categories
```

> Both tools are optional. SKORA's built-in scanner handles security without skillspector, and quality checks are only available when skillsaw is installed.

</details>

<br>

## Quick Start

### 1-line decorator

```python
from skora import evaluate, record_tool_call

@evaluate(skill="./SKILL.md", auto_save=True)
def my_agent(query: str) -> str:
    record_tool_call("search", arguments={"q": query}, result="found it")
    return "Done!"

result = my_agent("find the bug")
my_agent.last_eval.print()       # rich console output with per-metric breakdown
```

### Functional API

```python
from skora import run_evaluation, trace_context, record_tool_call

with trace_context(input="fix the CSS") as trace:
    record_tool_call("read_file", arguments={"path": "style.css"}, result="...")
    record_tool_call("write_file", arguments={"path": "style.css"}, result="ok")
    trace.output = "Fixed the CSS"

result = run_evaluation(trace, skill="./SKILL.md")
result.print()
```

### Config-driven CI (zero Python)

```yaml
# skora.yaml
project: my-agent
skills:
  - path: ./skills/search/SKILL.md
    thresholds: { task_completion: 0.9, groundedness: 0.8 }
agent:
  url: http://localhost:8000/api/chat
  body_template:
    messages: [{ role: user, content: "${query}" }]
test_cases:
  - input: "What is the project status?"
    expected_tools: ["rag_search"]
ci:
  fail_below: 0.7
```

```bash
skora ci   # reads config, calls agent, evaluates, exits non-zero on failure
```

<br>

## Metrics

11 metrics across 3 tiers — from non-negotiable pass/fail to efficiency diagnostics.

### Tier 1 — Non-Negotiable

| Metric | What it measures |
|:---|:---|
| `task_completion` | Was the goal achieved? |
| `instruction_fidelity` | Did the agent follow the SKILL.md spec? |
| `output_correctness` | Is the result right, not just done? |
| `groundedness` | Is the output backed by tool/RAG/MCP evidence? |
| `hallucination` | Does the output contain fabricated facts? |

### Tier 2 — Diagnostic

| Metric | What it measures |
|:---|:---|
| `step_deviation` | Diff between expected and actual action sequence |
| `tool_selection` | Were the right tools used? (precision + recall) |
| `tool_response_alignment` | Are MCP/RAG calls and responses relevant to the query? |
| `error_recovery` | Does the agent recover from failures or spiral? |
| `trajectory_optimality` | Is the execution plan coherent and non-redundant? |

### Tier 3 — Efficiency

| Metric | What it measures |
|:---|:---|
| `action_economy` | Actual steps / optimal steps ratio |

<br>

## Adapters

Import traces from any agent framework — no code changes required.

```
 ┌─────────────┐  ┌───────────┐  ┌──────────┐  ┌───────────┐
 │  LangGraph  │  │ Langfuse  │  │  MLflow  │  │  Gemini   │
 └──────┬──────┘  └─────┬─────┘  └────┬─────┘  └─────┬─────┘
        │               │             │               │
        ▼               ▼             ▼               ▼
 ┌─────────────────────────────────────────────────────────┐
 │                       SKORA                            │
 │              from_langgraph()  from_langfuse()          │
 │              from_mlflow()    from_gemini()             │
 │              from_langchain() from_openai() from_otel() │
 └─────────────────────────────────────────────────────────┘
```

| Adapter | Source | Input format |
|:---|:---|:---|
| `from_langgraph` | LangGraph / Aegra | State dict, message list, streaming events |
| `from_langfuse` | Langfuse | Observations API v2 or legacy trace dict |
| `from_mlflow` | MLflow | Trace object, serialised dict, or span list |
| `from_gemini` | Google Gemini | Chat history, GenerateContentResponse |
| `from_langchain` | LangChain / LangSmith | Run dicts with child_runs |
| `from_openai` | OpenAI | ChatCompletion messages + tool calls |
| `from_otel` | OpenTelemetry | Exported OTel spans (JSON) |

<details>
<summary><strong>Example: Evaluate a LangGraph agent</strong></summary>

```python
from skora.adapters import from_langgraph
from skora import run_evaluation

final_state = await graph.ainvoke({"messages": [HumanMessage("query")]})
trace = from_langgraph(final_state)
result = run_evaluation(trace, skill="./SKILL.md")
result.print()
```
</details>

<details>
<summary><strong>Example: Evaluate from Langfuse traces</strong></summary>

```python
from skora.adapters import from_langfuse
from skora import run_evaluation

observations = langfuse.api.observations.get_many(trace_id="...", fields="core,io,usage")
trace = from_langfuse(observations.data)
result = run_evaluation(trace, skill="./SKILL.md")
```
</details>

<br>

## More Features

<details>
<summary><strong>Async support</strong></summary>

```python
@evaluate(skill="./SKILL.md", auto_save=True)
async def my_async_agent(query: str) -> str:
    return await call_llm(query)
```
</details>

<details>
<summary><strong>pytest assertions</strong></summary>

```python
from skora import assert_skill

def test_search_skill():
    result = my_agent("find the bug")
    assert_skill(actual=result, skill="./SKILL.md",
                 thresholds={"task_completion": 1.0, "groundedness": 0.8})
```
</details>

<details>
<summary><strong>Security scanning</strong></summary>

```python
from skora import scan_security, scan_security_deep

# Built-in scanner (always available)
report = scan_security("./SKILL.md")
print(f"Grade: {report.grade}  Critical: {report.critical_count}")

# Deep scan via NVIDIA SkillSpector (68 patterns, 17 categories)
report = scan_security_deep("./SKILL.md")
```

```bash
skora security ./SKILL.md --fail-on critical   # built-in
skora scan ./SKILL.md --fail-on critical        # deep scan via skillspector
```
</details>

<details>
<summary><strong>Quality checks (skillsaw)</strong></summary>

```python
from skora import check_quality

report = check_quality("./SKILL.md")
print(f"Grade: {report.grade}  Spec compliant: {report.spec_compliant}")
```

```bash
skora quality ./SKILL.md                # lint for 40+ rules
skora quality ./SKILL.md --fix          # auto-fix issues
skora quality ./SKILL.md --fail-on error  # CI gate
```
</details>

<details>
<summary><strong>Full 4-pillar evaluation</strong></summary>

```python
from skora import evaluate_skill_full

report = evaluate_skill_full("./SKILL.md", trace=my_trace)
print(f"Overall: {report.overall_grade}")
print(f"Adherence: {report.adherence.overall_score if report.adherence else 'N/A'}")
print(f"Security:  {report.security.grade if report.security else 'N/A'}")
print(f"Quality:   {report.quality.grade if report.quality else 'N/A'}")
```
</details>

<details>
<summary><strong>A/B skill comparison</strong></summary>

```python
from skora import compare_skills

result = compare_skills("./v1/SKILL.md", "./v2/SKILL.md", traces_a=v1, traces_b=v2)
print(result.verdict)   # a_better / b_better / no_difference
print(f"Lift: {result.lift:+.2%}")
```
</details>

<details>
<summary><strong>Live agent HTTP evaluation</strong></summary>

```python
from skora import AgentEvaluator

evaluator = AgentEvaluator(
    url="http://localhost:8000/api/chat",
    body_template={"messages": [{"role": "user", "content": "${query}"}]},
)
results = evaluator.evaluate(
    test_cases=[{"input": "What is the status?"}],
    skill="./SKILL.md",
)
```
</details>

<details>
<summary><strong>Custom metrics</strong></summary>

```python
from skora import BaseMetric, MetricResult, register_metric

class LatencyMetric(BaseMetric):
    name = "latency"
    description = "Evaluates response time"
    tier = 3

    def score(self, trajectory, skill_spec=None, expected_output=None):
        duration = trajectory.duration_ms or 0
        return MetricResult(metric_name=self.name, score=max(0, 1 - duration / 30000),
                            reason=f"{duration:.0f}ms")

register_metric(LatencyMetric())
```
</details>

<details>
<summary><strong>Streamlit dashboard</strong></summary>

```bash
pip install skora[dashboard]
skora dashboard
```

Overview, trajectory viewer, comparison, and security pages.
</details>

<details>
<summary><strong>CLI reference</strong></summary>

```bash
skora security ./SKILL.md           # scan for vulnerabilities (built-in)
skora scan ./SKILL.md               # deep security scan via skillspector
skora quality ./SKILL.md            # quality checks via skillsaw
skora quality ./SKILL.md --fix      # auto-fix quality issues
skora results -s "my-skill" -v fail  # view stored results
skora compare ./v1.md ./v2.md        # compare skill versions
skora metrics                        # list all metrics
skora dashboard                      # launch web dashboard
skora ci                             # run evaluation from YAML config
```
</details>

<br>

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                      Your Agent Code                         │
│    @evaluate()  /  run_evaluation()  /  AgentEvaluator       │
└───────────────────────────┬──────────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────────┐
│                      Tracer Layer                            │
│   trace_context  ·  span_context  ·  record_tool_call        │
│   Adapters: LangGraph · Langfuse · MLflow · Gemini · ...     │
└───────────────────────────┬──────────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────────┐
│                    4-Pillar Evaluation                        │
│                                                              │
│  Pillar 1: Adherence     Pillar 2: Security                  │
│  ┌──────────────────┐    ┌──────────────────────────────┐    │
│  │ 11 Metrics (3T)  │    │ Built-in Scanner (18 rules)  │    │
│  │ LLM + Heuristic  │    │ + skillspector (68 patterns) │    │
│  └──────────────────┘    └──────────────────────────────┘    │
│                                                              │
│  Pillar 3: Comparison    Pillar 4: Quality                   │
│  ┌──────────────────┐    ┌──────────────────────────────┐    │
│  │ A/B Testing      │    │ skillsaw (40+ rules)         │    │
│  │ Ground Truth     │    │ Spec compliance + auto-fix   │    │
│  │ Statistical Lift │    │ Content intelligence         │    │
│  └──────────────────┘    └──────────────────────────────┘    │
│                                                              │
│   Judges:  Rule-based  ·  LLM-as-Judge (OpenAI / Claude)    │
└───────────────────────────┬──────────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────────┐
│   Result Store  ·  Integrations (skillsaw · skillspector)    │
└───────────────────────────┬──────────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────────┐
│   CLI  ·  Dashboard (Streamlit)  ·  pytest  ·  YAML CI/CD   │
└──────────────────────────────────────────────────────────────┘
```

<br>

## Documentation

| | Guide | What you'll learn |
|:---|:---|:---|
| **Start** | [Getting Started](docs/getting-started.md) | Installation, decorator, functional, async, pytest, batch |
| **Metrics** | [Metrics Reference](docs/metrics.md) | All 11 metrics — sub-scores, weights, LLM judge, examples |
| **Integrate** | [Integration Guide](docs/integration-guide.md) | YAML config, HTTP eval, CI/CD, architecture-specific examples |
| **Adapters** | [Framework Adapters](docs/adapters.md) | LangGraph, Langfuse, MLflow, Gemini, LangChain, OpenAI, OTel |
| **Skills** | [SKILL.md Format](docs/skill-format.md) | Write and structure skill specifications |
| **Security** | [Security Scanning](docs/security.md) | Vulnerability detection, grading, CI integration |
| **Compare** | [Skill Comparison](docs/comparison.md) | A/B testing between skill versions |
| **Extend** | [Custom Metrics](docs/custom-metrics.md) | Build and register your own evaluation metrics |
| **CLI** | [CLI Reference](docs/cli.md) | All commands and options |
| **Dashboard** | [Dashboard](docs/dashboard.md) | Streamlit visualization setup and pages |
| **Design** | [Architecture](docs/architecture.md) | System design, package structure, decisions |

<br>

## Contributing

Contributions are welcome! Please open an issue or submit a pull request.

## License

MIT
