"""Integration with NVIDIA SkillSpector CLI for deep security scanning (Pillar 2)."""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path

from ..models import SecurityFinding, SecurityReport, Severity

logger = logging.getLogger(__name__)

_SEVERITY_MAP = {
    "critical": Severity.CRITICAL,
    "high": Severity.CRITICAL,
    "medium": Severity.WARNING,
    "warning": Severity.WARNING,
    "low": Severity.INFO,
    "info": Severity.INFO,
    "note": Severity.INFO,
}


def is_skillspector_available() -> bool:
    """Check whether the skillspector binary is on PATH."""
    return shutil.which("skillspector") is not None


def run_skillspector(path: str | Path, use_llm: bool = False) -> SecurityReport:
    """Run NVIDIA SkillSpector on a skill path.

    If skillspector is not installed, falls back to SKORA's built-in
    security scanner with a warning.

    Args:
        path: Path to a SKILL.md file or directory containing one.
        use_llm: If True, omit --no-llm flag (enables LLM-based analysis).

    Returns:
        SecurityReport compatible with SKORA's existing model.
    """
    skill_path = Path(path).resolve()
    skillspector_bin = shutil.which("skillspector")

    if skillspector_bin is None:
        logger.warning(
            "skillspector is not installed — falling back to SKORA's built-in scanner. "
            "For deeper analysis, install SkillSpector: "
            "pip install skillspector  OR  see https://github.com/NVIDIA/SkillSpector"
        )
        return _fallback_builtin_scan(skill_path)

    cmd = [skillspector_bin, "scan", "--format", "json"]
    if not use_llm:
        cmd.append("--no-llm")
    cmd.append(str(skill_path))

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        logger.error("skillspector timed out after 120s on %s", skill_path)
        return SecurityReport(skill_path=str(skill_path), skill_name=skill_path.stem)

    raw = proc.stdout.strip()
    if not raw:
        logger.warning(
            "skillspector produced no output for %s (exit %d)", skill_path, proc.returncode
        )
        return SecurityReport(skill_path=str(skill_path), skill_name=skill_path.stem)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse skillspector JSON output: %s", exc)
        return SecurityReport(skill_path=str(skill_path), skill_name=skill_path.stem)

    return _parse_skillspector_output(data, str(skill_path))


def _parse_skillspector_output(data: dict, skill_path: str) -> SecurityReport:
    """Convert raw SkillSpector JSON into SKORA's SecurityReport."""
    findings: list[SecurityFinding] = []

    for item in data.get("findings", data.get("results", [])):
        raw_sev = item.get("severity", "info").lower()
        severity = _SEVERITY_MAP.get(raw_sev, Severity.INFO)

        finding = SecurityFinding(
            severity=severity,
            category=item.get("category", item.get("rule_id", "unknown")),
            description=item.get("message", item.get("description", "")),
            location=item.get("file", item.get("location", "")),
            line_number=item.get("line", item.get("line_number")),
            recommendation=item.get("recommendation", item.get("fix", "")),
        )
        findings.append(finding)

    risk_score = data.get("risk_score")
    if risk_score is not None:
        score = max(0.0, min(1.0, 1.0 - risk_score / 100.0))
    else:
        score = data.get("score", 1.0)

    grade = data.get("grade", _score_to_grade(score))

    return SecurityReport(
        skill_path=skill_path,
        skill_name=data.get("skill_name", Path(skill_path).stem),
        findings=findings,
        score=score,
        grade=grade,
    )


def _score_to_grade(score: float) -> str:
    if score >= 0.95:
        return "A+"
    if score >= 0.9:
        return "A"
    if score >= 0.8:
        return "B"
    if score >= 0.7:
        return "C"
    if score >= 0.6:
        return "D"
    return "F"


def _fallback_builtin_scan(skill_path: Path) -> SecurityReport:
    """Use SKORA's built-in security evaluator as a fallback."""
    from ..evaluators.security import SecurityEvaluator

    evaluator = SecurityEvaluator()
    return evaluator.scan_skill(str(skill_path))
