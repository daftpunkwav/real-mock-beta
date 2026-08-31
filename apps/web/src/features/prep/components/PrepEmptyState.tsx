"use client";

/** prep 空态:未开会话时选简历 + 开始辅导。 */

import { Sparkles } from "lucide-react";
import type { ResumePickerItem } from "@/types";

interface PrepEmptyStateProps {
  resumeLoadError: string;
  resumes: ResumePickerItem[];
  resumeId: number | null;
  onResumeChange: (id: number | null) => void;
  prepError: string;
  starting: boolean;
  onStart: () => void;
}

export function PrepEmptyState({
  resumeLoadError,
  resumes,
  resumeId,
  onResumeChange,
  prepError,
  starting,
  onStart,
}: PrepEmptyStateProps) {
  return (
    <div className="surface-card flex flex-1 flex-col justify-center overflow-hidden p-8">
      <div className="mx-auto w-full max-w-md space-y-5">
        <div className="text-center">
          <span className="icon-badge icon-badge-brand mx-auto mb-4 !h-14 !w-14">
            <Sparkles size={22} strokeWidth={1.75} />
          </span>
          <h2 className="text-[18px] font-semibold tracking-tight text-ink">
            开始你的面试辅导
          </h2>
          <p className="mt-1.5 text-[13px] text-ink-muted">
            关联简历后,AI 教练将基于你的背景进行针对性辅导。
          </p>
        </div>

        {resumeLoadError ? (
          <div className="alert alert-error !block text-center">{resumeLoadError}</div>
        ) : resumes.length > 0 ? (
          <div>
            <label className="field-label">关联简历</label>
            <select
              className="field-select"
              value={resumeId ?? ""}
              onChange={(e) => onResumeChange(Number(e.target.value))}
            >
              {resumes.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.filename}
                  {r.is_active ? " (投递)" : ""}
                </option>
              ))}
            </select>
          </div>
        ) : (
          <div className="alert alert-warning !block text-center">
            暂无简历,可先去「简历管理」上传,也可直接开始通用辅导
          </div>
        )}

        {prepError && (
          <div className="alert alert-error !block text-center">{prepError}</div>
        )}

        <button
          type="button"
          onClick={onStart}
          disabled={starting}
          className="btn-primary !h-10 w-full"
        >
          {starting ? (
            <span className="block h-3.5 w-3.5 anim-spin rounded-full border-2 border-current border-t-transparent" />
          ) : (
            <Sparkles size={14} />
          )}
          {starting ? "正在连接…" : "开始辅导"}
        </button>
      </div>
    </div>
  );
}
