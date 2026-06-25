# CLI Reference

agentic-eval provides a command-line interface for security scanning, viewing results, comparing skills, and launching the dashboard.

## Commands

### `agentic-eval security`

Scan a SKILL.md file for security vulnerabilities.

```bash
agentic-eval security ./SKILL.md
agentic-eval security ./SKILL.md --output report.json
agentic-eval security ./SKILL.md --db ./custom.db
agentic-eval security ./SKILL.md --fail-on critical
```

| Option | Description |
|---|---|
| `SKILL_PATH` | Path to SKILL.md file (required) |
| `--output, -o` | Export report to JSON file |
| `--db` | Database path (default: `./agentic_eval_results.db`) |
| `--fail-on` | Exit non-zero on findings: `critical`, `warning`, or `any` |

### `agentic-eval results`

View stored evaluation results.

```bash
agentic-eval results
agentic-eval results -s "my-skill"
agentic-eval results -s "my-skill" -v fail
agentic-eval results --limit 50
agentic-eval results --export report.json
agentic-eval results --format json
```

| Option | Description |
|---|---|
| `--skill, -s` | Filter by skill name |
| `--verdict, -v` | Filter by verdict: `pass`, `fail`, `partial` |
| `--limit, -l` | Max results to show (default: 20) |
| `--db` | Database path |
| `--export, -e` | Export all results to JSON file |
| `--format` | Output format: `table` (default) or `json` |

### `agentic-eval compare`

Compare two SKILL.md files (security + stored evaluation metrics).

```bash
agentic-eval compare ./v1/SKILL.md ./v2/SKILL.md
agentic-eval compare ./v1/SKILL.md ./v2/SKILL.md --format json
```

| Option | Description |
|---|---|
| `SKILL_A` | First skill path (baseline) |
| `SKILL_B` | Second skill path (candidate) |
| `--db` | Database path |
| `--format` | Output format: `table` (default) or `json` |

### `agentic-eval metrics`

List all registered evaluation metrics.

```bash
agentic-eval metrics
```

### `agentic-eval dashboard`

Launch the Streamlit evaluation dashboard.

```bash
agentic-eval dashboard
agentic-eval dashboard --port 8502
agentic-eval dashboard --db ./custom.db
```

| Option | Description |
|---|---|
| `--port, -p` | Server port (default: 8501) |
| `--db` | Database path |

Requires: `pip install agentic-eval[dashboard]`
