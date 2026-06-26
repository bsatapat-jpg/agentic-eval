# SKILL.md Format

> Define what your agent is *supposed to do* — agentic-eval evaluates how well it actually does it.

agentic-eval parses Cursor-style `SKILL.md` files to extract structured information from both YAML frontmatter and markdown body.

<br>

---

## Quick Example

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

<br>

---

## What Gets Extracted

| Field | Source | Description |
|:---|:---|:---|
| `name` | H1 heading or frontmatter `name` | The skill's display name |
| `description` | First paragraph or frontmatter `description` | What the skill does |
| `trigger_conditions` | "When to use" section or frontmatter `triggers` | When to activate |
| `steps` | "Steps" / "Workflow" section or frontmatter `steps` | Ordered workflow steps |
| `expected_tools` | Backtick-quoted names or frontmatter `tools` | Tools the agent should use |
| `constraints` | "Constraints" / "Rules" section or frontmatter | Guardrails and limitations |
| `input_schema` | Frontmatter `input_schema` | Expected input format |
| `output_schema` | Frontmatter `output_schema` | Expected output format |
| `version_hash` | Auto-computed SHA-256 | Content fingerprint for comparison |

<br>

---

## With YAML Frontmatter

For more structured definitions, use YAML frontmatter:

```markdown
---
name: Data Pipeline Skill
description: Process and transform data from CSV files
tools:
  - read_file
  - pandas_transform
  - write_file
steps:
  - description: Read input CSV
    tools: [read_file]
    required: true
  - description: Transform data
    tools: [pandas_transform]
    required: true
  - description: Write output
    tools: [write_file]
    required: true
constraints:
  - Never modify the original input file
  - Validate data types before transformation
triggers:
  - User asks to process a CSV
  - User asks to transform data
input_schema:
  type: object
  properties:
    file_path: { type: string }
output_schema:
  type: object
  required: [row_count, output_path]
  properties:
    row_count: { type: integer }
    output_path: { type: string }
---

# Data Pipeline Skill

Process and transform data from CSV files.

## Steps
1. Read the input CSV using `read_file`
2. Transform the data using `pandas_transform`
3. Write the output using `write_file`
```

<br>

---

## Section Headings Recognized

The parser looks for these section headings (case-insensitive):

| Category | Recognized headings |
|:---|:---|
| **Steps** | `workflow`, `steps`, `instructions`, `procedure`, `how to use` |
| **Tools** | `tools`, `available tools`, `tool usage` |
| **Constraints** | `constraints`, `guardrails`, `rules`, `limitations`, `important` |
| **Triggers** | `trigger`, `when to use`, `activation` |

<br>

---

## Inline Tool References

Tool names inside backticks within step descriptions are **automatically extracted**:

```markdown
1. Read the file using `read_file`
2. Search with `web_search`
```

> This would extract `["read_file", "web_search"]` as expected tools.

<br>

---

## Using Parsed Skills in Code

```python
from agentic_eval import parse_skill

spec = parse_skill("./SKILL.md")

print(spec.name)             # "Code Review Skill"
print(spec.expected_tools)   # ["read_file", "security_scan", "write_comment"]
print(spec.steps)            # [SkillStep(order=1, ...), ...]
print(spec.constraints)      # ["Never approve without...", "Always check..."]
print(spec.version_hash)     # "a1b2c3d4e5f6g7h8"
```

<br>

---

<p align="center">
  <a href="getting-started.md">Getting Started</a> · <a href="metrics.md">Metrics</a> · <a href="security.md">Security</a> · <a href="comparison.md">Comparison</a>
</p>
