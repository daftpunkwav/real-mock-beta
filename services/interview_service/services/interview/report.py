"""面试报告生成与持久化。"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from shared.core.prompts import with_agent_output_rules
from interview_service.models import InterviewSession
from interview_service.schemas import InterviewReport, ScoreBreakdown
from shared.capabilities.ai.llm.client import LLMClient

logger = logging.getLogger(__name__)

_REPORT_LOCKS: dict[int, asyncio.Lock] = {}

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


def _fallback_report() -> InterviewReport:
    return InterviewReport(
        overall_score=70,
        score_breakdown=ScoreBreakdown(
            overall=70, technical=70, communication=70,
            project_depth=70, problem_solving=70, presence=70, politeness=70,
        ),
        weaknesses=["报告生成时遇到错误，请重试"],
        improvement_suggestions=["完成更多面试练习以获得准确评估"],
    )


def _apply_interrupt_politeness_penalty(
    session: InterviewSession,
    report: InterviewReport,
) -> InterviewReport:
    """候选人打断面试官：硬性下调礼貌/表达分，避免模型忽略统计。"""
    try:
        state = json.loads(session.agent_state or "{}")
        c_int = int(state.get("candidate_interrupts") or 0) if isinstance(state, dict) else 0
    except Exception:
        c_int = 0
    if c_int <= 0:
        return report
    sb = report.score_breakdown
    penalty = min(30, c_int * 6)
    sb.politeness = max(0, (sb.politeness or 75) - penalty)
    sb.communication = max(0, sb.communication - max(2, penalty // 2))
    sb.presence = max(0, sb.presence - max(1, penalty // 3))
    # 略微拉动总分
    dims = [
        sb.technical,
        sb.communication,
        sb.project_depth,
        sb.problem_solving,
        sb.presence,
        sb.politeness,
    ]
    sb.overall = int(round(sum(dims) / len(dims)))
    report.overall_score = sb.overall
    tip = f"本场打断面试官 {c_int} 次，话轮礼仪有扣分；建议等对方说完再接话。"
    if tip not in report.interview_suggestions:
        report.interview_suggestions = [tip, *list(report.interview_suggestions or [])]
    return report


async def generate_report(
    session: InterviewSession,
    llm: LLMClient,
    face_records: list[dict] | None = None,
) -> InterviewReport:
    """根据面试对话生成评估报告。

    失败时向上抛出，避免调用方把假分数 ``_fallback_report`` 当作正式结果落库。
    仅在明确需要降级展示且不落库的场景再调用 :func:`_fallback_report`。
    """
    try:
        data = await llm.chat_json(build_report_messages(session, face_records))
        return InterviewReport(**data)
    except Exception as e:
        logger.error("报告生成失败: %s", e)
        raise


_REPORT_GENERATING_SENTINEL = '{"_generating":true}'


async def generate_and_persist_report(
    session: InterviewSession,
    llm: LLMClient,
    db: Session,
    face_records: list[dict] | None = None,
) -> InterviewReport:
    """生成报告并写入 session / GrowthRecord（同一事务）。

    任意阶段失败整体回滚，避免「session 已 completed 但 GrowthRecord 缺失」。
    同 session 并发调用时加进程内锁 + DB 哨兵 CAS，避免 WS/HTTP / 多 worker 双打。
    """
    from sqlalchemy import or_, update

    from shared.core.constants import SessionStatus
    from interview_service.models import GrowthRecord

    sid = int(session.id)
    lock = _REPORT_LOCKS.setdefault(sid, asyncio.Lock())
    async with lock:
        try:
            db.refresh(session)
        except Exception:
            pass
        raw = (session.report or "").strip()
        if raw and raw != "{}" and raw != _REPORT_GENERATING_SENTINEL:
            try:
                return InterviewReport.model_validate_json(raw)
            except Exception:
                pass
        if raw == _REPORT_GENERATING_SENTINEL:
            # 另一路径正在生成：短暂等待后若已落库则返回
            for _ in range(30):
                await asyncio.sleep(0.2)
                try:
                    db.refresh(session)
                except Exception:
                    break
                cur = (session.report or "").strip()
                if cur and cur != _REPORT_GENERATING_SENTINEL and cur != "{}":
                    try:
                        return InterviewReport.model_validate_json(cur)
                    except Exception:
                        break
            # 超时仍卡在哨兵：清哨兵后由本路径重试
            try:
                db.execute(
                    update(InterviewSession)
                    .where(InterviewSession.id == sid)
                    .where(InterviewSession.report == _REPORT_GENERATING_SENTINEL)
                    .values(report="{}")
                )
                db.commit()
            except Exception:
                db.rollback()

        # DB CAS：仅当报告仍为空时写入哨兵
        claimed = False
        try:
            result = db.execute(
                update(InterviewSession)
                .where(InterviewSession.id == sid)
                .where(
                    or_(
                        InterviewSession.report.is_(None),
                        InterviewSession.report == "",
                        InterviewSession.report == "{}",
                    )
                )
                .values(report=_REPORT_GENERATING_SENTINEL)
            )
            db.commit()
            # SQLAlchemy Result.rowcount 类型标注不完整，显式取 rowcount 防并发双写
            claimed = (getattr(result, "rowcount", 0) or 0) > 0
        except Exception:
            db.rollback()
            claimed = False

        if not claimed:
            try:
                db.refresh(session)
            except Exception:
                pass
            cur = (session.report or "").strip()
            if cur and cur != _REPORT_GENERATING_SENTINEL and cur != "{}":
                try:
                    return InterviewReport.model_validate_json(cur)
                except Exception:
                    pass
            # 可能刚被其他方设为哨兵：再等一轮
            if cur == _REPORT_GENERATING_SENTINEL:
                for _ in range(30):
                    await asyncio.sleep(0.2)
                    try:
                        db.refresh(session)
                    except Exception:
                        break
                    cur2 = (session.report or "").strip()
                    if cur2 and cur2 != _REPORT_GENERATING_SENTINEL and cur2 != "{}":
                        try:
                            return InterviewReport.model_validate_json(cur2)
                        except Exception:
                            break

        try:
            # 确保 ORM 对象与哨兵一致
            try:
                db.refresh(session)
            except Exception:
                pass
            report = await generate_report(session, llm, face_records)
            report = _apply_interrupt_politeness_penalty(session, report)

            growth = GrowthRecord(
                profile_id=session.profile_id,
                session_id=session.id,
                weak_skills=json.dumps(report.weaknesses, ensure_ascii=False),
                common_mistakes=json.dumps(report.weaknesses[:3], ensure_ascii=False),
                training_plan=json.dumps(report.training_plan, ensure_ascii=False),
            )

            try:
                session.report = report.model_dump_json()
                session.overall_score = report.overall_score
                session.status = SessionStatus.COMPLETED.value
                session.ended_at = datetime.now(timezone.utc)
                db.add(growth)
                db.commit()
                try:
                    from interview_service.services.growth.learning import record_interview_learning

                    record_interview_learning(session, report=report.model_dump())
                except Exception:
                    pass
            except Exception:
                db.rollback()
                raise
            return report
        except Exception:
            # 异常路径清哨兵，避免永久卡住
            try:
                db.execute(
                    update(InterviewSession)
                    .where(InterviewSession.id == sid)
                    .where(InterviewSession.report == _REPORT_GENERATING_SENTINEL)
                    .values(report="{}")
                )
                db.commit()
            except Exception:
                try:
                    db.rollback()
                except Exception:
                    pass
            raise


async def stream_report(
    session: InterviewSession,
    llm: LLMClient,
    face_records: list[dict] | None = None,
):
    """流式生成评估报告，每次 yield 一个 token 字符串。

    与同步版不同：流式版本不复用 ``chat_json``，而是直接 ``chat_stream`` 让前端可以
    增量渲染。返回的最终结构仍通过 SSE 的 ``done`` 事件承载（由调用方解析）。
    """
    report_messages = build_report_messages(session, face_records)
    async for token in llm.chat_stream(report_messages, temperature=0.3):
        yield token