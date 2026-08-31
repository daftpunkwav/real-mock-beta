"use client";

import { FileText } from "lucide-react";
import type { Resume } from "@/types";
import { ResumeListItem } from "./ResumeListItem";

interface ResumeListProps {
  resumes: Resume[];
  previewId: number | null;
  analyzingId: number | null;
  onSelect: (id: number) => void;
  onActivate: (id: number) => void;
  onAnalyze: (id: number) => void;
  onDelete: (id: number) => void;
}

/** 简历列表侧栏。 */
export function ResumeList({
  resumes,
  previewId,
  analyzingId,
  onSelect,
  onActivate,
  onAnalyze,
  onDelete,
}: ResumeListProps) {
  return (
    <div className="surface-card overflow-hidden">
      <div className="flex items-center justify-between border-b border-surface-border px-4 py-3">
        <h2 className="text-[13px] font-semibold tracking-tight text-ink">我的简历</h2>
        <span className="chip chip-gray">{resumes.length} 份</span>
      </div>

      {resumes.length === 0 ? (
        <div className="empty-state !py-12">
          <div className="empty-state-icon">
            <FileText size={22} />
          </div>
          <p className="text-[13px]">暂无简历,请先上传一份</p>
        </div>
      ) : (
        <ul className="divide-y divide-surface-border">
          {resumes.map((r) => (
            <ResumeListItem
              key={r.id}
              resume={r}
              selected={r.id === previewId}
              analyzing={analyzingId === r.id}
              onSelect={onSelect}
              onActivate={onActivate}
              onAnalyze={onAnalyze}
              onDelete={onDelete}
            />
          ))}
        </ul>
      )}
    </div>
  );
}
