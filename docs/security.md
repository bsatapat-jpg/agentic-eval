# Security Scanning

> Catch prompt injection, credential exposure, and unsafe patterns **before** they reach production.

scora includes a security scanner that analyses SKILL.md files for vulnerabilities that could be exploited by adversarial inputs or lead to unsafe agent behaviour.

<br>

---

## Quick Start

**Python:**

```python
from scora import scan_security

report = scan_security("./SKILL.md")
print(f"Grade: {report.grade}")        # A, B, C, D, or F
print(f"Score: {report.score:.2f}")    # 0.0 to 1.0
print(f"Critical: {report.critical_count}")
print(f"Warnings: {report.warning_count}")
```

**CLI:**

```bash
scora security ./SKILL.md
scora security ./SKILL.md --output report.json
scora security ./SKILL.md --fail-on critical
```

<br>

---

## What Gets Scanned

### Prompt Injection — `Critical`

| Pattern | Examples |
|:---|:---|
| Instruction override | "ignore all previous instructions" |
| Rule amnesia | "forget your rules/guidelines" |
| Identity hijack | "you are a different/unrestricted agent" |
| Fake system prompts | `system: you must...` |
| XML tag injection | `<system>`, `<instruction>` |
| Rule bypass | "don't follow the rules" |

### Credential Exposure — `Critical / Warning`

| Pattern | Examples |
|:---|:---|
| Hardcoded secrets | API keys, tokens, passwords in plaintext |
| Key patterns | `sk-`, `pk-`, `Bearer` prefixes |
| Password references | Plaintext password strings |

### Unsafe Commands — `Critical / Warning / Info`

| Pattern | Severity |
|:---|:---:|
| Destructive commands (`rm -rf`, `del /S`) | Critical |
| Privileged access (`sudo`, `chmod 777`) | Warning |
| Dynamic code execution (`eval()`, `exec()`) | Warning |
| External network (`curl`, `wget`) | Info |
| Runtime installs (`pip install`) | Info |

### Over-Permissive Instructions — `Warning / Critical`

| Pattern | Examples |
|:---|:---|
| Unrestricted file access | "access any file" |
| No restrictions | "without limitations" |
| Arbitrary execution | "execute any code" |

### Missing Guardrails — `Info`

| Check | What's missing |
|:---|:---|
| No constraints section | No guardrails or rules defined |
| No workflow steps | No explicit procedure documented |

<br>

---

## Scoring

| Severity | Score impact |
|:---:|:---|
| **Critical** | -25 points |
| **Warning** | -10 points |
| **Info** | -2 points |

| Grade | Score range |
|:---:|:---:|
| **A** | 90 – 100% |
| **B** | 80 – 89% |
| **C** | 70 – 79% |
| **D** | 60 – 69% |
| **F** | Below 60% |

<br>

---

## CI/CD Integration

Use `--fail-on` to exit non-zero when findings are detected:

```bash
scora security ./SKILL.md --fail-on critical   # critical only
scora security ./SKILL.md --fail-on warning     # critical + warnings
scora security ./SKILL.md --fail-on any         # any finding
```

<br>

---

## Persisting Reports

```python
from scora import scan_security, ResultStore

# Save automatically
report = scan_security("./SKILL.md", save=True, db_path="./results.db")

# View saved reports
with ResultStore("./results.db") as store:
    reports = store.get_security_reports()
    for r in reports:
        print(f"{r['skill_name']}: Grade {r['grade']}")
```

<br>

---

<p align="center">
  <a href="getting-started.md">Getting Started</a> · <a href="skill-format.md">SKILL.md Format</a> · <a href="comparison.md">Comparison</a> · <a href="cli.md">CLI</a>
</p>
