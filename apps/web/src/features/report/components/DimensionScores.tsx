"use client";

import { formatScore, scoreColor, type NormalizedScores } from "../scoreFormat";

const DIMS = [
  { label: "技术能力", key: "technical" as const },
  { label: "表达能力", key: "communication" as const },
  { label: "项目深度", key: "project_depth" as const },
  { label: "问题解决", key: "problem_solving" as const },
  { label: "临场状态", key: "presence" as const },
  { label: "话轮礼貌", key: "politeness" as const },
];

/** 六维分数卡片网格。 */
export function DimensionScores({ scores }: { scores: NormalizedScores }) {
  return (
    <div className="mb-6 grid grid-cols-2 gap-2.5 sm:grid-cols-3 lg:grid-cols-6">
      {DIMS.map((d) => {
        const value = scores[d.key];
        const display = formatScore(value);
        const numeric = typeof value === "number";
        return (
          <div
            key={d.label}
            className="kpi-card items-center text-center !p-3"
          >
            <div
              className="font-mono text-[24px] font-semibold leading-none num-tabular"
              style={{ color: numeric ? scoreColor(value) : undefined }}
            >
              {display}
            </div>
            <div className="kpi-label mt-2 text-center">{d.label}</div>
            {numeric && value != null && (
              <div className="mt-2 h-1 w-full overflow-hidden rounded-full bg-surface-muted">
                <div
                  className="h-full rounded-full transition-all"
                  style={{
                    width: `${Math.min(100, Math.max(0, value))}%`,
                    backgroundColor: scoreColor(value),
                  }}
                />
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
