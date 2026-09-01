"use client";

/**
 * 模型与处理器设置页（能力声明制）。
 * 本文件只做数据加载与 section 组装；数据域在 features/settings/useSettingsPage，
 * 列表/表单/绑定 UI 在 features/settings/ 各组件。
 */

import { RefreshCw } from "lucide-react";
import { LoadError } from "@/components/LoadError";
import { BindingsCard } from "@/features/settings/BindingsCard";
import { ModelListCard } from "@/features/settings/ModelListCard";
import { ProviderCard } from "@/features/settings/ProviderCard";
import { ProviderList } from "@/features/settings/ProviderList";
import { useSettingsPage } from "@/features/settings/useSettingsPage";

export default function SettingsPage() {
  const {
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
  } = useSettingsPage();

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
            <ModelListCard
              provider={selectedProvider}
              editingModelId={editingModelId}
              addingModel={addingModel}
              draft={draft}
              setDraft={setDraft}
              saving={saving}
              testingId={testingId}
              onSave={saveModel}
              onEdit={openModelEdit}
              onDelete={deleteModel}
              onTest={testModel}
              onStartAdd={startAddModel}
              onCancelEdit={cancelEdit}
              onCancelAdd={() => setAddingModel(false)}
            />
          )}

          {/* 任务绑定 */}
          <BindingsCard bindings={bindings} allModels={allModels} onUpdate={saveBinding} />
        </div>
      </div>
    </div>
  );
}
