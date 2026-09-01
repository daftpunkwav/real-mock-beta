"use client";

/** 模型条目表单（新增/编辑）：模型名 / 显示名 / 窗口 / 输出 / 能力勾选 / 高级参数。 */

import { Save, X } from "lucide-react";
import { CAP_OPTIONS, type ModelDraft } from "./constants";

export function ModelForm({
  draft,
  setDraft,
  onSave,
  onCancel,
  saving,
}: {
  draft: ModelDraft;
  setDraft: (d: ModelDraft) => void;
  onSave: () => void;
  onCancel: () => void;
  saving: boolean;
}) {
  return (
    <div className="rounded-md border border-[var(--primary)]/40 bg-[var(--info-soft)]/40 p-3">
      <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
        <div>
          <label className="mb-1 block text-[11px] text-ink-muted">模型名(发往 API)</label>
          <input
            className="field-input !h-9"
            value={draft.model}
            placeholder="如 deepseek-chat"
            onChange={(e) => setDraft({ ...draft, model: e.target.value })}
          />
        </div>
        <div>
          <label className="mb-1 block text-[11px] text-ink-muted">显示名(可选)</label>
          <input
            className="field-input !h-9"
            value={draft.display_name}
            onChange={(e) => setDraft({ ...draft, display_name: e.target.value })}
          />
        </div>
        <div>
          <label className="mb-1 block text-[11px] text-ink-muted">上下文窗口(tokens)</label>
          <input
            className="field-input !h-9"
            type="number"
            min={0}
            value={draft.context_window}
            onChange={(e) => setDraft({ ...draft, context_window: e.target.value })}
          />
        </div>
        <div>
          <label className="mb-1 block text-[11px] text-ink-muted">最大输出(tokens)</label>
          <input
            className="field-input !h-9"
            type="number"
            min={1}
            value={draft.max_output}
            onChange={(e) => setDraft({ ...draft, max_output: e.target.value })}
          />
        </div>
      </div>

      <div className="mt-2.5">
        <p className="mb-1 text-[11px] text-ink-muted">能力(可多选;同一模型可服务多个任务)</p>
        <div className="flex flex-wrap gap-x-4 gap-y-1.5">
          {CAP_OPTIONS.map(({ key, label }) => (
            <label key={key} className="flex items-center gap-1.5 text-[12px] text-ink-muted">
              <input
                type="checkbox"
                checked={draft.capabilities[key]}
                onChange={(e) =>
                  setDraft({
                    ...draft,
                    capabilities: { ...draft.capabilities, [key]: e.target.checked },
                  })
                }
              />
              {label}
            </label>
          ))}
        </div>
      </div>

      <details className="mt-2.5">
        <summary className="cursor-pointer text-[11px] text-ink-subtle hover:text-ink-muted">
          高级参数(语音凭证等 JSON)
        </summary>
        <textarea
          className="field-input mt-1.5 min-h-16 w-full font-mono text-[11px]"
          value={draft.extras_text}
          onChange={(e) => setDraft({ ...draft, extras_text: e.target.value })}
          spellCheck={false}
        />
      </details>

      <div className="mt-3 flex justify-end gap-2">
        <button
          type="button"
          className="flex items-center gap-1 rounded-md border border-surface-border px-2.5 py-1.5 text-[12px] text-ink-muted hover:text-ink"
          onClick={onCancel}
        >
          <X size={13} /> 取消
        </button>
        <button type="button" className="btn-primary !h-8" onClick={onSave} disabled={saving}>
          <Save size={13} /> {saving ? "保存中…" : "保存模型"}
        </button>
      </div>
    </div>
  );
}
