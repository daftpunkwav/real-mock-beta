"use client";

/** 供应商编辑卡：名称 / Base URL / 协议 / Key / 启用 / 删除。 */

import { useEffect, useState } from "react";
import { Save, Trash2 } from "lucide-react";
import { profileHttp } from "@/lib/api/clients";
import { toast } from "@/components/Toast";
import type { LLMProtocol, ProviderWithModels } from "@/types";
import { PROTOCOL_OPTIONS } from "./constants";

export function ProviderCard({
  provider,
  onChanged,
}: {
  provider: ProviderWithModels;
  onChanged: () => Promise<void>;
}) {
  const [name, setName] = useState(provider.name);
  const [apiBase, setApiBase] = useState(provider.api_base);
  const [protocol, setProtocol] = useState<LLMProtocol>(provider.protocol);
  const [apiKey, setApiKey] = useState("");
  const [enabled, setEnabled] = useState(provider.enabled);
  const [showKey, setShowKey] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setName(provider.name);
    setApiBase(provider.api_base);
    setProtocol(provider.protocol);
    setEnabled(provider.enabled);
    setApiKey("");
  }, [provider.id, provider.name, provider.api_base, provider.protocol, provider.enabled]);

  const save = async () => {
    setSaving(true);
    try {
      await profileHttp.updateProvider(provider.id, {
        name,
        api_base: apiBase,
        protocol,
        enabled,
        api_key: apiKey || undefined,
      });
      toast.success("供应商已保存");
      await onChanged();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "保存失败");
    } finally {
      setSaving(false);
    }
  };

  const remove = async () => {
    try {
      await profileHttp.deleteProvider(provider.id);
      toast.success("供应商已删除");
      await onChanged();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "删除失败");
    }
  };

  return (
    <div className="surface-card !p-4">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div>
          <label className="mb-1 block text-[11px] text-ink-muted">名称</label>
          <input className="field-input !h-9" value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <div>
          <label className="mb-1 block text-[11px] text-ink-muted">Base URL</label>
          <input
            className="field-input !h-9"
            value={apiBase}
            placeholder="https://…"
            onChange={(e) => setApiBase(e.target.value)}
          />
        </div>
        <div>
          <label className="mb-1 block text-[11px] text-ink-muted">API 格式</label>
          <select
            className="field-select !h-9"
            value={protocol}
            onChange={(e) => setProtocol(e.target.value as LLMProtocol)}
          >
            {PROTOCOL_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="mb-1 block text-[11px] text-ink-muted">
            API Key{provider.has_api_key ? "（已设置,留空保持）" : ""}
          </label>
          <div className="flex gap-1.5">
            <input
              className="field-input !h-9 flex-1"
              type={showKey ? "text" : "password"}
              value={apiKey}
              placeholder={provider.has_api_key ? "••••••••" : "sk-…"}
              onChange={(e) => setApiKey(e.target.value)}
            />
            <button
              type="button"
              className="shrink-0 text-[11px] text-ink-subtle hover:text-ink"
              onClick={() => setShowKey((v) => !v)}
            >
              {showKey ? "隐藏" : "显示"}
            </button>
          </div>
        </div>
      </div>
      <div className="mt-3 flex items-center gap-2">
        <label className="flex items-center gap-1.5 text-[12px] text-ink-muted">
          <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
          启用
        </label>
        <div className="flex-1" />
        <button
          type="button"
          className="flex items-center gap-1 rounded-md border border-surface-border px-2.5 py-1.5 text-[12px] text-ink-muted transition-colors hover:border-[var(--danger)] hover:text-[var(--danger)]"
          onClick={remove}
        >
          <Trash2 size={13} /> 删除
        </button>
        <button type="button" className="btn-primary !h-8" onClick={save} disabled={saving}>
          <Save size={13} /> {saving ? "保存中…" : "保存供应商"}
        </button>
      </div>
    </div>
  );
}
