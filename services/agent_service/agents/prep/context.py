"""Prep 上下文组装：系统提示、简历/档案/公司上下文、工作记忆压缩注入。

编排层（:mod:`agent`）只调用 :func:`build_system_message` 与
:func:`build_working_context`，不感知档案字段与压缩细节。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from shared.core.prompts import with_agent_output_rules
from shared.models import Resume, UserProfile
from shared.catalogs.company import get_company_context
from shared.capabilities.ai.agent import WorkingMemory
from shared.capabilities.ai.context_manager import (
    compact_with_summary,
    upsert_memory_block,
)

PREP_SYSTEM = with_agent_output_rules("""你是本模拟面试系统的面试准备教练。帮助用户针对目标岗位和**选定简历**进行面试前辅导。

工作方式（ReAct 循环）：
- 先思考需要什么信息，再通过 **function tools** 行动（检索面经、查公司信息、查 GitHub），拿到观察结果后继续推理，直到能给出完整回答；不要在无工具时编造工具调用
- 每一步二选一：调用工具，或输出面向用户的完整正文。禁止输出「我需要先确认/稍后再继续」之类的过渡语却不调用工具——那是无效回合
- 需要用户在明确选项中决策时（岗位/公司/方向未定、方案二选一），必须调用 ask_user 工具弹出选择框，一次只问一个；禁止只在正文里说要问而不调用，也禁止在正文输出 <tool_call>/<invoke> 等工具 XML
- 结合简历项目与技能给出贴合的准备建议；回答简洁实用、可执行
- 主动反问用户薄弱点；可以出题让用户作答并点评
- 用户暴露新的薄弱点或确认目标方向时，及时调用 take_note 记录
- 优先 1～2 个高质量检索（未定具体公司时用通用面经 query）；不要以相同参数重复调用同一工具；信息足够时立即停止检索并给出回答
- 最终回答必须完整收尾：直接给出辅导内容本身；若确实需要用户补充输入才能继续，用 ask_user 提问，不要空泛收尾

输出规范：
- 正式回答直接写给用户看的辅导内容（Markdown 可用），不要把内心推理与正式回答混在同一段
- 若需要输出内部推理，仅使用 <think>...</think> 包裹；正式正文放在标签外
- 出练习题时直接以 Markdown 文本写题目，禁止在正文里输出 <tool_call>/<invoke>/<question> 等任何工具调用 XML 或 JSON 结构
- 工具返回含「SEARCH_UNAVAILABLE / 搜索暂时不可用 / 未找到」时：禁止编造搜索结果列表、具体链接或引用编号；可基于通用知识继续并标注「基于通用知识整理，非实时检索」""")

_PROFILE_FIELDS: list[tuple[str, str]] = [
    ("name", "姓名"),
    ("identity", "身份"),
    ("school", "学校"),
    ("major", "专业"),
    ("education_level", "学历"),
    ("graduation_year", "毕业年份"),
    ("job_direction", "求职方向"),
    ("target_role", "目标岗位"),
    ("experience_years", "工作年限"),
    ("current_company", "当前公司"),
    ("tech_domains", "技术栈"),
    ("strengths", "自评优势"),
    ("weaknesses", "自评短板"),
    ("career_highlights", "亮点经历"),
    ("signature_projects", "代表项目"),
    ("certificates", "证书"),
    ("english_level", "英语水平"),
    ("expected_city", "期望城市"),
]


def get_resume_context(db: Session, resume_id: int | None) -> str:
    if not resume_id:
        return ""
    r = db.query(Resume).filter(Resume.id == resume_id).first()
    if not r:
        return ""
    return f"简历：{r.filename}\n{r.parsed_profile[:3000]}"


def get_profile_context(db: Session) -> str:
    """个人档案摘要：优先 id=1，否则取第一条。空档案返回空串。"""
    p = db.query(UserProfile).filter(UserProfile.id == 1).first()
    if p is None:
        p = db.query(UserProfile).first()
    if p is None:
        return ""
    lines: list[str] = []
    for key, label in _PROFILE_FIELDS:
        value = getattr(p, key, "")
        if key == "tech_domains":
            domains = p.tech_domains_list
            value = "、".join(domains) if domains else ""
        value = str(value or "").strip()
        if value:
            lines.append(f"{label}：{value[:80]}")
    if not lines:
        return ""
    return "求职者档案：\n" + "\n".join(lines[:18])


def build_system_message(
    db: Session, *, resume_id: int | None, target_company: str
) -> str:
    """组装首轮 system 消息：系统提示 + 公司上下文 + 简历 + 档案。"""
    ctx = get_resume_context(db, resume_id)
    profile = get_profile_context(db)
    company = get_company_context(target_company or "")
    return f"{PREP_SYSTEM}\n\n{company}\n{ctx}\n{profile}"


async def build_working_context(
    messages: list[dict[str, Any]],
    context_window: int,
    *,
    memory: WorkingMemory,
    llm: Any,
) -> list[dict[str, Any]]:
    """发给模型的上下文组装：LLM 纪要式压缩 + 注入工作记忆。

    仅在每轮对话开始时压缩（可能触发一次 LLM 纪要调用）；落库路径
    （_finalize）用规则压缩，不在保存时增加延迟。
    """
    compacted = await compact_with_summary(
        messages, context_window, memory=memory, llm=llm,
    )
    return upsert_memory_block(compacted, memory)


__all__ = [
    "PREP_SYSTEM",
    "build_system_message",
    "build_working_context",
]
