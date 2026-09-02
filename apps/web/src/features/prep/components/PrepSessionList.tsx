"use client";

import { memo, useMemo } from "react";
import { MessageSquare, Plus } from "lucide-react";
import type { PrepSessionSummary } from "@/lib/api/contract";

/** 相对时间:刚刚 / N 分钟前 / … / 超过 7 天显示 M-D */
function relativeTime(iso: string): string {
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return "";
  const min = Math.floor((Date.now() - t) / 60000);
  if (min < 1) return "刚刚";
  if (min < 60) return `${min} 分钟前`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr} 小时前`;
  const day = Math.floor(hr / 24);
  if (day < 7) return `${day} 天前`;
  const d = new Date(t);
  return `${d.getMonth() + 1}-${d.getDate()}`;
}

interface PrepSessionListProps {
  sessions: PrepSessionSummary[];
  currentId: number | null;
  /** 流式回答中,禁止切换/新建 */
  disabled?: boolean;
  creating?: boolean;
  onSelect: (id: number) => void;
  onNew: () => void;
}

/**
 * 对话记录列表:按归属简历分组,组内按最近活跃排序;
 * 顶部「新对话」新建会话,点击条目切换并恢复该会话消息。
 */
export const PrepSessionList = memo(function PrepSessionList({
  sessions,
  currentId,
  disabled = false,
  creating = false,
  onSelect,
  onNew,
}: PrepSessionListProps) {
  const groups = useMemo(() => {
    const map = new Map<string, { label: string; items: PrepSessionSummary[] }>();
    for (const s of sessions) {
      const key = s.resume_id != null ? `r${s.resume_id}` : "none";
      if (!map.has(key)) map.set(key, { label: s.resume_filename || "通用辅导", items: [] });
      map.get(key)!.items.push(s);
    }
    return [...map.values()];
  }, [sessions]);

  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-[13px] font-semibold tracking-tight text-ink">
          <MessageSquare size={14} className="text-[var(--primary)]" />
          对话记录
        </h2>
        <button
          type="button"
          onClick={onNew}
          disabled={disabled || creating}
          className="flex items-center gap-1 rounded-md border border-surface-border px-2 py-1 text-[11px] font-medium text-ink-muted transition-colors hover:border-[var(--primary)] hover:bg-[var(--info-soft)] hover:text-ink disabled:cursor-not-allowed disabled:opacity-50"
        >
          <Plus size={12} />
          新对话
        </button>
      </div>

      {sessions.length === 0 ? (
        <p className="text-[11px] leading-relaxed text-ink-subtle">
          暂无历史对话;发起第一条消息后自动保存
        </p>
      ) : (
        <div className="max-h-[280px] space-y-3 overflow-y-auto pr-0.5">
          {groups.map((g) => (
            <div key={`${g.label}-${g.items[0]?.id}`}>
              <p className="mb-1 truncate text-[10px] font-medium uppercase tracking-wider text-ink-subtle">
                {g.label}
              </p>
              <div className="space-y-1">
                {g.items.map((s) => {
                  const active = s.id === currentId;
                  return (
                    <button
                      key={s.id}
                      type="button"
                      onClick={() => onSelect(s.id)}
                      disabled={disabled}
                      className={`w-full rounded-md border px-2.5 py-1.5 text-left transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
                        active
                          ? "border-[var(--primary)] bg-[var(--info-soft)]"
                          : "border-surface-border hover:border-[var(--primary)] hover:bg-surface-muted"
                      }`}
                    >
                      <span className="block truncate text-[12px] leading-snug text-ink">
                        {s.summary || "新会话"}
                      </span>
                      <span className="mt-0.5 block text-[10px] text-ink-subtle">
                        {relativeTime(s.updated_at) || "—"} · {s.message_count} 条
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
});
