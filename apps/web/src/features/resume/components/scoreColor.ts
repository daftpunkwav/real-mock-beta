/** 评分→颜色档位:≥80 success / ≥60 primary / ≥40 warning / else danger。 */
export function scoreColor(score: number): string {
  if (score >= 80) return "var(--success)";
  if (score >= 60) return "var(--primary)";
  if (score >= 40) return "var(--warning)";
  return "var(--danger)";
}
