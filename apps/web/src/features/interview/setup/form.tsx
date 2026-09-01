"use client";

/** 面试配置页左列表单区：岗位/职级/类型/风格 + 公司 + 性格/严厉 + 人像/场景/简历 + 处理器卡。 */

import { Mic } from "lucide-react";
import type { ModelProfile, ReasoningEffort, ResumePickerItem } from "@/types";
import { EffortSelect, ModelSelect } from "@/components/ModelControls";
import { Select } from "./controls";

export function strictnessLabel(strictness: number): string {
  return strictness <= 3 ? "友好" : strictness <= 6 ? "正常" : strictness <= 8 ? "高压" : "极限";
}

export function ResumeSelect({
  resumes,
  value,
  onChange,
}: {
  resumes: ResumePickerItem[];
  value: number | null;
  onChange: (v: number | null) => void;
}) {
  return (
    <Select
      label="关联简历"
      value={String(value)}
      options={resumes.map((r) => String(r.id))}
      labels={resumes.map((r) => `${r.filename}${r.is_active ? " (投递)" : ""}`)}
      onChange={(v) => onChange(Number(v))}
    />
  );
}

export function ProcessorCard({
  chatModels,
  sttModels,
  ttsModels,
  chatModelId,
  sttModelId,
  ttsModelId,
  effort,
  setChatModelId,
  setSttModelId,
  setTtsModelId,
  setEffort,
  defaultBindings,
  disabled,
}: {
  chatModels: ModelProfile[];
  sttModels: ModelProfile[];
  ttsModels: ModelProfile[];
  chatModelId: number | null;
  sttModelId: number | null;
  ttsModelId: number | null;
  effort: ReasoningEffort;
  setChatModelId: (v: number | null) => void;
  setSttModelId: (v: number | null) => void;
  setTtsModelId: (v: number | null) => void;
  setEffort: (v: ReasoningEffort) => void;
  defaultBindings: import("@/types").TaskBindings | null;
  disabled: boolean;
}) {
  return (
    <div className="rounded-lg border border-surface-border p-3">
      <p className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-ink">
        <Mic size={13} className="text-[var(--primary)]" />
        处理器与思考强度
      </p>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        <div>
          <label className="mb-1 block text-[11px] text-ink-muted">思考模型</label>
          <ModelSelect
            models={chatModels}
            value={chatModelId}
            onChange={setChatModelId}
            disabled={disabled}
            ariaLabel="思考模型"
            className="!w-full"
            defaultProfile={defaultBindings?.chat?.profile ?? null}
          />
        </div>
        <div>
          <label className="mb-1 block text-[11px] text-ink-muted">思考强度</label>
          <EffortSelect
            model={chatModels.find((m) => m.id === chatModelId) ?? null}
            value={effort}
            onChange={setEffort}
            disabled={disabled}
            forceVisible
          />
        </div>
        <div>
          <label className="mb-1 block text-[11px] text-ink-muted">语音输入（识别）</label>
          <ModelSelect
            models={sttModels}
            value={sttModelId}
            onChange={setSttModelId}
            disabled={disabled}
            ariaLabel="语音输入模型"
            className="!w-full"
            defaultProfile={defaultBindings?.stt?.profile ?? null}
          />
        </div>
        <div>
          <label className="mb-1 block text-[11px] text-ink-muted">语音输出（播报）</label>
          <ModelSelect
            models={ttsModels}
            value={ttsModelId}
            onChange={setTtsModelId}
            disabled={disabled}
            ariaLabel="语音输出模型"
            className="!w-full"
            defaultProfile={defaultBindings?.tts?.profile ?? null}
          />
        </div>
      </div>
    </div>
  );
}
