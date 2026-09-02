"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { interviewHttp as api } from "@/lib/api/clients";
import type { GrowthRecord } from "@/types";
import { computeGrowthStats } from "./growthStats";
import type { SystemInsights } from "./types";

/** 成长页加载域：历史 + insights（失败降级 null）、选中记录、LoadError 重试。 */
export function useGrowthPage() {
  const [records, setRecords] = useState<GrowthRecord[]>([]);
  const [insights, setInsights] = useState<SystemInsights | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const seqRef = useRef(0);

  const load = useCallback(async () => {
    const seq = ++seqRef.current;
    setLoading(true);
    setLoadError(null);
    try {
      const [list, sys] = await Promise.all([
        api.getGrowthHistory(),
        api.getSystemInsights().catch(() => null),
      ]);
      if (seq !== seqRef.current) return;
      setRecords(list);
      setInsights(sys);
      setSelectedId(list[0]?.id ?? null);
    } catch (e) {
      if (seq !== seqRef.current) return;
      setLoadError(e instanceof Error ? e.message : "加载失败");
    } finally {
      if (seq !== seqRef.current) return;
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const selected = useMemo(
    () => records.find((r) => r.id === selectedId) ?? null,
    [records, selectedId],
  );

  const stats = useMemo(() => computeGrowthStats(records), [records]);

  return {
    records,
    insights,
    loading,
    loadError,
    selectedId,
    setSelectedId,
    selected,
    stats,
    load,
  };
}
