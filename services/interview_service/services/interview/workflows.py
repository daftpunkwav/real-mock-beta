"""面试流程 Workflow 定义（阶段元数据唯一数据源）。

阶段 id / 中文名 / 描述 / 题量上下限只在本模块维护。
``interview_service.constants.InterviewPhaseId`` 仅作 id 枚举与类型约束；
前端展示文案应与本模块一致（由 options API 的 ``phase_labels`` 下发，
``frontend/src/config/phases.ts`` 作离线回退并由单测锁同步）。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from interview_service.constants import InterviewPhaseId, WorkflowType


@dataclass(frozen=True)
class PhaseDef:
    """单个面试阶段的运行时定义。"""

    id: str
    name: str
    description: str
    min_questions: int = 1
    max_questions: int = 3


@dataclass
class Workflow:
    id: str
    name: str
    phases: list[PhaseDef] = field(default_factory=list)


def _p(
    phase_id: InterviewPhaseId,
    name: str,
    description: str,
    min_q: int = 1,
    max_q: int = 3,
) -> PhaseDef:
    return PhaseDef(phase_id.value, name, description, min_q, max_q)


TECHNICAL_WORKFLOW = Workflow(
    id=WorkflowType.TECHNICAL.value,
    name="技术面",
    phases=[
        _p(InterviewPhaseId.IDENTITY_CHECK, "身份确认", "确认候选人身份，简短寒暄", 1, 1),
        _p(InterviewPhaseId.SELF_INTRO, "自我介绍", "请候选人做自我介绍", 1, 1),
        _p(InterviewPhaseId.BASIC_KNOWLEDGE, "基础知识", "考察岗位相关基础知识", 2, 4),
        _p(InterviewPhaseId.PROJECT_DEEP_DIVE, "项目深挖", "深入追问简历中的项目经历", 3, 6),
        _p(InterviewPhaseId.TECHNICAL_DEEP, "技术深挖", "针对技术栈进行深度考察", 2, 4),
        _p(InterviewPhaseId.SYSTEM_DESIGN, "系统设计", "设计类问题或架构讨论", 1, 2),
        _p(InterviewPhaseId.SCENARIO, "情景问题", "模拟真实工作场景的问题", 1, 2),
        _p(InterviewPhaseId.REVERSE_QA, "反问环节", "候选人向面试官提问", 1, 3),
        _p(InterviewPhaseId.SUMMARY, "总结评价", "面试官做简要总结", 1, 1),
    ],
)

HR_WORKFLOW = Workflow(
    id=WorkflowType.HR.value,
    name="HR 面",
    phases=[
        _p(InterviewPhaseId.IDENTITY_CHECK, "身份确认", "确认身份", 1, 1),
        _p(InterviewPhaseId.SELF_INTRO, "自我介绍", "自我介绍", 1, 1),
        _p(InterviewPhaseId.CAREER_PLAN, "职业规划", "了解职业发展方向", 2, 3),
        _p(InterviewPhaseId.TEAMWORK, "团队合作", "团队协作经历", 2, 3),
        _p(InterviewPhaseId.PRESSURE, "压力问题", "压力与冲突处理", 1, 2),
        _p(InterviewPhaseId.SALARY, "薪资沟通", "薪资期望（模拟）", 1, 1),
        _p(InterviewPhaseId.REVERSE_QA, "反问环节", "候选人提问", 1, 3),
        _p(InterviewPhaseId.SUMMARY, "总结评价", "总结", 1, 1),
    ],
)

MANAGEMENT_WORKFLOW = Workflow(
    id=WorkflowType.MANAGEMENT.value,
    name="管理岗面",
    phases=[
        _p(InterviewPhaseId.IDENTITY_CHECK, "身份确认", "确认身份", 1, 1),
        _p(InterviewPhaseId.SELF_INTRO, "自我介绍", "自我介绍", 1, 1),
        _p(InterviewPhaseId.LEADERSHIP, "领导经验", "团队管理经验", 2, 4),
        _p(InterviewPhaseId.DECISION_MAKING, "决策能力", "关键决策案例", 2, 3),
        _p(InterviewPhaseId.CONFLICT, "冲突处理", "团队冲突解决", 1, 2),
        _p(InterviewPhaseId.BUSINESS, "业务理解", "业务战略理解", 2, 3),
        _p(InterviewPhaseId.REVERSE_QA, "反问环节", "候选人提问", 1, 3),
        _p(InterviewPhaseId.SUMMARY, "总结评价", "总结", 1, 1),
    ],
)

WORKFLOWS: dict[str, Workflow] = {
    WorkflowType.TECHNICAL.value: TECHNICAL_WORKFLOW,
    WorkflowType.HR.value: HR_WORKFLOW,
    WorkflowType.MANAGEMENT.value: MANAGEMENT_WORKFLOW,
}


def phase_label_map() -> dict[str, str]:
    """全 workflow 阶段 id → 展示名（技术面优先，其它补全）。"""
    labels: dict[str, str] = {}
    # 先技术面（与前端离线回退一致），再其它
    for wf in (TECHNICAL_WORKFLOW, HR_WORKFLOW, MANAGEMENT_WORKFLOW):
        for p in wf.phases:
            labels.setdefault(p.id, p.name)
    return labels


def technical_phase_order() -> tuple[str, ...]:
    """技术面阶段 id 顺序（唯一权威来源）。"""
    return tuple(p.id for p in TECHNICAL_WORKFLOW.phases)


PERSONALITY_PROMPTS = {
    "gentle": "你是一位温和友善的面试官，语气亲切，会适当鼓励和引导候选人。",
    "professional": "你是一位专业严谨的面试官，问题精准，注重逻辑和深度。",
    "pressure": "你是一位高压型面试官，追问犀利，不给候选人喘息机会，模拟压力面试。",
    "hr": "你是一位 HR 面试官，关注软技能、文化匹配和职业规划。",
    "expert": "你是一位技术专家型面试官，问题极具深度，追求技术细节和原理理解。",
}

STYLE_PROMPTS = {
    "guided": "采用引导型风格，当候选人回答不完整时给予适当提示。",
    "deep_dive": "采用深挖型风格，对每个回答追问 3-5 层，直到触及技术本质。",
    "continuous": "采用连续追问型，不切换话题，在一个技术点上连续深入。",
    "challenging": "采用挑战型风格，质疑候选人的方案，要求论证和反驳。",
}

STRICTNESS_DESCRIPTIONS = {
    1: "非常友好，像聊天一样轻松",
    2: "较为宽松，偶尔追问",
    3: "正常企业面试强度",
    4: "偏严格，频繁追问细节",
    5: "严格，对模糊回答不接受",
    6: "高压，连续追问不给思考时间",
    7: "很高压，质疑每个论点",
    8: "极度高压，模拟大厂终面",
    9: "压力测试级别",
    10: "极限压力测试，挑战候选人心理极限",
}


def get_workflow(workflow_id: str) -> Workflow:
    return WORKFLOWS.get(workflow_id, TECHNICAL_WORKFLOW)


# 向后兼容别名（旧名 InterviewPhase 指 dataclass）
InterviewPhase = PhaseDef
