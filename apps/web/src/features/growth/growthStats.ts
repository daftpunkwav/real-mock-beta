import type { GrowthRecord } from "@/types";

export interface GrowthStats {
  /** 薄弱项与出现次数，按频次降序，最多 5 条。 */
  topWeaknesses: [string, number][];
  totalInterviews: number;
  totalPlans: number;
  totalWeakSkills: number;
  growthPct: number;
  growthLevel: string;
}

/** 从成长记录聚合页面统计：薄弱项频次、完成度公式、档位文案。 */
export function computeGrowthStats(records: GrowthRecord[]): GrowthStats {
  const count: Record<string, number> = {};
  for (const r of records) {
    for (const w of r.weak_skills) count[w] = (count[w] || 0) + 1;
  }
  const topWeaknesses = Object.entries(count)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5);
  const totalInterviews = records.length;
  const totalPlans = records.reduce((sum, r) => sum + r.training_plan.length, 0);
  const totalWeakSkills = new Set(Object.keys(count)).size;
  const growthPct = Math.min(100, totalInterviews * 25 + Math.min(totalPlans, 4) * 5);
  const growthLevel =
    totalInterviews === 0
      ? "待启动"
      : totalInterviews < 3
        ? "起步阶段"
        : totalInterviews < 6
          ? "持续成长"
          : "进阶提升";
  return { topWeaknesses, totalInterviews, totalPlans, totalWeakSkills, growthPct, growthLevel };
}
