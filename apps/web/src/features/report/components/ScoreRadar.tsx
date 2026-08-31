"use client";

import type { NormalizedScores } from "../scoreFormat";

/** 面试六维能力雷达(本页专用,与简历域 RadarChart 无关)。 */
export function ScoreRadar({ scores }: { scores: NormalizedScores }) {
  const dims = [
    { key: "technical" as const, label: "技术" },
    { key: "communication" as const, label: "表达" },
    { key: "project_depth" as const, label: "项目" },
    { key: "problem_solving" as const, label: "解题" },
    { key: "presence" as const, label: "临场" },
    { key: "politeness" as const, label: "礼貌" },
  ];
  const cx = 120;
  const cy = 120;
  const r = 80;
  const values = dims.map((d) => {
    const v = scores[d.key];
    return typeof v === "number" ? Math.min(1, Math.max(0, v / 100)) : 0;
  });
  const points = dims
    .map((_, i) => {
      const angle = (Math.PI * 2 * i) / dims.length - Math.PI / 2;
      const v = values[i] ?? 0;
      return `${cx + Math.cos(angle) * r * v},${cy + Math.sin(angle) * r * v}`;
    })
    .join(" ");
  const rings = [0.25, 0.5, 0.75, 1];
  const hasAny = values.some((v) => v > 0);

  return (
    <div className="surface-card mb-6 p-4">
      <h3 className="mb-1 text-center text-[14px] font-semibold tracking-tight text-ink">
        能力雷达图
      </h3>
      <p className="mb-4 text-center text-[11px] text-ink-subtle">各轴满分 100;0 分会落在中心附近</p>
      <div className="flex justify-center">
        <svg width="240" height="240" viewBox="0 0 240 240" aria-label="能力雷达图">
          {rings.map((ring) => (
            <polygon
              key={ring}
              points={dims
                .map((_, i) => {
                  const angle = (Math.PI * 2 * i) / dims.length - Math.PI / 2;
                  return `${cx + Math.cos(angle) * r * ring},${cy + Math.sin(angle) * r * ring}`;
                })
                .join(" ")}
              fill="none"
              stroke="var(--border)"
              strokeWidth="1"
            />
          ))}
          {dims.map((d, i) => {
            const angle = (Math.PI * 2 * i) / dims.length - Math.PI / 2;
            const x = cx + Math.cos(angle) * (r + 18);
            const y = cy + Math.sin(angle) * (r + 18);
            const score = scores[d.key];
            return (
              <text
                key={d.key}
                x={x}
                y={y}
                textAnchor="middle"
                dominantBaseline="middle"
                className="fill-ink-subtle"
                style={{ fontSize: 10 }}
              >
                {d.label}
                {typeof score === "number" ? ` ${score}` : ""}
              </text>
            );
          })}
          {hasAny && (
            <polygon
              points={points}
              fill="color-mix(in srgb, var(--primary) 28%, transparent)"
              stroke="var(--primary)"
              strokeWidth="2"
            />
          )}
          {!hasAny && (
            <text
              x={cx}
              y={cy}
              textAnchor="middle"
              dominantBaseline="middle"
              className="fill-ink-subtle"
              style={{ fontSize: 11 }}
            >
              暂无有效维度分
            </text>
          )}
        </svg>
      </div>
    </div>
  );
}
