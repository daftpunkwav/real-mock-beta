"""shared 平台层禁止 import 业务服务包（AST 守护）。"""

from __future__ import annotations

import ast
from pathlib import Path

FORBIDDEN_PREFIXES = ("api_service", "agent_service", "interview_service")
SCAN_ROOT = Path("shared")


def _forbidden_service_imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            top = node.module.split(".")[0]
            if top in FORBIDDEN_PREFIXES:
                hits.append(f"from {node.module} import ... (line {node.lineno})")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top in FORBIDDEN_PREFIXES:
                    hits.append(f"import {alias.name} (line {node.lineno})")
    return hits


def test_shared_package_no_business_service_imports() -> None:
    services = Path(__file__).resolve().parents[1]
    base = services / SCAN_ROOT
    violations: list[str] = []
    for path in base.rglob("*.py"):
        if "tests" in path.parts or path.name == "__init__.py":
            continue
        for hit in _forbidden_service_imports(path):
            violations.append(f"{path.relative_to(services)}: {hit}")
    assert not violations, (
        "shared 不得 import 业务服务包；会话 ORM 注册见 bootstrap.sessions_orm:\n"
        + "\n".join(violations)
    )
