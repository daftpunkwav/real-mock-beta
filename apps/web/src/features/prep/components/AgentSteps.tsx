"use client";

import { useState } from "react";
import { ChevronRight, Wrench } from "lucide-react";
import type { PrepToolStep } from "@/types";

const TOOL_LABELS: Record<string, string> = {
  web_search: "搜索面经",
  company_info: "查询公司",
  quiz: "出练习题",
  ask_user: "向你提问",
  take_note: "记录要点",
  github_list_repos: "查看 GitHub 仓库",
  github_get_readme: "读取仓库 README",
  github_get_repo: "查看仓库详情",
  github_list_commits: "查看提交记录",
  github_get_user: "查看 GitHub 用户",
};

/** ReAct 执行过程时间线(思考→行动→观察),默认收起。 */
export function AgentSteps({ steps }: { steps: PrepToolStep[] }) {
  const [expanded, setExpanded] = useState(false);
  if (steps.length === 0) return null;

  return (
    <div className="overflow-hidden rounded-md border border-surface-border bg-surface-alt">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center gap-2 px-2.5 py-1.5 text-left text-[11px] text-ink-muted transition-colors hover:bg-surface-muted"
        aria-expanded={expanded}
      >
        <ChevronRight
          size={13}
          className={`shrink-0 text-ink-subtle transition-transform ${expanded ? "rotate-90" : ""}`}
        />
        <Wrench size={12} className="shrink-0 text-[var(--primary)]" />
        <span className="font-medium">执行过程 · {steps.length} 步</span>
        {!expanded && steps.length > 0 && (
          <span className="min-w-0 flex-1 truncate text-ink-subtle">
            {steps[steps.length - 1]!.name}
          </span>
        )}
      </button>
      {expanded && (
        <ol className="space-y-1.5 border-t border-surface-border px-3 py-2.5">
          {steps.map((s, i) => (
            <li key={`${s.name}-${i}`} className="flex items-start gap-2 text-[11px] leading-relaxed">
              <span className="mt-px shrink-0 rounded bg-[var(--info-soft)] px-1.5 py-0.5 font-medium text-[var(--info-ink)]">
                {TOOL_LABELS[s.name] ?? s.name}
              </span>
              {s.query ? (
                <span className="min-w-0 flex-1 truncate text-ink-subtle" title={s.query}>
                  {s.query}
                </span>
              ) : null}
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
