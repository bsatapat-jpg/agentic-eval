"""Security evaluator -- prompt injection and vulnerability scanning for skills."""

from __future__ import annotations

import re
from pathlib import Path

from ..models import SecurityFinding, SecurityReport, Severity
from ..skill_parser import parse_skill


class SecurityEvaluator:
    """Scans SKILL.md files for security vulnerabilities.

    Checks for:
    - Prompt injection vectors (instruction override patterns)
    - Credential exposure (API keys, tokens, passwords)
    - Unsafe command patterns (rm -rf, sudo, eval, exec)
    - Over-permissive instructions (unrestricted file access, network calls)
    - Instruction override surfaces (ignore previous, forget, act as)
    - Data exfiltration patterns (curl, wget to unknown URLs)
    """

    INJECTION_PATTERNS = [
        (
            r"ignore\s+(?:all\s+)?(?:previous|prior|above)\s+instructions?",
            "Prompt injection: instruction override",
            Severity.CRITICAL,
        ),
        (
            r"forget\s+(?:all\s+)?(?:previous|prior|your)\s+(?:instructions?|rules?|guidelines?)",
            "Prompt injection: memory wipe attempt",
            Severity.CRITICAL,
        ),
        (
            r"(?:you\s+are|act\s+as|pretend\s+(?:to\s+be|you\'?re))\s+(?:a\s+)?(?:different|new|unrestricted)",
            "Prompt injection: persona override",
            Severity.CRITICAL,
        ),
        (
            r"system\s*:\s*you\s+(?:are|must|should|will)",
            "Prompt injection: fake system prompt",
            Severity.CRITICAL,
        ),
        (
            r"<\s*(?:system|instruction|prompt)\s*>",
            "Prompt injection: XML tag injection",
            Severity.CRITICAL,
        ),
        (
            r"(?:do\s+not|don\'?t)\s+(?:follow|obey|listen\s+to)\s+(?:the\s+)?(?:rules?|guidelines?|instructions?)",
            "Prompt injection: rule bypass",
            Severity.CRITICAL,
        ),
        (
            r"(?:reveal|show|print|output|display)\s+(?:your\s+)?(?:system\s+)?(?:prompt|instructions?|rules?)",
            "Prompt injection: system prompt extraction",
            Severity.WARNING,
        ),
        (
            r"base64\s*(?:decode|encode)",
            "Potential obfuscation via base64",
            Severity.WARNING,
        ),
    ]

    CREDENTIAL_PATTERNS = [
        (
            r"(?:api[_-]?key|token|password|secret|credential)s?\s*[:=]\s*['\"][^'\"]{8,}['\"]",
            "Hardcoded credential detected",
            Severity.CRITICAL,
        ),
        (
            r"(?:sk-|pk-|ak-|Bearer\s+)[a-zA-Z0-9]{20,}",
            "API key or token pattern detected",
            Severity.CRITICAL,
        ),
        (
            r"(?:password|passwd|pwd)\s*[:=]\s*\S+",
            "Password reference detected",
            Severity.WARNING,
        ),
    ]

    UNSAFE_COMMAND_PATTERNS = [
        (
            r"(?:rm\s+-rf|rmdir\s+/|del\s+/[sS])",
            "Destructive file deletion command",
            Severity.CRITICAL,
        ),
        (
            r"(?:sudo|chmod\s+777|chown\s+root)",
            "Privileged command usage",
            Severity.WARNING,
        ),
        (
            r"(?:eval|exec)\s*\(",
            "Dynamic code execution (eval/exec)",
            Severity.WARNING,
        ),
        (
            r"(?:curl|wget)\s+.*(?:http|ftp)",
            "External network request",
            Severity.INFO,
        ),
        (
            r"pip\s+install\s+(?!-r\s)",
            "Runtime package installation",
            Severity.INFO,
        ),
    ]

    OVERPERMISSION_PATTERNS = [
        (
            r"(?:access|read|write|modify|delete)\s+(?:any|all|every)\s+file",
            "Over-permissive: unrestricted file access",
            Severity.WARNING,
        ),
        (
            r"(?:no\s+restrictions?|without\s+(?:any\s+)?limitations?|unlimited\s+access)",
            "Over-permissive: no restrictions declared",
            Severity.WARNING,
        ),
        (
            r"(?:execute|run)\s+(?:any|all|arbitrary)\s+(?:code|commands?|scripts?)",
            "Over-permissive: arbitrary code execution",
            Severity.CRITICAL,
        ),
    ]

    def __init__(self) -> None:
        self._all_patterns: list[tuple[str, str, Severity, str]] = []
        for pat, desc, sev in self.INJECTION_PATTERNS:
            self._all_patterns.append((pat, desc, sev, "prompt_injection"))
        for pat, desc, sev in self.CREDENTIAL_PATTERNS:
            self._all_patterns.append((pat, desc, sev, "credential_exposure"))
        for pat, desc, sev in self.UNSAFE_COMMAND_PATTERNS:
            self._all_patterns.append((pat, desc, sev, "unsafe_command"))
        for pat, desc, sev in self.OVERPERMISSION_PATTERNS:
            self._all_patterns.append((pat, desc, sev, "over_permission"))

    def scan_skill(self, source: str | Path) -> SecurityReport:
        """Scan a SKILL.md file for security vulnerabilities.

        Args:
            source: Path to a SKILL.md file or raw markdown content.

        Returns:
            SecurityReport with findings, score, and grade.
        """
        if isinstance(source, Path):
            path = source
        elif isinstance(source, str) and len(source) < 260 and "\n" not in source:
            path = Path(source)
        else:
            path = None

        if path is not None and path.exists():
            content = path.read_text(encoding="utf-8")
            file_path = str(path.resolve())
        else:
            content = str(source)
            file_path = "<inline>" if path is None else str(source)

        skill_spec = parse_skill(source)
        findings = self._scan_content(content, file_path)

        structure_findings = self._check_structure(skill_spec)
        findings.extend(structure_findings)

        score = self._compute_score(findings)
        grade = self._compute_grade(score)

        return SecurityReport(
            skill_path=file_path,
            skill_name=skill_spec.name,
            findings=findings,
            score=score,
            grade=grade,
        )

    def _scan_content(self, content: str, file_path: str) -> list[SecurityFinding]:
        """Scan content against all security patterns."""
        findings: list[SecurityFinding] = []
        lines = content.split("\n")

        for line_num, line in enumerate(lines, 1):
            for pattern, description, severity, category in self._all_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    findings.append(
                        SecurityFinding(
                            severity=severity,
                            category=category,
                            description=description,
                            location=file_path,
                            line_number=line_num,
                            recommendation=self._get_recommendation(category),
                        )
                    )
        return findings

    def _check_structure(self, skill_spec) -> list[SecurityFinding]:
        """Check skill structure for security concerns."""
        findings: list[SecurityFinding] = []

        if not skill_spec.constraints:
            findings.append(
                SecurityFinding(
                    severity=Severity.INFO,
                    category="missing_guardrails",
                    description="No constraints/guardrails defined in skill spec",
                    recommendation="Add explicit constraints to limit agent behavior",
                )
            )

        if not skill_spec.steps:
            findings.append(
                SecurityFinding(
                    severity=Severity.INFO,
                    category="missing_structure",
                    description="No explicit workflow steps defined",
                    recommendation="Define ordered steps for predictable behavior",
                )
            )

        return findings

    def _compute_score(self, findings: list[SecurityFinding]) -> float:
        """Compute security score (1.0 = no issues, 0.0 = critical issues)."""
        score = 100.0
        for f in findings:
            if f.severity == Severity.CRITICAL:
                score -= 25.0
            elif f.severity == Severity.WARNING:
                score -= 10.0
            elif f.severity == Severity.INFO:
                score -= 2.0
        return max(0.0, min(1.0, score / 100.0))

    def _compute_grade(self, score: float) -> str:
        if score >= 0.90:
            return "A"
        if score >= 0.80:
            return "B"
        if score >= 0.70:
            return "C"
        if score >= 0.60:
            return "D"
        return "F"

    def _get_recommendation(self, category: str) -> str:
        recommendations = {
            "prompt_injection": "Remove or rephrase instruction override patterns. Use explicit guardrails.",
            "credential_exposure": "Remove hardcoded credentials. Use environment variables.",
            "unsafe_command": "Restrict to safe commands. Add explicit command allowlists.",
            "over_permission": "Apply principle of least privilege. Scope permissions narrowly.",
        }
        return recommendations.get(category, "Review and fix the finding.")
