"use client";

/**
 * 模型与处理器设置(能力声明制)。
 *
 * 三层数据:
 * - 供应商:api_base / protocol / API Key(凭证归属级);
 * - 模型条目:模型名 + 中立能力位(对话/视觉/语音输入/语音输出/思考强度)
 *   + 上下文窗口 + 最大输出——一个条目可同时被多个任务复用;
 * - 任务绑定:chat(思考)/ stt(语音输入)/ tts(语音输出)各自的默认条目
 *   与语音降级策略,即各场景的「默认处理器」。
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Check,
  ChevronRight,
  Cpu,
  Pencil,
  Plus,
  RefreshCw,
  Save,
  Trash2,
  X,
} from "lucide-react";
import { apiService } from "@/lib/api/apiService";
import { toast } from "@/components/Toast";
import type {
  LLMProtocol,
  ModelProfile,
  ProviderWithModels,
  TaskBindings,
} from "@/types";
import { LoadError } from "@/components/LoadError";

const PROTOCOL_OPTIONS: { value: LLMProtocol; label: string }[] = [
  { value: "openai_chat", label: "OpenAI Chat Completions" },
  { value: "anthropic_messages", label: "Anthropic Messages (/v1/messages)" },
  { value: "openai_responses", label: "OpenAI Responses" },
];

const CAP_OPTIONS: { key: keyof ModelProfile["capabilities"]; label: string }[] = [
  { key: "chat", label: "对话/思考" },
  { key: "vision", label: "视觉输入" },
  { key: "audio_input", label: "语音输入" },
  { key: "audio_output", label: "语音输出" },
  { key: "reasoning", label: "思考强度" },
];

const TASK_META: {
  task: "chat" | "stt" | "tts";
  label: string;
  hint: string;
  capKey: keyof ModelProfile["capabilities"];
}[] = [
  { task: "chat", label: "思考(chat)", hint: "面试教练 / 模拟面试对话 / 简历评价的默认模型", capKey: "chat" },
  { task: "stt", label: "语音输入(stt)", hint: "面试语音识别;失败时按降级策略回退", capKey: "audio_input" },
  { task: "tts", label: "语音输出(tts)", hint: "面试官播报;失败时按降级策略回退", capKey: "audio_output" },
];

/** 把条目列表按任务能力分桶,供绑定下拉用 */
function modelsForTask(models: ModelProfile[], capKey: keyof ModelProfile["capabilities"]) {
  return models.filter((m) => m.capabilities?.[capKey]);
}

function formatWindow(n: number) {
  if (!n) return "—";
  return n >= 1000 ? `${Math.round(n / 1000)}K` : String(n);
}

interface ModelDraft {
  model: string;
  display_name: string;
  context_window: string;
  max_output: string;
  capabilities: ModelProfile["capabilities"];
  extras_text: string;
}

const EMPTY_DRAFT: ModelDraft = {
  model: "",
  display_name: "",
  context_window: "128000",
  max_output: "4096",
  capabilities: { chat: true, vision: false, audio_input: false, audio_output: false, reasoning: false },
  extras_text: "",
};

export default function SettingsPage() {
  const [providers, setProviders] = useState<ProviderWithModels[]>([]);
  const [bindings, setBindings] = useState<TaskBindings | null>(null);
  const [selectedProviderId, setSelectedProviderId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [saving, setSaving] = useState(false);
  const [testingId, setTestingId] = useState<number | null>(null);

  const [newProviderName, setNewProviderName] = useState("");
  const [editingModelId, setEditingModelId] = useState<number | null>(null);
  const [draft, setDraft] = useState<ModelDraft>(EMPTY_DRAFT);
  const [addingModel, setAddingModel] = useState(false);

  const selectedProvider = useMemo(
    () => providers.find((p) => p.id === selectedProviderId) ?? null,
    [providers, selectedProviderId],
  );
  const allModels = useMemo(() => providers.flatMap((p) => p.models), [providers]);

  const reload = useCallback(async () => {
    setLoading(true);
    setLoadError("");
    try {
      const [provRes, bindRes] = await Promise.all([
        apiService.listProviders(),
        apiService.getBindings().catch(() => null),
      ]);
      const list = Array.isArray(provRes?.providers) ? provRes.providers : [];
      setProviders(list);
      if (bindRes) setBindings(bindRes);
      setSelectedProviderId((cur) =>
        cur && list.some((p) => p.id === cur) ? cur : (list[0]?.id ?? null),
      );
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  const openModelEdit = (m: ModelProfile) => {
    setEditingModelId(m.id);
    setAddingModel(false);
    setDraft({
      model: m.model,
      display_name: m.display_name || "",
      context_window: String(m.context_window || ""),
      max_output: String(m.max_output || ""),
      capabilities: { ...m.capabilities },
      extras_text: m.extras && Object.keys(m.extras).length ? JSON.stringify(m.extras, null, 2) : "",
    });
  };

  const draftFromForm = () => {
    let extras: Record<string, unknown> = {};
    if (draft.extras_text.trim()) {
      try {
        extras = JSON.parse(draft.extras_text);
      } catch {
        toast.error("高级参数不是合法 JSON");
        return null;
      }
    }
    return {
      model: draft.model.trim(),
      display_name: draft.display_name.trim(),
      context_window: Number(draft.context_window) || 0,
      max_output: Number(draft.max_output) || 4096,
      capabilities: draft.capabilities,
      extras,
    };
  };

  const saveModel = async (providerId: number) => {
    const body = draftFromForm();
    if (!body) return;
    if (!body.model) {
      toast.error("模型名不能为空");
      return;
    }
    setSaving(true);
    try {
      if (editingModelId) {
        await apiService.updateModel(editingModelId, body);
        toast.success("模型已更新");
      } else {
        await apiService.createModel(providerId, body);
        toast.success("模型已添加");
      }
      setEditingModelId(null);
      setAddingModel(false);
      setDraft(EMPTY_DRAFT);
      await reload();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "保存失败");
    } finally {
      setSaving(false);
    }
  };

  const deleteModel = async (id: number) => {
    try {
      await apiService.deleteModel(id);
      toast.success("已删除");
      await reload();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "删除失败");
    }
  };

  const testModel = async (id: number) => {
    setTestingId(id);
    try {
      const res = await apiService.testModel(id);
      if (res.success) toast.success(res.message || "测试通过");
      else toast.warning(res.message || "测试未通过");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "测试失败");
    } finally {
      setTestingId(null);
    }
  };

  const saveBinding = async (task: "chat" | "stt" | "tts", profileId: number | null) => {
    if (!profileId) return;
    try {
      const res = await apiService.updateBinding(task, { profile_id: profileId });
      setBindings(res);
      toast.success("默认处理器已更新");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "保存失败");
    }
  };

  const bindingSelect = (task: "chat" | "stt" | "tts", capKey: keyof ModelProfile["capabilities"]) => {
    const binding = bindings?.[task];
    const options = modelsForTask(allModels, capKey);
    const currentId = binding?.profile?.id ?? null;
    return (
      <select
        className="field-select !h-8 !py-0 text-[12px]"
        value={currentId ?? ""}
        onChange={(e) => {
          const id = e.target.value ? Number(e.target.value) : null;
          if (id) saveBinding(task, id);
        }}
        disabled={!options.length}
        aria-label={`${task} 默认模型`}
      >
        <option value="">{options.length ? "未设置" : "无可选模型"}</option>
        {options.map((m) => (
          <option key={m.id} value={m.id}>
            {m.label}（{m.provider_name}）
          </option>
        ))}
      </select>
    );
  };

  if (loading) {
    return (
      <div className="page-shell-tight anim-rise">
        <div className="surface-card flex items-center justify-center p-10 text-sm text-ink-muted">
          <RefreshCw size={16} className="mr-2 animate-spin" /> 加载中…
        </div>
      </div>
    );
  }
  if (loadError) {
    return (
      <div className="page-shell-tight anim-rise">
        <LoadError message={loadError} onRetry={reload} />
      </div>
    );
  }

  return (
    <div className="page-shell anim-rise">
      <div className="page-header !mb-4">
        <div>
          <p className="page-eyebrow">BYOK</p>
          <h1 className="page-title">模型与处理器</h1>
          <p className="page-desc">
            管理供应商与模型条目(按能力声明),为思考 / 语音输入 / 语音输出指定默认处理器。
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[280px_1fr]">
        {/* 左列:供应商列表 */}
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
                onClick={() => setSelectedProviderId(p.id)}
                className={`flex w-full items-center gap-2 rounded-md border px-2.5 py-2 text-left text-[13px] transition-colors ${
                  p.id === selectedProviderId
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
                onClick={async () => {
                  try {
                    await apiService.createProvider({ name: newProviderName.trim() });
                    setNewProviderName("");
                    await reload();
                  } catch (e) {
                    toast.error(e instanceof Error ? e.message : "创建失败");
                  }
                }}
              >
                <Plus size={14} />
              </button>
            </div>
          </div>
        </div>

        {/* 右列:供应商编辑 + 模型条目 */}
        <div className="min-w-0 space-y-4">
          {selectedProvider ? (
            <ProviderCard provider={selectedProvider} onChanged={reload} />
          ) : (
            <div className="surface-card p-6 text-center text-[13px] text-ink-muted">
              从左侧选择或新增一个供应商
            </div>
          )}

          {selectedProvider && (
            <div className="surface-card !p-4">
              <div className="mb-3 flex items-center justify-between">
                <h2 className="flex items-center gap-2 text-[13px] font-semibold text-ink">
                  <Cpu size={14} className="text-[var(--primary)]" />
                  模型条目（{selectedProvider.models.length}）
                </h2>
                <button
                  type="button"
                  className="flex items-center gap-1 rounded-md border border-surface-border px-2 py-1 text-[11px] text-ink-muted transition-colors hover:border-[var(--primary)] hover:text-ink"
                  onClick={() => {
                    setAddingModel(true);
                    setEditingModelId(null);
                    setDraft(EMPTY_DRAFT);
                  }}
                >
                  <Plus size={12} /> 添加模型
                </button>
              </div>

              <div className="space-y-2">
                {selectedProvider.models.length === 0 && !addingModel && (
                  <p className="text-[12px] text-ink-subtle">
                    还没有模型条目;条目按「能力」声明,可同时服务多个任务
                  </p>
                )}
                {selectedProvider.models.map((m) =>
                  editingModelId === m.id ? (
                    <ModelForm
                      key={m.id}
                      draft={draft}
                      setDraft={setDraft}
                      onCancel={() => {
                        setEditingModelId(null);
                        setDraft(EMPTY_DRAFT);
                      }}
                      onSave={() => saveModel(selectedProvider.id)}
                      saving={saving}
                    />
                  ) : (
                    <ModelRow
                      key={m.id}
                      model={m}
                      testing={testingId === m.id}
                      onEdit={() => openModelEdit(m)}
                      onDelete={() => deleteModel(m.id)}
                      onTest={() => testModel(m.id)}
                    />
                  ),
                )}
                {addingModel && (
                  <ModelForm
                    draft={draft}
                    setDraft={setDraft}
                    onCancel={() => setAddingModel(false)}
                    onSave={() => saveModel(selectedProvider.id)}
                    saving={saving}
                  />
                )}
              </div>
            </div>
          )}

          {/* 任务绑定 */}
          <div className="surface-card !p-4">
            <h2 className="mb-1 text-[13px] font-semibold text-ink">默认处理器</h2>
            <p className="mb-3 text-[11px] text-ink-subtle">
              各场景未手动选择模型时使用的默认条目;语音任务的降级策略在其失败时生效。
            </p>
            <div className="space-y-3">
              {TASK_META.map(({ task, label, hint, capKey }) => (
                <div key={task} className="flex flex-wrap items-center gap-2">
                  <span className="w-32 shrink-0 text-[12px] font-medium text-ink">{label}</span>
                  {bindingSelect(task, capKey)}
                  <span className="min-w-0 flex-1 basis-48 truncate text-[11px] text-ink-subtle" title={hint}>
                    {hint}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/** 供应商编辑卡:名称 / Base URL / 协议 / Key / 启用 */
function ProviderCard({
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
      await apiService.updateProvider(provider.id, {
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
      await apiService.deleteProvider(provider.id);
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

/** 模型条目行:label + 能力徽章 + 操作 */
function ModelRow({
  model,
  testing,
  onEdit,
  onDelete,
  onTest,
}: {
  model: ModelProfile;
  testing: boolean;
  onEdit: () => void;
  onDelete: () => void;
  onTest: () => void;
}) {
  const caps = CAP_OPTIONS.filter(({ key }) => model.capabilities?.[key]).map(({ label }) => label);
  return (
    <div className="flex items-center gap-2 rounded-md border border-surface-border px-3 py-2">
      <span className="min-w-0 flex-1 truncate text-[13px] text-ink">
        {model.label}
        <span className="ml-2 text-[11px] text-ink-subtle">{model.provider_name}</span>
      </span>
      <span className="shrink-0 rounded bg-[var(--info-soft)] px-1.5 py-0.5 text-[10px] text-[var(--info-ink)]">
        {formatWindow(model.context_window)}
      </span>
      {caps.map((c) => (
        <span key={c} className="hidden shrink-0 rounded bg-surface-muted px-1.5 py-0.5 text-[10px] text-ink-muted sm:inline">
          {c}
        </span>
      ))}
      <button
        type="button"
        className="shrink-0 rounded p-1 text-ink-subtle transition-colors hover:bg-surface-muted hover:text-ink"
        onClick={onTest}
        aria-label="测试"
      >
        {testing ? <RefreshCw size={13} className="animate-spin" /> : <Check size={13} />}
      </button>
      <button
        type="button"
        className="shrink-0 rounded p-1 text-ink-subtle transition-colors hover:bg-surface-muted hover:text-ink"
        onClick={onEdit}
        aria-label="编辑"
      >
        <Pencil size={13} />
      </button>
      <button
        type="button"
        className="shrink-0 rounded p-1 text-ink-subtle transition-colors hover:bg-surface-muted hover:text-[var(--danger)]"
        onClick={onDelete}
        aria-label="删除"
      >
        <Trash2 size={13} />
      </button>
    </div>
  );
}

/** 模型条目表单(新增/编辑) */
function ModelForm({
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
