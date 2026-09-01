"use client";

/** 面试配置页：表单 + 处理器卡 + 右侧预览；default export 维持本页。 */

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { interviewService as api } from "@/lib/api/interviewService";
import { apiService } from "@/lib/api/apiService";
import { toast } from "@/components/Toast";
import { Play, Sparkles } from "lucide-react";
import { LoadError } from "@/components/LoadError";
import type {
  ModelProfile,
  ReasoningEffort,
  Options,
  ResumePickerItem,
  TaskBindings,
} from "@/types";
import type { InterviewConfig } from "@/types/interview";
import {
  ChoiceGroup,
  CompanyGrid,
  ResumeWarning,
  Select,
} from "@/features/interview/setup/controls";
import { ProcessorCard, ResumeSelect, strictnessLabel } from "@/features/interview/setup/form";
import { InterviewPreview } from "@/features/interview/setup/preview";

export default function InterviewSetupPage() {
  const router = useRouter();
  const [options, setOptions] = useState<Options | null>(null);
  const [resumes, setResumes] = useState<ResumePickerItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [creating, setCreating] = useState(false);
  const [config, setConfig] = useState<InterviewConfig>({
    role: "后端工程师",
    level: "中级工程师",
    company: "bytedance",
    workflow_type: "technical",
    personality: "professional",
    strictness: 3,
    interview_style: "deep_dive",
    resume_id: null,
    avatar_id: "professional_male",
    scene_id: "meeting_room",
  });

  const [chatModels, setChatModels] = useState<ModelProfile[]>([]);
  const [sttModels, setSttModels] = useState<ModelProfile[]>([]);
  const [ttsModels, setTtsModels] = useState<ModelProfile[]>([]);
  const [chatModelId, setChatModelId] = useState<number | null>(null);
  const [sttModelId, setSttModelId] = useState<number | null>(null);
  const [ttsModelId, setTtsModelId] = useState<number | null>(null);
  const [effort, setEffort] = useState<ReasoningEffort>("medium");
  const [defaultBindings, setDefaultBindings] = useState<TaskBindings | null>(null);

  const loadData = () => {
    setLoading(true);
    setLoadError("");
    Promise.all([api.getOptions(), api.listResumes()])
      .then(([opts, res]) => {
        setOptions(opts);
        setResumes(res);
        if (res.length > 0) {
          const active = res.find((r) => r.is_active) ?? res[0];
          if (active) setConfig((c) => ({ ...c, resume_id: active.id }));
        }
      })
      .catch((e) => setLoadError(e instanceof Error ? e.message : "加载失败"))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadData();
  }, []);

  // 处理器选择数据:按能力位分桶(缺省回落各任务的默认绑定)；加载失败不阻塞主流程
  useEffect(() => {
    apiService
      .listModelOptions()
      .then((res) => {
        const list = Array.isArray(res?.models) ? res.models : [];
        setChatModels(list.filter((m) => m.capabilities?.chat));
        setSttModels(list.filter((m) => m.capabilities?.audio_input));
        setTtsModels(list.filter((m) => m.capabilities?.audio_output));
      })
      .catch(() => {});
    apiService.getBindings().then(setDefaultBindings).catch(() => {});
  }, []);

  const set = (patch: Partial<InterviewConfig>) => setConfig((c) => ({ ...c, ...patch }));

  const handleStart = async () => {
    setCreating(true);
    try {
      const session = await api.createSessionWithAI(config, {
        chat_profile_id: chatModelId,
        stt_profile_id: sttModelId,
        tts_profile_id: ttsModelId,
        reasoning_effort: effort,
      });
      router.push(`/interview/${session.id}`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "创建失败");
    } finally {
      setCreating(false);
    }
  };

  const startButton = (fullWidth = false) => (
    <button
      type="button"
      className={`btn-primary shrink-0 ${fullWidth ? "w-full" : ""}`}
      onClick={handleStart}
      disabled={creating || loading || !!loadError}
    >
      {creating ? (
        <span className="block h-3.5 w-3.5 anim-spin rounded-full border-2 border-current border-t-transparent" />
      ) : (
        <Play size={14} className="btn-arrow transition-transform" />
      )}
      开始模拟面试
    </button>
  );

  return (
    <div className="page-shell flex h-full flex-col overflow-hidden !py-4 sm:!py-5 anim-rise">
      <div className="mb-4 flex shrink-0 items-center justify-between gap-4">
        <div className="page-header !mb-0 min-w-0">
          <div className="flex items-start gap-3">
            <span className="icon-badge icon-badge-brand shrink-0">
              <Sparkles size={18} strokeWidth={1.75} />
            </span>
            <div className="min-w-0">
              <p className="page-eyebrow">Mock Setup</p>
              <h1 className="page-title !text-[20px]">配置模拟面试</h1>
              <p className="page-desc !text-xs">定制你的专属面试体验</p>
            </div>
          </div>
        </div>
        <div className="hidden sm:block">
          {!loading && !loadError && options ? startButton(false) : null}
        </div>
      </div>

      {loading ? (
        <div className="flex flex-1 items-center justify-center gap-2 text-[13px] text-ink-muted">
          <span className="block h-4 w-4 anim-spin rounded-full border-2 border-current border-t-transparent" />
          加载配置中…
        </div>
      ) : loadError ? (
        <LoadError message={loadError} onRetry={loadData} />
      ) : options ? (
        <div className="grid min-h-0 flex-1 grid-cols-1 gap-3 overflow-hidden lg:grid-cols-[1fr_260px]">
          {/* 左侧配置 */}
          <div className="flex min-h-0 flex-col gap-3 overflow-y-auto pb-2 pr-0.5">
            <div className="surface-card p-3.5">
              <div className="grid grid-cols-2 gap-2.5 lg:grid-cols-4">
                <Select label="目标岗位" value={config.role} options={options.roles} onChange={(v) => set({ role: v })} />
                <Select label="职级" value={config.level} options={options.levels} onChange={(v) => set({ level: v })} />
                <Select
                  label="面试类型"
                  value={config.workflow_type}
                  options={options.workflow_types.map((w) => w.id)}
                  labels={options.workflow_types.map((w) => w.name)}
                  onChange={(v) => set({ workflow_type: v })}
                />
                <Select
                  label="面试风格"
                  value={config.interview_style}
                  options={options.interview_styles.map((s) => s.id)}
                  labels={options.interview_styles.map((s) => s.name)}
                  onChange={(v) => set({ interview_style: v as import("@/types").InterviewStyleId })}
                />
              </div>
            </div>

            <div className="surface-card p-3.5">
              <label className="field-label !mb-2 !text-xs">目标公司</label>
              <CompanyGrid value={config.company} companies={options.companies} onChange={(v) => set({ company: v })} />
            </div>

            <div className="surface-card p-3.5">
              <div className="grid grid-cols-1 items-end gap-3 lg:grid-cols-[1fr_auto]">
                <ChoiceGroup
                  label="面试官性格"
                  value={config.personality}
                  options={options.personalities}
                  onChange={(v) => set({ personality: v })}
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
                    onChange={(e) => set({ strictness: Number(e.target.value) })}
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
                    onChange={(v) => set({ avatar_id: v })}
                  />
                )}
                {options.scenes && options.scenes.length > 0 && (
                  <Select
                    label="面试场景"
                    value={config.scene_id || "meeting_room"}
                    options={options.scenes.map((s) => s.id)}
                    labels={options.scenes.map((s) => s.name)}
                    onChange={(v) => set({ scene_id: v })}
                  />
                )}
                {resumes.length > 0 ? (
                  <ResumeSelect resumes={resumes} value={config.resume_id ?? null} onChange={(v) => set({ resume_id: v })} />
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

            {/* 小屏底部开始按钮 */}
            <div className="sticky bottom-0 shrink-0 bg-[var(--background)]/90 pb-1 pt-1 backdrop-blur-sm sm:hidden">
              {startButton(true)}
            </div>
          </div>

          {/* 右侧摘要(大屏) */}
          <div className="hidden min-h-0 flex-col gap-2.5 overflow-hidden lg:flex">
            <InterviewPreview options={options} config={config} resumes={resumes} />
          </div>
        </div>
      ) : null}
    </div>
  );
}
