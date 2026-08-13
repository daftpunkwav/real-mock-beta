"""系统成长记忆单测。"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from interview_service.services.growth import learning as learning_mod
from interview_service.services.growth.learning import get_system_insights, record_interview_learning


def test_record_and_insights(tmp_path, monkeypatch):
    monkeypatch.setattr(learning_mod, "_memory_path", lambda: tmp_path / "sys.json")

    session = SimpleNamespace(
        id=42,
        role="后端工程师",
        company="bytedance",
        overall_score=85,
        agent_state=json.dumps({
            "tool_trace": [{"tool": "github_get_readme"}],
            "weak_points": ["缓存一致性"],
            "followup_clues": ["vague", "missing_data", "vague"],
        }),
    )

    record_interview_learning(session, report={"weaknesses": ["系统设计"]})
    insights = get_system_insights()
    assert insights["company_session_counts"].get("bytedance") == 1
    # followup_category_hits 现在记录真实追问类别（来自 followup_clues）
    assert insights["followup_category_hits"].get("vague") == 2
    assert insights["followup_category_hits"].get("missing_data") == 1
    # 工具调用统计单独记录在 tool_call_counts
    assert insights["tool_call_counts"].get("github_get_readme") == 1
    assert any("缓存" in (p.get("point") or "") for p in insights["recent_probes"])
    assert Path(tmp_path / "sys.json").exists()
