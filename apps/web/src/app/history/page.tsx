"use client";

import { BarChart3 } from "lucide-react";
import { LoadError } from "@/components/LoadError";
import { useHistoryPage } from "@/features/history/useHistoryPage";
import { HistoryListCard } from "@/features/history/components/HistoryListCard";
import { HistoryDetailAside } from "@/features/history/components/HistoryDetailAside";

export default function HistoryPage() {
  const { sessions, loading, loadError, selectedId, setSelectedId, selected, stats, load } =
    useHistoryPage();

  return (
    <div className="page-shell anim-rise">
      <div className="page-header">
        <div className="flex items-start gap-3">
          <span className="icon-badge icon-badge-brand">
            <BarChart3 size={18} strokeWidth={1.75} />
          </span>
          <div>
            <p className="page-eyebrow">History</p>
            <h1 className="page-title">面试记录</h1>
            <p className="page-desc">回顾每一次模拟面试与报告</p>
          </div>
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center gap-2 py-16 text-[13px] text-ink-muted">
          <span className="block h-4 w-4 anim-spin rounded-full border-2 border-current border-t-transparent" />
          加载记录…
        </div>
      ) : loadError ? (
        <LoadError message={loadError} onRetry={load} />
      ) : (
        <div className="grid grid-cols-1 items-start gap-5 xl:grid-cols-[minmax(0,1fr)_300px]">
          <HistoryListCard
            sessions={sessions}
            selectedId={selectedId}
            onSelect={setSelectedId}
            total={stats.total}
          />
          <HistoryDetailAside selected={selected} stats={stats} />
        </div>
      )}
    </div>
  );
}
