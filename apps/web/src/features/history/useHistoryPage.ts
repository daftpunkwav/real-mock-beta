"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { interviewService as api } from "@/lib/api/interviewService";
import type { InterviewSession } from "@/types";

/** 记录页加载域：sessions + 默认选中 + stats + LoadError 重试。 */
export function useHistoryPage() {
  const [sessions, setSessions] = useState<InterviewSession[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const list = await api.listSessions();
      setSessions(list);
      const firstCompleted = list.find((s) => s.status === "completed");
      const fallback = list[0];
      setSelectedId(firstCompleted?.id ?? fallback?.id ?? null);
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const selected = useMemo(
    () => sessions.find((s) => s.id === selectedId) ?? null,
    [sessions, selectedId],
  );

  const stats = useMemo(
    () => ({
      total: sessions.length,
      completed: sessions.filter((s) => s.status === "completed").length,
      active: sessions.filter((s) => s.status === "active").length,
      avgScore: (() => {
        const scored = sessions.filter((s) => s.overall_score != null);
        if (scored.length === 0) return null;
        return Math.round(
          scored.reduce((sum, s) => sum + (s.overall_score ?? 0), 0) / scored.length,
        );
      })(),
    }),
    [sessions],
  );

  return {
    sessions,
    loading,
    loadError,
    selectedId,
    setSelectedId,
    selected,
    stats,
    load,
  };
}
