"""双库后 interview/agent 域禁止直接 import 共表 ORM。"""

from __future__ import annotations

import ast
from pathlib import Path

FORBIDDEN = frozenset({"Resume", "UserProfile"})
SCAN_ROOTS = (
    Path("interview_service"),
    Path("agent_service"),
)


def _imports_resume_or_profile(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "shared.models":
            for alias in node.names:
                if alias.name in FORBIDDEN:
                    hits.append(f"from shared.models import {alias.name}")
    return hits


def test_interview_agent_no_direct_shared_resume_imports() -> None:
    services = Path(__file__).resolve().parents[1]
    violations: list[str] = []
    for root in SCAN_ROOTS:
        base = services / root
        if not base.is_dir():
            continue
        for path in base.rglob("*.py"):
            if "tests" in path.parts or path.name == "__init__.py":
                continue
            for hit in _imports_resume_or_profile(path):
                violations.append(f"{path.relative_to(services)}: {hit}")
    assert not violations, "应经 candidate_read 读档案/简历:\n" + "\n".join(violations)
