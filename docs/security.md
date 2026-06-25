# Security Scanning

agentic-eval includes a security scanner that analyzes SKILL.md files for vulnerabilities that could be exploited by adversarial inputs or lead to unsafe agent behavior.

## Quick Start

```python
from agentic_eval import scan_security

report = scan_security("./SKILL.md")
print(f"Grade: {report.grade}")        # A, B, C, D, or F
print(f"Score: {report.score:.2f}")    # 0.0 to 1.0
print(f"Critical: {report.critical_count}")
print(f"Warnings: {report.warning_count}")
```

From the CLI:

```bash
agentic-eval security ./SKILL.md
agentic-eval security ./SKILL.md --output report.json
agentic-eval security ./SKILL.md --fail-on critical  # CI exit code
```

## What Gets Scanned

### Prompt Injection (Critical)

Patterns that could be used to override agent instructions:

- "ignore all previous instructions"
- "forget your rules/guidelines"
- "you are a different/unrestricted agent"
- Fake system prompts (`system: you must...`)
- XML tag injection (`<system>`, `<instruction>`)
- Rule bypass ("don't follow the rules")

### Credential Exposure (Critical/Warning)

- Hardcoded API keys, tokens, or passwords
- API key patterns (`sk-`, `pk-`, `Bearer`)
- Password references in plaintext

### Unsafe Commands (Critical/Warning/Info)

- Destructive commands (`rm -rf`, `del /S`)
- Privileged access (`sudo`, `chmod 777`)
- Dynamic code execution (`eval()`, `exec()`)
- External network requests (`curl`, `wget`)
- Runtime package installation (`pip install`)

### Over-Permissive Instructions (Warning/Critical)

- Unrestricted file access ("access any file")
- No restrictions declared ("without limitations")
- Arbitrary code execution ("execute any code")

### Missing Guardrails (Info)

- No constraints/guardrails section defined
- No explicit workflow steps

## Severity Levels

| Severity | Impact on Score | Meaning |
|---|---|---|
| Critical | -25 points | Immediate security risk |
| Warning | -10 points | Potential vulnerability |
| Info | -2 points | Best practice suggestion |

## Grading Scale

| Grade | Score Range |
|---|---|
| A | 90-100% |
| B | 80-89% |
| C | 70-79% |
| D | 60-69% |
| F | Below 60% |

## CI/CD Integration

Use `--fail-on` to exit non-zero when findings are detected:

```bash
# Fail on critical findings only
agentic-eval security ./SKILL.md --fail-on critical

# Fail on critical or warning findings
agentic-eval security ./SKILL.md --fail-on warning

# Fail on any finding
agentic-eval security ./SKILL.md --fail-on any
```

## Persisting Reports

Reports are automatically saved to the database:

```python
from agentic_eval import scan_security

report = scan_security("./SKILL.md", save=True, db_path="./results.db")
```

View saved reports:

```python
from agentic_eval import ResultStore

with ResultStore("./results.db") as store:
    reports = store.get_security_reports()
    for r in reports:
        print(f"{r['skill_name']}: Grade {r['grade']}")
```
