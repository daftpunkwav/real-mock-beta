"use client";

import { useEffect, useMemo, useRef, useState, type ChangeEvent } from "react";
import { profileHttp as api } from "@/lib/api/clients";
import { toast } from "@/components/Toast";
import type { Resume } from "@/types";
import { asAnalysis } from "./analysisFormat";

/** 简历管理页列表状态与副作用：加载、上传、深度评价、设为投递、删除。 */
export function useResumeList() {
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

  const handleUpload = async (e: ChangeEvent<HTMLInputElement>) => {
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

  const handleActivate = async (id: number) => {
    try {
      await api.activateResume(id);
      await load();
      toast.success("已设为投递简历");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "设为投递失败");
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await api.deleteResume(id);
      toast.success("已删除");
      await load();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "删除失败");
    }
  };

  return {
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
  };
}
