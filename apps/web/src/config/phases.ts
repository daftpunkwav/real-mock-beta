/**
 * 面试阶段展示映射（离线回退）。
 *
 * 权威数据源：后端 ``app/services/interview/workflows.py``（PhaseDef）。
 * options API 下发 ``phase_labels``；本文件仅作首屏/离线回退，
 * 并由 ``backend/tests/test_phase_ssot.py`` 与后端技术面顺序锁同步。
 */
export const PHASE_LABELS: Record<string, string> = {
  identity_check: "身份确认",
  self_intro: "自我介绍",
  basic_knowledge: "基础知识",
  project_deep_dive: "项目深挖",
  technical_deep: "技术深挖",
  system_design: "系统设计",
  scenario: "情景问题",
  reverse_qa: "反问环节",
  summary: "总结评价",
  // HR / 管理（options 也会下发；此处补全避免未知 id 闪烁）
  career_plan: "职业规划",
  teamwork: "团队合作",
  pressure: "压力问题",
  salary: "薪资沟通",
  leadership: "领导经验",
  decision_making: "决策能力",
  conflict: "冲突处理",
  business: "业务理解",
} as const;

/** 技术面默认顺序（与 ``technical_phase_order()`` 一致） */
export const PHASE_ORDER: readonly string[] = [
  "identity_check",
  "self_intro",
  "basic_knowledge",
  "project_deep_dive",
  "technical_deep",
  "system_design",
  "scenario",
  "reverse_qa",
  "summary",
] as const;
