"use client";

import { Sparkles } from "lucide-react";
import type { Resume, ResumeAnalysis } from "@/types";
import { AnalysisPanel } from "./AnalysisPanel";
import { AnalyzeStageProgress } from "./AnalyzeStageProgress";

interface ResumeDetailPanelProps {
  resume: Resume | null;
  analysis: ResumeAnalysis | null;
  analyzingId: number | null;
  error: string;
  onAnalyze: (id: number) => void;
}

/** 深度评价区：当前选中简历 + AnalysisPanel 组装，评价 JSX 仍在 AnalysisPanel。 */
export function ResumeDetailPanel({
  resume: previewResume,
  analysis,
  analyzingId,
  error,
  onAnalyze,
}: ResumeDetailPanelProps) {
  return (
    <section className="surface-card overflow-hidden">
      {analyzingId != null && analyzingId === previewResume?.id && (
        <div className="flex items-center gap-2.5 border-b border-surface-border bg-[var(--info-soft)] px-5 py-3 text-[13px] text-[var(--info-ink)] sm:px-7">
          <span className="block h-3.5 w-3.5 anim-spin rounded-full border-2 border-current border-t-transparent" />
          <span className="tracking-[0.02em]">
            Agent 正在深度评价与联网检索,完成后将自动刷新…
          </span>
        </div>
      )}
      <div className="px-5 pb-6 pt-6 sm:px-8 sm:pb-8 sm:pt-7">
        {!previewResume ? (
          <div className="empty-state !py-10">
            <p className="text-[13px] tracking-[0.04em]">选择一份简历后查看评价</p>
          </div>
        ) : analyzingId === previewResume.id ? (
          <AnalyzeStageProgress />
        ) : !analysis ? (
          <div className="py-12 text-center">
            <div className="empty-state-icon mx-auto mb-4">
              <Sparkles size={20} />
            </div>
            <p className="mb-1.5 text-[13px] tracking-[0.04em] text-ink-muted">
              尚未生成深度评价
            </p>
            <p className="mx-auto mb-5 max-w-sm text-[11px] leading-relaxed tracking-[0.03em] text-ink-subtle">
              生成后将给出排版、字体与内容的完整审阅
            </p>
            {error && (
              <p className="mx-auto mb-4 max-w-md text-[11px] leading-relaxed text-[var(--danger-ink)]">
                {error}
              </p>
            )}
            <button
              type="button"
              onClick={() => onAnalyze(previewResume.id)}
              disabled={analyzingId === previewResume.id}
              className="btn-primary !h-9"
            >
              <Sparkles size={13} />
              开始评价
            </button>
          </div>
        ) : (
          <>
            {error && (
              <div className="alert alert-warning mb-4 text-xs">{error}</div>
            )}
            <AnalysisPanel analysis={analysis} />
          </>
        )}
      </div>
    </section>
  );
}
