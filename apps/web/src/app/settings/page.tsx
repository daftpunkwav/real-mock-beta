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
 *
 * 本文件只做 load/save 状态与组装;列表/表单/绑定 UI 在
 * ``features/settings/`` 各组件。
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { Cpu, Plus, RefreshCw } from "lucide-react";
import { apiService } from "@/lib/api/apiService";
import { toast } from "@/components/Toast";
import type { ModelProfile, ProviderWithModels, TaskBindings } from "@/types";
import { LoadError } from "@/components/LoadError";
import { BindingsCard } from "@/features/settings/BindingsCard";
import { ModelForm } from "@/features/settings/ModelForm";
import { ModelRow } from "@/features/settings/ModelRow";
import { ProviderCard } from "@/features/settings/ProviderCard";
import { ProviderList } from "@/features/settings/ProviderList";
import { EMPTY_DRAFT, type ModelDraft } from "@/features/settings/constants";

export default function SettingsPage() {
  const [providers, setProviders] = useState<ProviderWithModels[]>([]);
  const [bindings, setBindings] = useState<TaskBindings | null>(null);
  const [selectedProviderId, setSelectedProviderId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [saving, setSaving] = useState(false);
  const [testingId, setTestingId] = useState<number | null>(null);

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

  const saveBinding = async (task: "chat" | "stt" | "tts", profileId: number) => {
    try {
      const res = await apiService.updateBinding(task, { profile_id: profileId });
      setBindings(res);
      toast.success("默认处理器已更新");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "保存失败");
    }
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
        <ProviderList
          providers={providers}
          selectedId={selectedProviderId}
          onSelect={setSelectedProviderId}
          onChanged={reload}
        />

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
          <BindingsCard bindings={bindings} allModels={allModels} onUpdate={saveBinding} />
        </div>
      </div>
    </div>
  );
}
