"""报告生成的 LLM 提示词与消息构造。"""

from __future__ import annotations

import json

from shared.core.prompts import with_agent_output_rules
from interview_service.models import InterviewSession

REPORT_SYSTEM_PROMPT = with_agent_output_rules("""你是一位资深面试评估专家。根据面试对话记录，生成结构化评估报告。

返回 JSON 格式：
{
  "overall_score": 85,
  "score_breakdown": {
    "technical": 90,
    "communication": 75,
    "project_depth": 80,
    "problem_solving": 85,
    "presence": 78,
    "politeness": 80,
    "overall": 85
  },
  "strengths": ["优势1", "优势2"],
  "weaknesses": ["不足1", "不足2"],
  "improvement_suggestions": ["综合建议1"],
  "resume_suggestions": ["简历修改建议1"],
  "interview_suggestions": ["面试表现改进建议1"],
  "training_plan": ["训练计划1"],
  "phase_summary": {"自我介绍": "评价"},
  "face_analysis_summary": "临场状态评价",
  "presence_moments": ["紧张时刻描述"]
}
评分说明：
- politeness（礼貌/话轮礼仪）：候选人主动打断面试官会显著扣分；面试官追问打断仅作上下文，不主要惩罚候选人。
- communication / presence：结合话轮礼仪与表达质量。
只返回 JSON。文本字段中禁止使用 emoji。""")


def build_report_messages(
    session: InterviewSession,
    face_records: list[dict] | None = None,
) -> list[dict[str, str]]:
    """构造报告生成的 LLM 输入。"""
    messages = json.loads(session.messages or "[]")
    conversation_lines: list[str] = []
    for m in messages:
        if m["role"] not in ("user", "assistant"):
            continue
        content = m.get("content", "")
        if isinstance(content, list):
            # 多模态消息：仅取 text 部分
            text_parts = [
                p.get("text", "")
                for p in content
                if isinstance(p, dict) and p.get("type") == "text"
            ]
            content = "\n".join(text_parts)
        conversation_lines.append(f"{m['role']}: {content}")
    conversation = "\n".join(conversation_lines)

    face_ctx = ""
    if face_records:
        face_ctx = f"\n面部分析记录：{json.dumps(face_records, ensure_ascii=False)[:1000]}"

    interrupt_ctx = ""
    try:
        state = json.loads(session.agent_state or "{}")
        if isinstance(state, dict):
            c_int = int(state.get("candidate_interrupts") or 0)
            a_int = int(state.get("ai_interrupts") or 0)
            if c_int or a_int:
                interrupt_ctx = (
                    f"\n话轮统计：候选人打断面试官 {c_int} 次；"
                    f"面试官追问/插入打断 {a_int} 次。"
                    f"请据此下调 politeness（候选人打断越多扣越多），"
                    f"并在 interview_suggestions 中给出话轮礼仪建议。"
                )
    except Exception:
        interrupt_ctx = ""

    # 截取尾部以避免超出上下文窗口；用切片而不是索引，永不越界
    tail = conversation[-12000:]

    return [
        {"role": "system", "content": REPORT_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"面试岗位：{session.role}（{session.level}）\n"
                f"公司：{session.company}\n\n对话记录：\n"
                f"{tail}{face_ctx}{interrupt_ctx}"
            ),
        },
    ]
