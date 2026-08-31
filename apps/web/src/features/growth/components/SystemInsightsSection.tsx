"use client";

import { BarChart3 } from "lucide-react";
import type { SystemInsights } from "../types";
import { Section } from "./Section";

/** 系统自我成长区块：跨面试聚合摘要 + 公司分布 + 近期线索。 */
export function SystemInsightsSection({ insights }: { insights: SystemInsights }) {
  return (
    <Section title="系统自我成长" icon={BarChart3}>
      <p className="mb-3 text-[11px] leading-relaxed text-ink-subtle">
        跨面试聚合:公司分布、工具调用、薄弱点沉淀。
        {insights.interview_tools_enabled ? " 工具循环已开启。" : " 工具循环已关闭。"}
        {insights.github_token_configured ? " GitHub Token 已配置。" : " 未配置 GITHUB_TOKEN。"}
      </p>
      <div className="mb-3 grid grid-cols-2 gap-2">
        {Object.entries(insights.company_session_counts || {})
          .slice(0, 6)
          .map(([k, v]) => (
            <div
              key={k}
              className="kpi-card flex !flex-row items-center justify-between gap-2 !p-2.5"
            >
              <span className="truncate text-[11px] text-ink-muted">{k}</span>
              <span className="font-mono text-[12px] font-semibold text-ink num-tabular">
                {v} 场
              </span>
            </div>
          ))}
      </div>
      {insights.recent_probes && insights.recent_probes.length > 0 && (
        <div>
          <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-ink-subtle">
            近期线索
          </p>
          <ul className="max-h-32 space-y-2 overflow-y-auto text-[11px] leading-relaxed text-ink-muted">
            {insights.recent_probes.slice(0, 5).map((p, i) => (
              <li key={i} className="break-words">
                · [{p.company || "—"}] {p.point}
              </li>
            ))}
          </ul>
        </div>
      )}
    </Section>
  );
}
