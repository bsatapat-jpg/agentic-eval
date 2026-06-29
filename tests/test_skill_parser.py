"""Tests for SKILL.md parser."""

import pytest

from scora.skill_parser import parse_skill


SAMPLE_SKILL_FRONTMATTER = """\
---
name: test-skill
description: A test skill for evaluation
tools:
  - read_file
  - write_file
  - run_tests
steps:
  - description: Read the input file
    tools: [read_file]
  - description: Process the data
  - description: Write the output
    tools: [write_file]
constraints:
  - Do not delete files
  - Only modify files in the workspace
triggers:
  - User asks to process data
  - User mentions test-skill
---

# Test Skill

This is a test skill that processes data files.

## Workflow

1. Read the input file using `read_file`
2. Process the data according to requirements
3. Write the output using `write_file`
4. Run tests to verify using `run_tests`

## Constraints

- Do not delete files
- Only modify files in the workspace
"""

SAMPLE_SKILL_NO_FRONTMATTER = """\
# My Awesome Skill

This skill helps with code review.

## Steps

1. Read the source code files
2. Analyze for common issues
3. Generate a review report
4. Save the review results

## Tools

Use `read_file`, `analyze_code`, and `write_report` tools.

## Constraints

- Do not modify source code
- Only read files in the repository
"""


class TestParseSkillFrontmatter:
    def test_parses_name(self):
        spec = parse_skill(SAMPLE_SKILL_FRONTMATTER)
        assert spec.name == "test-skill"

    def test_parses_description(self):
        spec = parse_skill(SAMPLE_SKILL_FRONTMATTER)
        assert spec.description == "A test skill for evaluation"

    def test_parses_tools(self):
        spec = parse_skill(SAMPLE_SKILL_FRONTMATTER)
        assert set(spec.expected_tools) == {"read_file", "write_file", "run_tests"}

    def test_parses_steps(self):
        spec = parse_skill(SAMPLE_SKILL_FRONTMATTER)
        assert len(spec.steps) == 3
        assert spec.steps[0].description == "Read the input file"
        assert spec.steps[0].expected_tools == ["read_file"]

    def test_parses_constraints(self):
        spec = parse_skill(SAMPLE_SKILL_FRONTMATTER)
        assert len(spec.constraints) == 2
        assert "Do not delete files" in spec.constraints

    def test_parses_triggers(self):
        spec = parse_skill(SAMPLE_SKILL_FRONTMATTER)
        assert len(spec.trigger_conditions) == 2

    def test_computes_version_hash(self):
        spec = parse_skill(SAMPLE_SKILL_FRONTMATTER)
        assert len(spec.version_hash) == 16

    def test_different_content_different_hash(self):
        spec1 = parse_skill(SAMPLE_SKILL_FRONTMATTER)
        spec2 = parse_skill(SAMPLE_SKILL_NO_FRONTMATTER)
        assert spec1.version_hash != spec2.version_hash


class TestParseSkillNoFrontmatter:
    def test_extracts_title_as_name(self):
        spec = parse_skill(SAMPLE_SKILL_NO_FRONTMATTER)
        assert spec.name == "My Awesome Skill"

    def test_extracts_steps_from_body(self):
        spec = parse_skill(SAMPLE_SKILL_NO_FRONTMATTER)
        assert len(spec.steps) >= 3

    def test_extracts_tools_from_body(self):
        spec = parse_skill(SAMPLE_SKILL_NO_FRONTMATTER)
        assert len(spec.expected_tools) >= 2

    def test_extracts_constraints_from_body(self):
        spec = parse_skill(SAMPLE_SKILL_NO_FRONTMATTER)
        assert len(spec.constraints) >= 1
