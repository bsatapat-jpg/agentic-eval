"""Parser for SKILL.md files -- extracts structured skill specifications."""

from __future__ import annotations

import re
from pathlib import Path

import frontmatter

from .models import SkillSpec, SkillStep


def parse_skill(source: str | Path) -> SkillSpec:
    """Parse a SKILL.md file or raw markdown string into a SkillSpec.

    Args:
        source: Path to a SKILL.md file, or raw markdown content.

    Returns:
        Parsed SkillSpec with extracted steps, tools, constraints, etc.
    """
    if isinstance(source, Path):
        path = source
    elif isinstance(source, str) and len(source) < 260 and "\n" not in source:
        path = Path(source)
    else:
        path = None

    if path is not None and path.exists():
        raw_content = path.read_text(encoding="utf-8")
        file_path = str(path.resolve())
    else:
        raw_content = str(source)
        file_path = None

    post = frontmatter.loads(raw_content)
    meta = dict(post.metadata) if post.metadata else {}
    body = post.content

    name = meta.get("name", "")
    description = meta.get("description", "")

    if not name:
        name = _extract_title(body)
    if not description and not meta.get("description"):
        description = _extract_first_paragraph(body)

    steps = _extract_steps(body, meta)
    expected_tools = _extract_tools(body, meta)
    constraints = _extract_constraints(body, meta)
    trigger_conditions = _extract_triggers(body, meta)

    input_schema = meta.get("input_schema") or meta.get("inputSchema")
    output_schema = meta.get("output_schema") or meta.get("outputSchema")

    return SkillSpec(
        name=name,
        description=description,
        trigger_conditions=trigger_conditions,
        steps=steps,
        expected_tools=expected_tools,
        constraints=constraints,
        input_schema=input_schema,
        output_schema=output_schema,
        raw_content=raw_content,
        file_path=file_path,
        version_hash=SkillSpec.compute_hash(raw_content),
    )


def _extract_title(body: str) -> str:
    """Extract the first H1 heading as the skill name."""
    match = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
    return match.group(1).strip() if match else ""


def _extract_first_paragraph(body: str) -> str:
    """Extract first non-heading paragraph as description."""
    lines = body.strip().split("\n")
    paragraph_lines: list[str] = []
    in_paragraph = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            if in_paragraph:
                break
            continue
        if stripped == "":
            if in_paragraph:
                break
            continue
        in_paragraph = True
        paragraph_lines.append(stripped)

    return " ".join(paragraph_lines)


def _extract_steps(body: str, meta: dict) -> list[SkillStep]:
    """Extract workflow steps from the markdown body or frontmatter."""
    if "steps" in meta and isinstance(meta["steps"], list):
        return _parse_meta_steps(meta["steps"])

    return _parse_body_steps(body)


def _parse_meta_steps(raw_steps: list) -> list[SkillStep]:
    """Parse steps from frontmatter YAML list."""
    steps: list[SkillStep] = []
    for i, item in enumerate(raw_steps):
        if isinstance(item, str):
            steps.append(SkillStep(order=i + 1, description=item))
        elif isinstance(item, dict):
            steps.append(
                SkillStep(
                    order=item.get("order", i + 1),
                    description=item.get("description", item.get("step", str(item))),
                    expected_tools=item.get("tools", item.get("expected_tools", [])),
                    required=item.get("required", True),
                )
            )
    return steps


def _parse_body_steps(body: str) -> list[SkillStep]:
    """Extract steps from markdown sections like 'Workflow', 'Steps', 'Instructions'."""
    step_section = _find_section(
        body, ["workflow", "steps", "instructions", "procedure", "how to use"]
    )
    if not step_section:
        return _extract_numbered_or_bulleted_steps(body)

    return _extract_numbered_or_bulleted_steps(step_section)


def _find_section(body: str, headings: list[str]) -> str | None:
    """Find a markdown section by heading keywords."""
    patterns = [
        rf"^#+\s*(?:.*\b{re.escape(h)}\b.*)$"
        for h in headings
    ]
    for pattern in patterns:
        match = re.search(pattern, body, re.MULTILINE | re.IGNORECASE)
        if match:
            start = match.end()
            next_heading = re.search(r"^#+\s", body[start:], re.MULTILINE)
            end = start + next_heading.start() if next_heading else len(body)
            return body[start:end].strip()
    return None


def _extract_numbered_or_bulleted_steps(text: str) -> list[SkillStep]:
    """Extract ordered/bulleted list items as steps."""
    pattern = r"^\s*(?:\d+[.)]\s+|[-*]\s+)(.+)$"
    matches = re.findall(pattern, text, re.MULTILINE)

    steps: list[SkillStep] = []
    for i, desc in enumerate(matches):
        desc_clean = desc.strip().rstrip(".")
        if len(desc_clean) < 5:
            continue
        tools = _extract_inline_tools(desc_clean)
        steps.append(
            SkillStep(order=i + 1, description=desc_clean, expected_tools=tools)
        )
    return steps


def _extract_inline_tools(text: str) -> list[str]:
    """Extract tool names from backtick-quoted references in text."""
    return re.findall(r"`(\w+(?:_\w+)*)`", text)


def _extract_tools(body: str, meta: dict) -> list[str]:
    """Extract expected tools from frontmatter or body."""
    if "tools" in meta:
        raw = meta["tools"]
        if isinstance(raw, list):
            return [str(t) for t in raw]
        if isinstance(raw, str):
            return [t.strip() for t in raw.split(",")]

    if "expected_tools" in meta:
        return list(meta["expected_tools"])

    tools_section = _find_section(body, ["tools", "available tools", "tool usage"])
    if tools_section:
        return re.findall(r"`(\w+(?:_\w+)*)`", tools_section)

    return []


def _extract_constraints(body: str, meta: dict) -> list[str]:
    """Extract constraints/guardrails from frontmatter or body."""
    if "constraints" in meta:
        return list(meta["constraints"])

    section = _find_section(
        body, ["constraints", "guardrails", "rules", "limitations", "important"]
    )
    if section:
        items = re.findall(r"^\s*(?:\d+[.)]\s+|[-*]\s+)(.+)$", section, re.MULTILINE)
        return [item.strip() for item in items]

    return []


def _extract_triggers(body: str, meta: dict) -> list[str]:
    """Extract trigger conditions from frontmatter or body."""
    if "triggers" in meta:
        return list(meta["triggers"])
    if "trigger_conditions" in meta:
        return list(meta["trigger_conditions"])

    section = _find_section(body, ["trigger", "when to use", "activation"])
    if section:
        items = re.findall(r"^\s*(?:\d+[.)]\s+|[-*]\s+)(.+)$", section, re.MULTILINE)
        return [item.strip() for item in items]

    return []
