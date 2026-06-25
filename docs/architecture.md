# Architecture

## System Overview

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

## Package Structure

```
agentic-eval/
├── src/agentic_eval/
│   ├── __init__.py              # Public API exports
│   ├── models.py                # Pydantic data models (Trace, Span, EvalResult, etc.)
│   ├── tracer.py                # Context managers for capturing traces
│   ├── decorators.py            # @trace_skill and @evaluate decorators
│   ├── skill_parser.py          # SKILL.md → SkillSpec parser
│   ├── api.py                   # High-level functions (run_evaluation, etc.)
│   ├── assertions.py            # assert_skill for pytest
│   ├── store.py                 # SQLite result persistence
│   ├── cli.py                   # Click CLI entry point
│   ├── metrics/
│   │   ├── base.py              # BaseMetric + MetricRegistry
│   │   ├── task_completion.py
│   │   ├── instruction_fidelity.py
│   │   ├── output_correctness.py
│   │   ├── groundedness.py          # Tier 1: evidence grounding
│   │   ├── hallucination.py         # Tier 1: fabrication detection
│   │   ├── step_deviation.py
│   │   ├── tool_selection.py
│   │   ├── tool_response_alignment.py  # Tier 2: MCP/RAG alignment
│   │   ├── trajectory_optimality.py    # Tier 2: plan quality
│   │   ├── error_recovery.py
│   │   └── action_economy.py
│   ├── evaluators/
│   │   ├── skill_adherence.py   # Composite scoring pipeline
│   │   ├── security.py          # Vulnerability scanner
│   │   └── comparator.py        # A/B skill comparison
│   └── adapters/
│       ├── gemini_adapter.py
│       ├── langchain_adapter.py
│       ├── openai_adapter.py
│       └── otel_adapter.py
├── dashboard/
│   ├── app.py                   # Streamlit entry point
│   └── pages/
│       ├── overview.py
│       ├── trajectory.py
│       ├── comparison.py
│       └── security.py
├── tests/
└── docs/
```

## Key Design Decisions

**Pydantic models throughout** — All data structures use Pydantic for validation, serialization, and clear contracts.

**Context variables for tracing** — Uses `contextvars.ContextVar` to track the current trace and span, allowing nested spans without manual threading.

**LRU-cached skill parsing** — Parsed SKILL.md specs are cached with `functools.lru_cache(maxsize=128)` to avoid re-parsing on every decorator invocation.

**WAL-mode SQLite** — The result store uses Write-Ahead Logging for concurrent read/write access without locking.

**Dual scoring modes** — Every metric that supports it has both a fast heuristic scorer (no API keys needed) and an LLM-as-judge scorer for production-grade semantic evaluation.

**Weighted composite scoring** — The `SkillAdherenceEvaluator` computes a weighted average across all metrics, with weights summing to 1.0. Unknown metrics get a default weight of 0.1.
