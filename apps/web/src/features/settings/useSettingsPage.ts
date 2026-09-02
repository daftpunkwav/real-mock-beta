"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "@/components/Toast";
import { profileHttp } from "@/lib/api/clients";
import type { ModelProfile, ProviderWithModels, TaskBindings } from "@/types";
import { EMPTY_DRAFT, type ModelDraft } from "./constants";

/**
 * 设置页数据域（能力声明制）。
 * 三层数据：供应商 / 模型条目 / 任务绑定；本 hook 负责加载、CRUD 与保存状态，UI 在
 * features/settings/ 各组件。
 */
export function useSettingsPage() {
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
        profileHttp.listProviders(),
        profileHttp.getBindings().catch(() => null),
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

  const startAddModel = () => {
    setAddingModel(true);
    setEditingModelId(null);
    setDraft(EMPTY_DRAFT);
  };

  const cancelEdit = () => {
    setEditingModelId(null);
    setDraft(EMPTY_DRAFT);
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
        await profileHttp.updateModel(editingModelId, body);
        toast.success("模型已更新");
      } else {
        await profileHttp.createModel(providerId, body);
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
      await profileHttp.deleteModel(id);
      toast.success("已删除");
      await reload();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "删除失败");
    }
  };

  const testModel = async (id: number) => {
    setTestingId(id);
    try {
      const res = await profileHttp.testModel(id);
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
      const res = await profileHttp.updateBinding(task, { profile_id: profileId });
      setBindings(res);
      toast.success("默认处理器已更新");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "保存失败");
    }
  };

  return {
    providers,
    bindings,
    selectedProvider,
    selectedProviderId,
    setSelectedProviderId,
    allModels,
    loading,
    loadError,
    saving,
    testingId,
    editingModelId,
    addingModel,
    setAddingModel,
    draft,
    setDraft,
    reload,
    openModelEdit,
    startAddModel,
    cancelEdit,
    saveModel,
    deleteModel,
    testModel,
    saveBinding,
  };
}
