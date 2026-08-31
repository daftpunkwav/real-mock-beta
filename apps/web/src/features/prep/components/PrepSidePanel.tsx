"use client";

/** prep 右侧栏:关联简历卡 + 对话记录 + 快捷提问(桌面 lg 以上显示)。 */

import { FileText, Zap } from "lucide-react";
import { PREP_QUICK_PROMPTS } from "@/config/prepPrompts";
import type { PrepSessionSummary, ResumePickerItem } from "@/types";
import { PrepSessionList } from "./PrepSessionList";

const QUICK_PROMPTS = PREP_QUICK_PROMPTS;

interface PrepSidePanelProps {
  selectedResume: ResumePickerItem | null;
  sessions: PrepSessionSummary[];
  prepSessionId: number | null;
  loading: boolean;
  starting: boolean;
  onSelectSession: (id: number) => void;
  onNewSession: () => void;
  onQuickPrompt: (prompt: string) => void;
}

export function PrepSidePanel({
  selectedResume,
  sessions,
  prepSessionId,
  loading,
  starting,
  onSelectSession,
  onNewSession,
  onQuickPrompt,
}: PrepSidePanelProps) {
  return (
    <div className="hidden min-h-0 flex-col gap-3 overflow-y-auto pr-0.5 lg:flex">
      <div className="surface-card p-4">
        <h2 className="mb-3 flex items-center gap-2 text-[13px] font-semibold tracking-tight text-ink">
          <FileText size={14} className="text-[var(--primary)]" />
          关联简历
        </h2>
        {selectedResume ? (
          <>
            <p className="truncate text-[13px] font-medium text-ink">
              {selectedResume.filename}
            </p>
            <p className="mt-1 text-[11px] text-ink-subtle">
              {selectedResume.is_active ? "当前投递" : "未设为投递"}
              {selectedResume.score != null && ` · 评分 ${selectedResume.score}`}
            </p>
          </>
        ) : (
          <p className="text-[12px] text-ink-subtle">未关联简历,将进行通用辅导</p>
        )}
      </div>

      <div className="surface-card p-4">
        <PrepSessionList
          sessions={sessions}
          currentId={prepSessionId}
          disabled={loading}
          creating={starting}
          onSelect={onSelectSession}
          onNew={onNewSession}
        />
      </div>

      <div className="surface-card p-4">
        <h2 className="mb-3 flex items-center gap-2 text-[13px] font-semibold tracking-tight text-ink">
          <Zap size={14} className="text-[var(--warning)]" />
          快捷提问
        </h2>
        <div className="space-y-1.5">
          {QUICK_PROMPTS.map((prompt) => (
            <button
              key={prompt}
              type="button"
              onClick={() => onQuickPrompt(prompt)}
              disabled={loading}
              className="w-full rounded-md border border-surface-border px-3 py-2 text-left text-[12px] leading-relaxed text-ink-muted transition-colors hover:border-[var(--primary)] hover:bg-[var(--info-soft)] hover:text-ink disabled:opacity-50"
            >
              {prompt}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
