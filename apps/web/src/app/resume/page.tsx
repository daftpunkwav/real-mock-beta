"use client";

import { LoadError } from "@/components/LoadError";
import {
  useResumeList,
  ResumePageHead,
  ResumeUploadArea,
  ResumeList,
  ResumeDetailPanel,
  ResumePreviewCard,
  ResumeOverviewCard,
  ResumeTipsCard,
} from "@/features/resume";

export default function ResumePage() {
  const {
    resumes,
    loading,
    loadError,
    uploading,
    analyzingId,
    error,
    previewId,
    inputRef,
    previewResume,
    analysis,
    setPreviewId,
    load,
    handleUpload,
    handleAnalyze,
    handleActivate,
    handleDelete,
  } = useResumeList();

  return (
    <div className="page-shell anim-rise">
      <ResumePageHead />

      {loading ? (
        <div className="flex items-center justify-center gap-2 py-16 text-[13px] text-ink-muted">
          <span className="block h-4 w-4 anim-spin rounded-full border-2 border-current border-t-transparent" />
          加载中…
        </div>
      ) : loadError ? (
        <LoadError message={loadError} onRetry={load} />
      ) : (
        <div className="grid grid-cols-1 items-start gap-5 xl:grid-cols-[minmax(0,1fr)_300px]">
          {/* ===== 左侧:上传 + 列表 + 深度评价 ===== */}
          <div className="min-w-0 space-y-4">
            <ResumeUploadArea
              uploading={uploading}
              error={error}
              inputRef={inputRef}
              onUpload={handleUpload}
            />

            <ResumeList
              resumes={resumes}
              previewId={previewId}
              analyzingId={analyzingId}
              onSelect={setPreviewId}
              onActivate={handleActivate}
              onAnalyze={handleAnalyze}
              onDelete={handleDelete}
            />

            <ResumeDetailPanel
              resume={previewResume}
              analysis={analysis}
              analyzingId={analyzingId}
              error={error}
              onAnalyze={handleAnalyze}
            />
          </div>

          {/* ===== 右侧:紧凑 sticky 预览 ===== */}
          <aside className="space-y-3 xl:sticky xl:top-6">
            <ResumePreviewCard resume={previewResume} />
            <ResumeOverviewCard resumes={resumes} />
            <ResumeTipsCard />
          </aside>
        </div>
      )}
    </div>
  );
}
