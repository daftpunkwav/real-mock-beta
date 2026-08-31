import type { ScoreBreakdown } from "@/types";

/** 归一化后的六维分数;缺省为 null(显示 —),0 视为有效分。 */
export interface NormalizedScores {
  technical: number | null;
  communication: number | null;
  project_depth: number | null;
  problem_solving: number | null;
  presence: number | null;
  politeness: number | null;
  overall: number | null;
}

/** 保证雷达/卡片拿到完整数值字段;缺省为 null(显示 —),0 视为有效分。 */
export function normalizeScores(raw: ScoreBreakdown | undefined | null): NormalizedScores {
  const pick = (v: unknown): number | null =>
    typeof v === "number" && Number.isFinite(v) ? Math.round(v) : null;
  return {
    technical: pick(raw?.technical),
    communication: pick(raw?.communication),
    project_depth: pick(raw?.project_depth),
    problem_solving: pick(raw?.problem_solving),
    presence: pick(raw?.presence),
    politeness: pick(raw?.politeness),
    overall: pick(raw?.overall),
  };
}

export function formatScore(score: number | null | undefined): string {
  if (typeof score !== "number" || !Number.isFinite(score)) return "—";
  return String(Math.round(score));
}

export function scoreColor(score: number | null | undefined): string {
  if (score == null || Number.isNaN(score)) return "var(--muted-foreground)";
  if (score >= 85) return "var(--success)";
  if (score >= 70) return "var(--primary)";
  if (score >= 60) return "var(--warning)";
  return "var(--danger)";
}
