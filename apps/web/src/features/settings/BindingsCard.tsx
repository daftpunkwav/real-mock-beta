"use client";

/** 任务绑定区：chat / stt / tts 各自的默认处理器下拉。 */

import type { ModelProfile, TaskBindings } from "@/types";
import { TASK_META, modelsForTask } from "./constants";

export function BindingsCard({
  bindings,
  allModels,
  onUpdate,
}: {
  bindings: TaskBindings | null;
  allModels: ModelProfile[];
  onUpdate: (task: "chat" | "stt" | "tts", profileId: number) => void;
}) {
  return (
    <div className="surface-card !p-4">
      <h2 className="mb-1 text-[13px] font-semibold text-ink">默认处理器</h2>
      <p className="mb-3 text-[11px] text-ink-subtle">
        各场景未手动选择模型时使用的默认条目;语音任务的降级策略在其失败时生效。
      </p>
      <div className="space-y-3">
        {TASK_META.map(({ task, label, hint, capKey }) => (
          <div key={task} className="flex flex-wrap items-center gap-2">
            <span className="w-32 shrink-0 text-[12px] font-medium text-ink">{label}</span>
            {bindingSelect(bindings, allModels, task, capKey, onUpdate)}
            <span className="min-w-0 flex-1 basis-48 truncate text-[11px] text-ink-subtle" title={hint}>
              {hint}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function bindingSelect(
  bindings: TaskBindings | null,
  allModels: ModelProfile[],
  task: "chat" | "stt" | "tts",
  capKey: keyof ModelProfile["capabilities"],
  onUpdate: (task: "chat" | "stt" | "tts", profileId: number) => void,
) {
  const binding = bindings?.[task];
  const options = modelsForTask(allModels, capKey);
  const currentId = binding?.profile?.id ?? null;
  return (
    <select
      className="field-select !h-8 !py-0 text-[12px]"
      value={currentId ?? ""}
      onChange={(e) => {
        const id = e.target.value ? Number(e.target.value) : null;
        if (id) onUpdate(task, id);
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
}
