# CLI Reference

> Everything you can do from the command line.

<br>

```
agentic-eval <command> [options]
```

| Command | Description |
|:---|:---|
| [`security`](#security) | Scan a SKILL.md for vulnerabilities |
| [`results`](#results) | View stored evaluation results |
| [`compare`](#compare) | Compare two SKILL.md files |
| [`metrics`](#metrics) | List all registered metrics |
| [`ci`](#ci) | Run evaluation from YAML config |
| [`dashboard`](#dashboard) | Launch the Streamlit dashboard |

<br>

---

## `security`

Scan a SKILL.md file for security vulnerabilities.

```bash
agentic-eval security ./SKILL.md
agentic-eval security ./SKILL.md --output report.json
agentic-eval security ./SKILL.md --fail-on critical
```

| Option | Description |
|:---|:---|
| `SKILL_PATH` | Path to SKILL.md file *(required)* |
| `--output, -o` | Export report to JSON file |
| `--db` | Database path (default: `./agentic_eval_results.db`) |
| `--fail-on` | Exit non-zero on findings: `critical`, `warning`, or `any` |

<br>

---

## `results`

View stored evaluation results.

```bash
agentic-eval results
agentic-eval results -s "my-skill" -v fail
agentic-eval results --limit 50 --format json
agentic-eval results --export report.json
```

| Option | Description |
|:---|:---|
| `--skill, -s` | Filter by skill name |
| `--verdict, -v` | Filter by verdict: `pass`, `fail`, `partial` |
| `--limit, -l` | Max results to show (default: 20) |
| `--db` | Database path |
| `--export, -e` | Export all results to JSON file |
| `--format` | Output format: `table` (default) or `json` |

<br>

---

## `compare`

Compare two SKILL.md files (security + stored evaluation metrics).

```bash
agentic-eval compare ./v1/SKILL.md ./v2/SKILL.md
agentic-eval compare ./v1/SKILL.md ./v2/SKILL.md --format json
```

| Option | Description |
|:---|:---|
| `SKILL_A` | First skill path *(baseline)* |
| `SKILL_B` | Second skill path *(candidate)* |
| `--db` | Database path |
| `--format` | Output format: `table` (default) or `json` |

<br>

---

## `metrics`

List all registered evaluation metrics.

```bash
agentic-eval metrics
```

Displays a table with name, tier, and description for each metric.

<br>

---

## `ci`

Run evaluation from a YAML config file. Designed for CI/CD pipelines.

```bash
agentic-eval ci                         # auto-finds agentic-eval.yaml
agentic-eval ci --config ./custom.yaml  # explicit path
agentic-eval ci --fail-below 0.8        # override threshold
agentic-eval ci --format json           # machine-readable output
```

| Option | Description |
|:---|:---|
| `--config, -c` | Path to YAML config file |
| `--fail-below` | Override: fail if overall score is below this |
| `--format` | Output format: `table` (default) or `json` |

> Exit codes: **0** = all checks passed, **1** = threshold violation or error.

See [Integration Guide](integration-guide.md) for full YAML config schema.

<br>

---

## `dashboard`

Launch the Streamlit evaluation dashboard.

```bash
agentic-eval dashboard
agentic-eval dashboard --port 8502
agentic-eval dashboard --db ./custom.db
```

| Option | Description |
|:---|:---|
| `--port, -p` | Server port (default: 8501) |
| `--db` | Database path |

> Requires: `pip install agentic-eval[dashboard]`

<br>

---

<p align="center">
  <a href="getting-started.md">Getting Started</a> · <a href="integration-guide.md">Integration Guide</a> · <a href="security.md">Security</a> · <a href="dashboard.md">Dashboard</a>
</p>
