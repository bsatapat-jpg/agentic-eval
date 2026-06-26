# Dashboard

> Explore your evaluation results visually with an interactive Streamlit dashboard.

<br>

---

## Setup

```bash
pip install agentic-eval[dashboard]
```

## Launch

```bash
agentic-eval dashboard
agentic-eval dashboard --port 8502
agentic-eval dashboard --db ./custom_results.db
```

Or programmatically:

```python
import subprocess
subprocess.run(["agentic-eval", "dashboard", "--port", "8501"])
```

<br>

---

## Pages

### Overview

> The big picture at a glance.

| Widget | What it shows |
|:---|:---|
| Score cards | Total evaluations, pass rate, average score |
| Trend chart | Score over time |
| Skill breakdown | Per-skill pass/fail/partial distribution |
| Verdict pie | Overall verdict distribution |

<br>

### Trajectory Viewer

> Drill into individual agent runs.

| Widget | What it shows |
|:---|:---|
| Span tree | Hierarchical visualization of tool calls, LLM calls, and errors |
| Metric breakdown | Per-metric score bar chart |
| Timeline | Duration-based timeline of spans |
| I/O inspector | Input and output for each span |

<br>

### Comparison

> Side-by-side skill version analysis.

| Widget | What it shows |
|:---|:---|
| Score comparison | Per-metric scores for Skill A vs Skill B |
| Lift indicator | Overall improvement or regression |
| Verdict history | Pass/fail trend per version |

<br>

### Security

> Security scan results at a glance.

| Widget | What it shows |
|:---|:---|
| Grade card | Current security grade and score |
| Trend chart | Grade over time |
| Finding table | Breakdown by severity (critical / warning / info) |
| Skill comparison | Security scores across skills |

<br>

---

<p align="center">
  <a href="getting-started.md">Getting Started</a> · <a href="cli.md">CLI</a> · <a href="metrics.md">Metrics</a> · <a href="architecture.md">Architecture</a>
</p>
