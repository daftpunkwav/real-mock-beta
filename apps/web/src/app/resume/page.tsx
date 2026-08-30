"use client";

import { useEffect, useState, useRef, useMemo } from "react";
import { apiService as api } from "@/lib/api/apiService";
import { toast } from "@/components/Toast";
import type { Resume } from "@/types";
import { AnalysisPanel, AnalyzeStageProgress, asAnalysis } from "@/features/resume";
import {
  Upload,
  FileText,
  CheckCircle,
  Sparkles,
  Lightbulb,
  FolderOpen,
  Trash2,
  ChevronRight,
  Gauge,
} from "lucide-react";
import { LoadError } from "@/components/LoadError";

export default function ResumePage() {
  const [resumes, setResumes] = useState<Resume[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [uploading, setUploading] = useState(false);
  const [analyzingId, setAnalyzingId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [previewId, setPreviewId] = useState<number | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const load = () => {
    setLoading(true);
    setLoadError("");
    return api
      .listResumes()
      .then((list) => {
        setResumes(list);
        setPreviewId((prev) => {
          if (prev && list.some((r) => r.id === prev)) return prev;
          const active = list.find((r) => r.is_active);
          return active?.id ?? list[0]?.id ?? null;
        });
      })
      .catch((e) => setLoadError(e instanceof Error ? e.message : "加载失败"))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, []);

  const previewResume = useMemo(
    () => resumes.find((r) => r.id === previewId) ?? null,
    [resumes, previewId],
  );

  const analysis = useMemo(
    () => (previewResume ? asAnalysis(previewResume.analysis) : null),
    [previewResume],
  );

  const activeResume = resumes.find((r) => r.is_active);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setError("");
    try {
      await api.uploadResume(file);
      await load();
      toast.success("简历已上传并解析");
    } catch (err) {
      setError(err instanceof Error ? err.message : "上传失败");
    } finally {
      setUploading(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  };

  const handleAnalyze = async (id: number) => {
    setError("");
    setAnalyzingId(id);
    setPreviewId(id);
    toast.clear();
    toast.info("正在生成深度评价（含联网检索），约需 1–3 分钟，请勿关闭页面…", {
      persist: true,
    });
    try {
      const data = await api.analyzeResume(id);
      await load();
      toast.clear();
      toast.success(`评价完成 · 综合评分 ${data.score}`, { durationMs: 8000 });
    } catch (err) {
      // 可能已写入库但响应失败：刷新列表，避免界面与数据不一致
      try {
        await load();
      } catch {
        /* ignore */
      }
      toast.clear();
      const msg = err instanceof Error ? err.message : "分析失败";
      toast.error(msg, { durationMs: 10000 });
      setError(msg);
    } finally {
      setAnalyzingId(null);
    }
  };

  return (
    <div className="page-shell anim-rise">
      <div className="page-header">
        <div className="flex items-start gap-3">
          <span className="icon-badge icon-badge-success">
            <FileText size={18} strokeWidth={1.75} />
          </span>
          <div>
            <p className="page-eyebrow">Resume</p>
            <h1 className="page-title">简历管理</h1>
            <p className="page-desc">
              PDF · Word · Markdown · TXT。AI 解析为职业知识档案并给出深度评价。
            </p>
          </div>
        </div>
      </div>

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
            {/* 上传区 */}
            <button
              type="button"
              onClick={() => inputRef.current?.click()}
              disabled={uploading}
              className="group surface-card flex w-full cursor-pointer flex-col items-center justify-center border-dashed !border-2 p-6 text-center hover:border-[var(--primary)] hover:bg-[var(--info-soft)] sm:p-8 disabled:opacity-60"
            >
              {uploading ? (
                <span className="block h-7 w-7 anim-spin rounded-full border-2 border-[var(--primary)] border-t-transparent" />
              ) : (
                <span className="icon-badge icon-badge-brand transition-transform group-hover:scale-105">
                  <Upload size={16} strokeWidth={1.75} />
                </span>
              )}
              <p className="mt-3 text-[13px] font-medium text-ink">
                {uploading ? "正在解析简历…" : "点击或拖拽上传简历"}
              </p>
              <p className="mt-1 text-[11px] text-ink-subtle">PDF · DOCX · MD · TXT · 最大 10MB</p>
              <input
                ref={inputRef}
                type="file"
                accept=".pdf,.docx,.doc,.md,.txt"
                className="hidden"
                onChange={handleUpload}
              />
            </button>

            {error && <div className="alert alert-error">{error}</div>}

            {/* 简历列表 */}
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
                  {resumes.map((r) => {
                    const selected = r.id === previewId;
                    return (
                      <li key={r.id}>
                        <div
                          role="button"
                          tabIndex={0}
                          onClick={() => setPreviewId(r.id)}
                          onKeyDown={(e) => {
                            if (e.key === "Enter" || e.key === " ") setPreviewId(r.id);
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
                              onClick={async (e) => {
                                e.stopPropagation();
                                try {
                                  await api.activateResume(r.id);
                                  await load();
                                  toast.success("已设为投递简历");
                                } catch (err) {
                                  toast.error(err instanceof Error ? err.message : "设为投递失败");
                                }
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
                                void handleAnalyze(r.id);
                              }}
                              disabled={analyzingId === r.id}
                              className="btn-primary !h-8 !px-3 !text-xs"
                            >
                              {analyzingId === r.id ? (
                                <span className="block h-3 w-3 anim-spin rounded-full border-2 border-current border-t-transparent" />
                              ) : (
                                <Sparkles size={12} />
                              )}
                              {analyzingId === r.id ? "评价中…" : "AI 深度评价"}
                            </button>
                            <button
                              type="button"
                              onClick={async (e) => {
                                e.stopPropagation();
                                if (!confirm(`确定删除「${r.filename}」?`)) return;
                                try {
                                  await api.deleteResume(r.id);
                                  toast.success("已删除");
                                  await load();
                                } catch (err) {
                                  toast.error(err instanceof Error ? err.message : "删除失败");
                                }
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
                  })}
                </ul>
              )}
            </div>

            {/* Agent 深度评价 · 审阅笺 */}
            <section className="surface-card overflow-hidden">
              {analyzingId != null && analyzingId === previewId && (
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
                      onClick={() => void handleAnalyze(previewResume.id)}
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
          </div>

          {/* ===== 右侧:紧凑 sticky 预览 ===== */}
          <aside className="space-y-3 xl:sticky xl:top-6">
            <div className="surface-card p-4 sm:p-5">
              <h2 className="mb-3.5 flex items-center gap-2 text-[13px] font-semibold tracking-tight text-ink">
                <FolderOpen size={14} className="text-[var(--primary)]" />
                简历预览
              </h2>
              {previewResume ? (
                <>
                  <div className="mb-3 flex items-start gap-3">
                    <span className="icon-badge icon-badge-brand shrink-0">
                      <FileText size={16} strokeWidth={1.75} />
                    </span>
                    <div className="min-w-0">
                      <p className="truncate text-[13px] font-semibold text-ink">{previewResume.filename}</p>
                      <p className="mt-0.5 text-[11px] text-ink-subtle">
                        {previewResume.parsed_profile.name || "未解析姓名"} ·{" "}
                        {previewResume.file_type.toUpperCase()}
                      </p>
                    </div>
                  </div>

                  {previewResume.score != null && (
                    <div className="mb-3">
                      <div className="mb-1 flex justify-between text-[11px]">
                        <span className="text-ink-subtle">AI 评分</span>
                        <span className="font-mono font-semibold text-[var(--primary)] num-tabular">
                          {previewResume.score}
                        </span>
                      </div>
                      <div className="progress">
                        <div
                          className="progress-bar !bg-[var(--success)]"
                          style={{ width: `${Math.min(previewResume.score, 100)}%` }}
                        />
                      </div>
                    </div>
                  )}

                  {previewResume.parsed_profile.summary && (
                    <div className="mb-3">
                      <p className="mb-1 text-[10px] font-semibold uppercase tracking-[0.1em] text-ink-subtle">
                        摘要
                      </p>
                      <p className="line-clamp-4 text-[12px] leading-relaxed text-ink-muted">
                        {previewResume.parsed_profile.summary}
                      </p>
                    </div>
                  )}

                  {previewResume.parsed_profile.skills.length > 0 && (
                    <div className="mb-3">
                      <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-[0.1em] text-ink-subtle">
                        技能
                      </p>
                      <div className="flex flex-wrap gap-1">
                        {previewResume.parsed_profile.skills.slice(0, 12).map((s) => (
                          <span key={s} className="chip chip-blue !text-[10px]">
                            {s}
                          </span>
                        ))}
                        {previewResume.parsed_profile.skills.length > 12 && (
                          <span className="chip chip-gray !text-[10px]">
                            +{previewResume.parsed_profile.skills.length - 12}
                          </span>
                        )}
                      </div>
                    </div>
                  )}

                  {previewResume.parsed_profile.projects.length > 0 && (
                    <div>
                      <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-[0.1em] text-ink-subtle">
                        项目
                      </p>
                      <ul className="space-y-1.5">
                        {previewResume.parsed_profile.projects.slice(0, 3).map((p, i) => (
                          <li key={i} className="flex items-start gap-1.5 text-[12px] text-ink-muted">
                            <CheckCircle size={11} className="mt-0.5 shrink-0 text-[var(--success)]" />
                            <span className="line-clamp-2">{p.name || p.description || "未命名项目"}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </>
              ) : (
                <p className="py-4 text-center text-[13px] text-ink-subtle">上传后显示预览</p>
              )}
            </div>

            <div className="surface-card p-4 sm:p-5">
              <h2 className="mb-3 flex items-center gap-2 text-[13px] font-semibold tracking-tight text-ink">
                <Gauge size={14} className="text-[var(--warning)]" />
                概览
              </h2>
              <div className="grid grid-cols-2 gap-2">
                <div className="kpi-card !p-3">
                  <p className="kpi-value !text-xl">{resumes.length}</p>
                  <p className="kpi-label mt-1">已上传</p>
                </div>
                <div className="kpi-card !p-3">
                  <p className="kpi-value !text-xl">{resumes.filter((r) => r.score != null).length}</p>
                  <p className="kpi-label mt-1">已评分</p>
                </div>
              </div>
              {activeResume && (
                <p className="mt-3 border-t border-surface-border pt-3 text-[11px] leading-relaxed text-ink-subtle">
                  当前投递:
                  <span className="ml-1 font-medium text-ink">{activeResume.filename}</span>
                </p>
              )}
            </div>

            <div className="surface-card p-4 sm:p-5">
              <h2 className="mb-2.5 flex items-center gap-2 text-[13px] font-semibold tracking-tight text-ink">
                <Lightbulb size={14} className="text-[var(--primary)]" />
                提示
              </h2>
              <ul className="space-y-2 text-[11px] leading-relaxed text-ink-subtle">
                <li>· 「投递简历」会关联到模拟面试与面试准备</li>
                <li>· 深度评价会联网检索岗位要求,并点评排版、字体与内容</li>
                <li>· 旧评价需重新点击「AI 深度评价」才会刷新新结构</li>
              </ul>
            </div>
          </aside>
        </div>
      )}
    </div>
  );
}
