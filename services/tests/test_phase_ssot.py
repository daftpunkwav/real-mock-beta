"""阶段单源（SSOT）锁：workflows PhaseDef ↔ InterviewPhaseId ↔ 前端 phases.ts。"""

from __future__ import annotations

import re
from pathlib import Path

from shared.core.constants import InterviewPhaseId
from interview_service.services.interview.workflows import WORKFLOWS, phase_label_map, technical_phase_order


ROOT = Path(__file__).resolve().parents[2]  # RealMock/
FRONTEND_PHASES = ROOT / "apps" / "web" / "src" / "config" / "phases.ts"


def test_all_phase_defs_use_known_ids() -> None:
    known = {m.value for m in InterviewPhaseId}
    used: set[str] = set()
    for wf in WORKFLOWS.values():
        for p in wf.phases:
            assert p.id in known, f"未知阶段 id {p.id}（workflow={wf.id}）"
            used.add(p.id)
    # 枚举中每个 id 至少出现在一个 workflow（避免死枚举）
    unused = known - used
    assert not unused, f"InterviewPhaseId 未使用: {unused}"


def test_technical_phase_order_single_source() -> None:
    assert list(technical_phase_order()) == [p.id for p in WORKFLOWS["technical"].phases]


def test_frontend_phase_order_matches_technical() -> None:
    text = FRONTEND_PHASES.read_text(encoding="utf-8")
    m = re.search(
        r"export const PHASE_ORDER[^=]*=\s*\[([^\]]+)\]",
        text,
        re.DOTALL,
    )
    assert m, "无法解析 frontend PHASE_ORDER"
    ids = re.findall(r'"([a-z_]+)"', m.group(1))
    assert tuple(ids) == technical_phase_order()


def test_frontend_phase_labels_cover_technical() -> None:
    text = FRONTEND_PHASES.read_text(encoding="utf-8")
    labels = phase_label_map()
    for pid in technical_phase_order():
        # 前端映射必须含技术面各阶段，且文案与后端一致
        assert f"{pid}:" in text or f'"{pid}"' in text
        assert labels[pid]
        assert labels[pid] in text, f"前端缺少文案 {pid}={labels[pid]}"
