# Architecture

> How scora is built and why.

<br>

---

## System Overview

```
┌──────────────────────────────────────────────────────────────┐
│                      Your Agent Code                         │
│    @evaluate()  ·  run_evaluation()  ·  AgentEvaluator       │
└───────────────────────────┬──────────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────────┐
│                      Tracer Layer                            │
│   trace_context  ·  span_context  ·  record_tool_call        │
│   Async: async_trace_context  ·  async_span_context          │
│   Adapters: LangGraph · Langfuse · MLflow · Gemini · ...     │
└───────────────────────────┬──────────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────────┐
│                 Evaluation Engine (11 Metrics)                │
│                                                              │
│   Tier 1 (5)           Tier 2 (5)           Tier 3 (1)       │
│   ┌──────────────┐    ┌──────────────┐    ┌────────────┐     │
│   │ Completion   │    │ Step Deviat. │    │  Action    │     │
│   │ Fidelity     │    │ Tool Select. │    │  Economy   │     │
│   │ Correctness  │    │ Alignment    │    └────────────┘     │
│   │ Groundedness │    │ Recovery     │                       │
│   │ Hallucinate  │    │ Optimality   │                       │
│   └──────────────┘    └──────────────┘                       │
│                                                              │
│   Judges:  Rule-based  ·  LLM-as-Judge (OpenAI / Claude)    │
└───────────────────────────┬──────────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────────┐
│   Security Scanner  ·  Skill Comparator  ·  Result Store     │
└───────────────────────────┬──────────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────────┐
│   CLI  ·  Dashboard  ·  pytest  ·  YAML CI/CD  ·  HTTP Eval │
└──────────────────────────────────────────────────────────────┘
```

<br>

---

## Package Structure

```
scora/
│
├── src/scora/
│   ├── __init__.py                  # Public API exports
│   ├── models.py                    # Pydantic data models
│   ├── tracer.py                    # Context managers for trace capture
│   ├── decorators.py                # @trace_skill and @evaluate
│   ├── skill_parser.py              # SKILL.md → SkillSpec parser
│   ├── api.py                       # High-level functions
│   ├── config.py                    # YAML config loading
│   ├── agent_evaluator.py           # HTTP live agent evaluation
│   ├── assertions.py                # assert_skill for pytest
│   ├── store.py                     # SQLite persistence
│   ├── cli.py                       # Click CLI entry point
│   │
│   ├── metrics/
│   │   ├── base.py                  # BaseMetric + MetricRegistry
│   │   ├── task_completion.py       #   Tier 1
│   │   ├── instruction_fidelity.py  #   Tier 1
│   │   ├── output_correctness.py    #   Tier 1
│   │   ├── groundedness.py          #   Tier 1
│   │   ├── hallucination.py         #   Tier 1
│   │   ├── step_deviation.py        #   Tier 2
│   │   ├── tool_selection.py        #   Tier 2
│   │   ├── tool_response_alignment.py  # Tier 2
│   │   ├── trajectory_optimality.py    # Tier 2
│   │   ├── error_recovery.py        #   Tier 2
│   │   └── action_economy.py        #   Tier 3
│   │
│   ├── evaluators/
│   │   ├── skill_adherence.py       # Composite scoring pipeline
│   │   ├── security.py              # Vulnerability scanner
│   │   └── comparator.py            # A/B skill comparison
│   │
│   └── adapters/
│       ├── langgraph_adapter.py     # LangGraph / Aegra
│       ├── langfuse_adapter.py      # Langfuse
│       ├── mlflow_adapter.py        # MLflow
│       ├── gemini_adapter.py        # Google Gemini
│       ├── langchain_adapter.py     # LangChain / LangSmith
│       ├── openai_adapter.py        # OpenAI
│       └── otel_adapter.py          # OpenTelemetry
│
├── dashboard/
│   ├── app.py                       # Streamlit entry point
│   └── pages/
│       ├── overview.py
│       ├── trajectory.py
│       ├── comparison.py
│       └── security.py
│
├── tests/                           # 215+ tests
└── docs/                            # You are here
```

<br>

---

## Key Design Decisions

<br>

### Pydantic models throughout

All data structures — `Trace`, `Span`, `EvalResult`, `SkillSpec`, `SecurityReport` — use Pydantic for validation, serialization, and clear contracts. This ensures type safety at boundaries and makes serialization to JSON/SQLite trivial.

<br>

### Context variables for tracing

Uses `contextvars.ContextVar` to track the current trace and span, allowing nested spans without manual threading. This means `record_tool_call()` works anywhere in the call stack, not just in the immediate function.

<br>

### LRU-cached skill parsing

Parsed SKILL.md specs are cached with `functools.lru_cache(maxsize=128)` to avoid re-parsing on every decorator invocation. This keeps evaluation fast even in hot loops.

<br>

### WAL-mode SQLite

The result store uses Write-Ahead Logging for concurrent read/write access without locking. This allows the dashboard to read while evaluations are still writing.

<br>

### Dual scoring modes

Every metric that supports it has both a **fast heuristic scorer** (no API keys needed) and an **LLM-as-judge scorer** for production-grade semantic evaluation. The heuristic mode runs in milliseconds; LLM mode provides deeper analysis.

<br>

### Weighted composite scoring

The `SkillAdherenceEvaluator` computes a weighted average across all metrics, with weights summing to 1.0. Unknown metrics get a default weight of 0.1. Weights are fully configurable per-evaluation.

<br>

### Adapter pattern for framework support

Each adapter is a standalone module that converts framework-specific data to the common `Trace` model. This makes adding new framework support a single-file, self-contained task with no changes to the evaluation engine.

<br>

---

<p align="center">
  <a href="getting-started.md">Getting Started</a> · <a href="metrics.md">Metrics</a> · <a href="adapters.md">Adapters</a> · <a href="custom-metrics.md">Custom Metrics</a>
</p>
