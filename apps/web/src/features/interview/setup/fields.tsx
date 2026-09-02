"use client";

/** 面试配置页左侧表单卡片区：岗位/职级/类型/风格 + 公司 + 性格/严厉 + 人像/场景/简历 + 处理器卡。 */

import type {
  InterviewConfig,
  Options,
  ResumePickerItem,
} from "@/lib/api/contract";
import type {
  ModelProfile,
  ReasoningEffort,
  TaskBindings,
} from "@/types";
import { ChoiceGroup, CompanyGrid, ResumeWarning, Select } from "./controls";
import { ProcessorCard, ResumeSelect, strictnessLabel } from "./form";

export function SetupFields({
  options,
  config,
  resumes,
  creating,
  chatModels,
  sttModels,
  ttsModels,
  chatModelId,
  sttModelId,
  ttsModelId,
  effort,
  defaultBindings,
  onConfig,
  setChatModelId,
  setSttModelId,
  setTtsModelId,
  setEffort,
  footer,
}: {
  options: Options;
  config: InterviewConfig;
  resumes: ResumePickerItem[];
  creating: boolean;
  chatModels: ModelProfile[];
  sttModels: ModelProfile[];
  ttsModels: ModelProfile[];
  chatModelId: number | null;
  sttModelId: number | null;
  ttsModelId: number | null;
  effort: ReasoningEffort;
  defaultBindings: TaskBindings | null;
  onConfig: (patch: Partial<InterviewConfig>) => void;
  setChatModelId: (v: number | null) => void;
  setSttModelId: (v: number | null) => void;
  setTtsModelId: (v: number | null) => void;
  setEffort: (v: ReasoningEffort) => void;
  footer?: React.ReactNode;
}) {
  return (
    <div className="flex min-h-0 flex-col gap-3 overflow-y-auto pb-2 pr-0.5">
      <div className="surface-card p-3.5">
        <div className="grid grid-cols-2 gap-2.5 lg:grid-cols-4">
          <Select label="目标岗位" value={config.role} options={options.roles} onChange={(v) => onConfig({ role: v })} />
          <Select label="职级" value={config.level} options={options.levels} onChange={(v) => onConfig({ level: v })} />
          <Select
            label="面试类型"
            value={config.workflow_type}
            options={options.workflow_types.map((w) => w.id)}
            labels={options.workflow_types.map((w) => w.name)}
            onChange={(v) => onConfig({ workflow_type: v as InterviewConfig["workflow_type"] })}
          />
          <Select
            label="面试风格"
            value={config.interview_style}
            options={options.interview_styles.map((s) => s.id)}
            labels={options.interview_styles.map((s) => s.name)}
            onChange={(v) => onConfig({ interview_style: v as InterviewConfig["interview_style"] })}
          />
        </div>
      </div>

      <div className="surface-card p-3.5">
        <label className="field-label !mb-2 !text-xs">目标公司</label>
        <CompanyGrid value={config.company} companies={options.companies} onChange={(v) => onConfig({ company: v })} />
      </div>

      <div className="surface-card p-3.5">
        <div className="grid grid-cols-1 items-end gap-3 lg:grid-cols-[1fr_auto]">
          <ChoiceGroup
            label="面试官性格"
            value={config.personality}
            options={options.personalities}
            onChange={(v) => onConfig({ personality: v as InterviewConfig["personality"] })}
          />
          <div className="lg:w-48">
            <label className="field-label !mb-2 !text-xs">
              严厉 {config.strictness}/10 · {strictnessLabel(config.strictness)}
            </label>
            <input
              type="range"
              min={1}
              max={10}
              value={config.strictness}
              onChange={(e) => onConfig({ strictness: Number(e.target.value) })}
              className="h-2 w-full accent-[var(--primary)]"
            />
          </div>
        </div>
      </div>

      <div className="surface-card p-3.5">
        <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-3">
          {options.avatars && options.avatars.length > 0 && (
            <Select
              label="面试官形象"
              value={config.avatar_id || "professional_male"}
              options={options.avatars.map((a) => a.id)}
              labels={options.avatars.map((a) => {
                const voiceName =
                  options.tts_voices?.find((v) => v.id === a.voice)?.name || a.voice;
                return voiceName ? `${a.name}(匹配:${voiceName})` : a.name;
              })}
              onChange={(v) => onConfig({ avatar_id: v })}
            />
          )}
          {options.scenes && options.scenes.length > 0 && (
            <Select
              label="面试场景"
              value={config.scene_id || "meeting_room"}
              options={options.scenes.map((s) => s.id)}
              labels={options.scenes.map((s) => s.name)}
              onChange={(v) => onConfig({ scene_id: v })}
            />
          )}
          {resumes.length > 0 ? (
            <ResumeSelect resumes={resumes} value={config.resume_id ?? null} onChange={(v) => onConfig({ resume_id: v })} />
          ) : (
            <ResumeWarning />
          )}

          {/* AI 处理器与思考强度(缺省回落系统默认绑定) */}
          <ProcessorCard
            chatModels={chatModels}
            sttModels={sttModels}
            ttsModels={ttsModels}
            chatModelId={chatModelId}
            sttModelId={sttModelId}
            ttsModelId={ttsModelId}
            effort={effort}
            setChatModelId={setChatModelId}
            setSttModelId={setSttModelId}
            setTtsModelId={setTtsModelId}
            setEffort={setEffort}
            defaultBindings={defaultBindings}
            disabled={creating}
          />
        </div>
      </div>

      {footer}
    </div>
  );
}
