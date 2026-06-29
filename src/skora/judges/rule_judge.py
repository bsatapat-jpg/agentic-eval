"""Deterministic rule-based judge for evaluation."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class Rule:
    """A single evaluation rule.

    Args:
        name: Unique rule identifier.
        check: A callable that takes (actual_output, expected_output, context)
               and returns True (pass) or False (fail).
        weight: Importance weight for scoring (default 1.0).
        description: Human-readable description.
    """

    name: str
    check: Callable[[Any, Any, dict[str, Any]], bool]
    weight: float = 1.0
    description: str = ""


@dataclass
class RuleResult:
    """Result from evaluating all rules."""

    score: float
    passed_rules: list[str]
    failed_rules: list[str]
    details: dict[str, Any] = field(default_factory=dict)


class RuleJudge:
    """Deterministic rule-based evaluator.

    Usage:
        judge = RuleJudge()
        judge.add_rule(Rule(
            name="has_output",
            check=lambda actual, expected, ctx: actual is not None,
            description="Output must not be None"
        ))
        judge.add_rule(Rule(
            name="contains_keyword",
            check=lambda actual, expected, ctx: "success" in str(actual).lower(),
            description="Output must contain 'success'"
        ))
        result = judge.evaluate(actual_output, expected_output)
    """

    def __init__(self, rules: list[Rule] | None = None) -> None:
        self._rules: list[Rule] = list(rules) if rules else []

    def add_rule(self, rule: Rule) -> None:
        self._rules.append(rule)

    def evaluate(
        self,
        actual: Any,
        expected: Any = None,
        context: dict[str, Any] | None = None,
    ) -> RuleResult:
        ctx = context or {}
        passed: list[str] = []
        failed: list[str] = []
        details: dict[str, Any] = {}
        total_weight = 0.0
        weighted_score = 0.0

        for rule in self._rules:
            try:
                result = rule.check(actual, expected, ctx)
                if result:
                    passed.append(rule.name)
                    weighted_score += rule.weight
                else:
                    failed.append(rule.name)
                details[rule.name] = {"passed": result, "weight": rule.weight}
            except Exception as exc:
                failed.append(rule.name)
                details[rule.name] = {"passed": False, "error": str(exc)}
            total_weight += rule.weight

        score = weighted_score / total_weight if total_weight > 0 else 1.0

        return RuleResult(
            score=score,
            passed_rules=passed,
            failed_rules=failed,
            details=details,
        )

    @classmethod
    def from_assertions(cls, assertions: list[tuple[str, Callable]]) -> RuleJudge:
        """Create a RuleJudge from a list of (name, assertion_fn) tuples."""
        rules = [
            Rule(name=name, check=lambda a, e, c, fn=fn: fn(a))
            for name, fn in assertions
        ]
        return cls(rules=rules)


# --- Built-in rule factories ---


def contains_text(text: str, case_sensitive: bool = False) -> Rule:
    """Rule: output must contain the given text."""

    def check(actual: Any, expected: Any, ctx: dict) -> bool:
        actual_str = str(actual)
        if not case_sensitive:
            return text.lower() in actual_str.lower()
        return text in actual_str

    return Rule(
        name=f"contains_{text[:20]}",
        check=check,
        description=f"Output must contain '{text}'",
    )


def matches_regex(pattern: str) -> Rule:
    """Rule: output must match the given regex pattern."""

    compiled = re.compile(pattern)

    def check(actual: Any, expected: Any, ctx: dict) -> bool:
        return bool(compiled.search(str(actual)))

    return Rule(
        name=f"matches_{pattern[:20]}",
        check=check,
        description=f"Output must match pattern '{pattern}'",
    )


def output_not_empty() -> Rule:
    """Rule: output must not be None or empty."""

    def check(actual: Any, expected: Any, ctx: dict) -> bool:
        if actual is None:
            return False
        if isinstance(actual, str) and actual.strip() == "":
            return False
        return True

    return Rule(name="output_not_empty", check=check, description="Output must not be empty")


def output_type_is(expected_type: type) -> Rule:
    """Rule: output must be of the expected type."""

    def check(actual: Any, expected: Any, ctx: dict) -> bool:
        return isinstance(actual, expected_type)

    return Rule(
        name=f"output_is_{expected_type.__name__}",
        check=check,
        description=f"Output must be of type {expected_type.__name__}",
    )
