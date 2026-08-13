"""面试选项静态数据（面试域；语音相关数据见 ``shared.capabilities.voice.tts.options``）。

注意：本文件归属面试域（依赖 ``services.interview.workflows`` 与
``services.company.knowledge``）；AVATARS / TTS_VOICES 已迁往
``shared.capabilities.voice.tts.options``（语音能力层自持）。
"""

from __future__ import annotations

from interview_service.schemas import WorkflowTypeOption
from shared.capabilities.knowledge.company.knowledge import get_all_companies
from interview_service.services.interview.workflows import WORKFLOWS, phase_label_map
from shared.capabilities.voice.tts.options import AVATARS, TTS_VOICES

ROLES = [
    "后端工程师", "前端工程师", "全栈工程师", "AI 工程师",
    "算法工程师", "游戏客户端工程师", "游戏服务端工程师",
    "移动端工程师", "DevOps 工程师", "产品经理", "技术经理",
]

LEVELS = ["实习生", "初级工程师", "中级工程师", "高级工程师", "专家", "架构师"]

EXPERIENCE_YEARS = ["0-1 年", "1-3 年", "3-5 年", "5-10 年", "10 年以上"]

PERSONALITIES = [
    {"id": "gentle", "name": "温和型", "description": "亲切友善，适当引导"},
    {"id": "professional", "name": "专业型", "description": "严谨精准，注重深度"},
    {"id": "pressure", "name": "压迫型", "description": "高压追问，模拟压力面"},
    {"id": "hr", "name": "HR 型", "description": "关注软技能与文化匹配"},
    {"id": "expert", "name": "技术专家型", "description": "极致深度，追求原理"},
]

INTERVIEW_STYLES = [
    {"id": "guided", "name": "引导型", "description": "适当提示，帮助展开"},
    {"id": "deep_dive", "name": "深挖型", "description": "层层追问至本质"},
    {"id": "continuous", "name": "连续追问型", "description": "单点深入不切换"},
    {"id": "challenging", "name": "挑战型", "description": "质疑方案，要求论证"},
]

WORKFLOW_TYPES = [
    WorkflowTypeOption(id=wf.id, name=wf.name, phases=[p.name for p in wf.phases])
    for wf in WORKFLOWS.values()
]

# AVATARS 在 shared.capabilities.voice.tts.options 定义,此处直接引用,勿重复定义

SCENES = [
    {"id": "meeting_room", "name": "企业会议室"},
    {"id": "glass_office", "name": "玻璃隔断办公室"},
    {"id": "online_interview", "name": "线上面试间"},
    {"id": "boardroom", "name": "董事会会议室"},
    {"id": "startup_loft", "name": "创业公司开放工位"},
    {"id": "library_corner", "name": "安静洽谈角"},
]


def build_options_payload() -> dict:
    """供 options API 组装响应。"""
    from shared.config import get_settings

    return {
        "roles": ROLES,
        "levels": LEVELS,
        "experience_years": EXPERIENCE_YEARS,
        "companies": get_all_companies(),
        "personalities": PERSONALITIES,
        "interview_styles": INTERVIEW_STYLES,
        "workflow_types": WORKFLOW_TYPES,
        "phase_labels": phase_label_map(),
        "avatars": AVATARS,
        "scenes": SCENES,
        "tts_voices": TTS_VOICES,
        # 前端据此设置静默追问计时器，与后端配置保持一致
        "silence_nudge_seconds": get_settings().silence_nudge_seconds,
    }
