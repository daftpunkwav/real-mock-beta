"use client";

import { ChevronRight, FileText, Sparkles, Trash2 } from "lucide-react";
import type { Resume } from "@/types";

interface ResumeListItemProps {
  resume: Resume;
  selected: boolean;
  analyzing: boolean;
  onSelect: (id: number) => void;
  onActivate: (id: number) => void;
  onAnalyze: (id: number) => void;
  onDelete: (id: number) => void;
}

/** 简历列表单项 + 选中操作条（设为投递 / AI 深度评价 / 删除）。 */
export function ResumeListItem({
  resume: r,
  selected,
  analyzing,
  onSelect,
  onActivate,
  onAnalyze,
  onDelete,
}: ResumeListItemProps) {
  return (
    <li>
      <div
        role="button"
        tabIndex={0}
        onClick={() => onSelect(r.id)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") onSelect(r.id);
        }}
        className={`flex cursor-pointer items-center gap-3 px-4 py-3.5 ${
          selected ? "bg-[var(--info-soft)]" : "hover:bg-surface-alt"
        }`}
      >
        <span
          className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-md ${
            selected
              ? "bg-[var(--primary)] text-white"
              : "bg-surface-alt text-ink-subtle"
          }`}
        >
          <FileText size={15} strokeWidth={1.75} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="truncate text-[13px] font-medium text-ink">
              {r.filename}
            </span>
            {r.is_active && <span className="chip chip-blue">投递</span>}
            {r.score != null && (
              <span className="chip chip-green">评分 {r.score}</span>
            )}
          </div>
          <p className="mt-0.5 text-[11px] text-ink-subtle">
            {r.file_type.toUpperCase()}
            {r.parsed_profile.name ? ` · ${r.parsed_profile.name}` : ""}
          </p>
        </div>
        <ChevronRight
          size={15}
          className={`shrink-0 ${selected ? "text-[var(--primary)]" : "text-ink-subtle"}`}
        />
      </div>

      {/* 选中项操作条 */}
      {selected && (
        <div className="flex flex-wrap items-center gap-2 border-t border-surface-border bg-[var(--info-soft)] px-4 pb-3.5 pt-2">
          <button
            type="button"
            disabled={r.is_active}
            onClick={(e) => {
              e.stopPropagation();
              onActivate(r.id);
            }}
            className={`inline-flex h-8 items-center gap-1.5 rounded-md px-3 text-[12px] font-medium transition-colors ${
              r.is_active
                ? "bg-[var(--chip-blue-bg)] text-[var(--chip-blue-fg)]"
                : "border border-surface-border bg-surface-card text-ink-muted hover:border-[var(--primary)] hover:text-[var(--primary)]"
            }`}
          >
            {r.is_active ? "当前投递" : "设为投递"}
          </button>
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onAnalyze(r.id);
            }}
            disabled={analyzing}
            className="btn-primary !h-8 !px-3 !text-xs"
          >
            {analyzing ? (
              <span className="block h-3 w-3 anim-spin rounded-full border-2 border-current border-t-transparent" />
            ) : (
              <Sparkles size={12} />
            )}
            {analyzing ? "评价中…" : "AI 深度评价"}
          </button>
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              if (!confirm(`确定删除「${r.filename}」?`)) return;
              onDelete(r.id);
            }}
            className="ml-auto inline-flex h-8 items-center gap-1.5 rounded-md px-2.5 text-[12px] font-medium text-[var(--danger-ink)] hover:bg-[var(--danger-soft)]"
          >
            <Trash2 size={12} />
            删除
          </button>
        </div>
      )}
    </li>
  );
}
