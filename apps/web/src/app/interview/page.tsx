"use client";

/** 面试配置页：状态与数据加载 + 页面组装；大块 JSX 在 features/interview/setup/。 */

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { interviewService as api } from "@/lib/api/interviewService";
import { apiService } from "@/lib/api/apiService";
import { toast } from "@/components/Toast";
import { Play } from "lucide-react";
import { LoadError } from "@/components/LoadError";
import type {
  ModelProfile,
  Options,
  ReasoningEffort,
  ResumePickerItem,
  TaskBindings,
} from "@/types";
import type { InterviewConfig } from "@/types/interview";
import { SetupFields } from "@/features/interview/setup/fields";
import { SetupHeader, SetupLoading, SetupMain } from "@/features/interview/setup/shell";
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
      <SetupHeader action={!loading && !loadError && options ? startButton(false) : undefined} />
      {loading ? (
        <SetupLoading />
      ) : loadError ? (
        <LoadError message={loadError} onRetry={loadData} />
      ) : options ? (
        <SetupMain
          left={
            <SetupFields
              options={options}
              config={config}
              resumes={resumes}
              creating={creating}
              chatModels={chatModels}
              sttModels={sttModels}
              ttsModels={ttsModels}
              chatModelId={chatModelId}
              sttModelId={sttModelId}
              ttsModelId={ttsModelId}
              effort={effort}
              defaultBindings={defaultBindings}
              onConfig={set}
              setChatModelId={setChatModelId}
              setSttModelId={setSttModelId}
              setTtsModelId={setTtsModelId}
              setEffort={setEffort}
              footer={
                <div className="sticky bottom-0 shrink-0 bg-[var(--background)]/90 pb-1 pt-1 backdrop-blur-sm sm:hidden">
                  {startButton(true)}
                </div>
              }
            />
          }
          preview={<InterviewPreview options={options} config={config} resumes={resumes} />}
        />
      ) : null}
    </div>
  );
}
