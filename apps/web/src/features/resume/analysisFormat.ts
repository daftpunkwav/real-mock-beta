import type { DimensionScore, Resume, ResumeAnalysis } from "@/types";

/** 深度评价维度中文标签。 */
export const DIM_LABELS: Record<string, string> = {
  structure_clarity: "结构清晰度",
  visual_layout: "版式布局",
  typography: "字体可读性",
  impact_quantification: "成果量化",
  tech_depth: "技术深度",
  project_narrative: "项目叙事",
  role_fit: "岗位匹配",
  keyword_ats: "ATS 关键词",
  credibility: "可信度",
  seniority_signal: "职级信号",
  growth_signal: "成长潜力",
  collaboration_signal: "协作信号",
};

/** dimension_scores 的取值形态：纯数字或 { score, comment? } 对象。 */
export type DimensionValue = DimensionScore | number;

export type TabId = "overview" | "projects" | "skills" | "actions";

export type DimEntry = [string, DimensionValue];

/** 宽容解析旧评价：无对象 / 无 score → null。 */
export function asAnalysis(raw: Resume["analysis"]): ResumeAnalysis | null {
  if (!raw || typeof raw !== "object") return null;
  if (!("score" in raw)) return null;
  return raw as ResumeAnalysis;
}

export function dimScore(v: DimensionValue): number {
  if (typeof v === "number") return v;
  if (v && typeof v === "object" && "score" in v) return Number((v as { score: number }).score) || 0;
  return 0;
}

export function dimComment(v: DimensionValue): string {
  if (v && typeof v === "object" && "comment" in v) {
    return String((v as { comment?: string }).comment || "").trim();
  }
  return "";
}
