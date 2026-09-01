"use client";

/** 左列供应商列表：选择 + 新增入口。 */

import { useState } from "react";
import { ChevronRight, Plus } from "lucide-react";
import { apiService } from "@/lib/api/apiService";
import { toast } from "@/components/Toast";
import type { ProviderWithModels } from "@/types";

export function ProviderList({
  providers,
  selectedId,
  onSelect,
  onChanged,
}: {
  providers: ProviderWithModels[];
  selectedId: number | null;
  onSelect: (id: number) => void;
  onChanged: () => Promise<void>;
}) {
  const [newProviderName, setNewProviderName] = useState("");

  const create = async () => {
    try {
      await apiService.createProvider({ name: newProviderName.trim() });
      setNewProviderName("");
      await onChanged();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "创建失败");
    }
  };

  return (
    <div className="surface-card !p-3">
      <p className="mb-2 px-1 text-[11px] font-semibold uppercase tracking-wider text-ink-subtle">
        供应商
      </p>
      <div className="space-y-1">
        {providers.length === 0 && (
          <p className="px-1 text-[12px] text-ink-subtle">暂无供应商,先添加一个</p>
        )}
        {providers.map((p) => (
          <button
            key={p.id}
            type="button"
            onClick={() => onSelect(p.id)}
            className={`flex w-full items-center gap-2 rounded-md border px-2.5 py-2 text-left text-[13px] transition-colors ${
              p.id === selectedId
                ? "border-[var(--primary)] bg-[var(--info-soft)] text-ink"
                : "border-transparent text-ink-muted hover:bg-surface-muted"
            }`}
          >
            <span
              className={`h-1.5 w-1.5 shrink-0 rounded-full ${p.enabled ? "bg-[var(--success)]" : "bg-ink-subtle"}`}
            />
            <span className="min-w-0 flex-1 truncate">{p.name}</span>
            <span className="shrink-0 text-[10px] text-ink-subtle">{p.models.length}</span>
            <ChevronRight size={13} className="shrink-0 text-ink-subtle" />
          </button>
        ))}
      </div>

      <div className="mt-3 border-t border-surface-border pt-3">
        <label className="mb-1 block text-[11px] text-ink-muted">新增供应商</label>
        <div className="flex gap-1.5">
          <input
            className="field-input !h-8 flex-1 text-[12px]"
            placeholder="名称,如 DeepSeek"
            value={newProviderName}
            onChange={(e) => setNewProviderName(e.target.value)}
          />
          <button
            type="button"
            className="btn-primary !h-8 !w-8 shrink-0 !p-0"
            aria-label="添加供应商"
            disabled={!newProviderName.trim()}
            onClick={create}
          >
            <Plus size={14} />
          </button>
        </div>
      </div>
    </div>
  );
}
