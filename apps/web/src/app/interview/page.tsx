"use client";

import { useEffect, useState, useMemo } from "react";
import { useRouter } from "next/navigation";
import { interviewService as api } from "@/lib/api/interviewService";
import { apiService as apiService } from "@/lib/api/apiService";
import { toast } from "@/components/Toast";
import type { Options, Resume, InterviewConfig } from "@/types";
import {
  Play,
  Sparkles,
  Building2,
  UserCircle,
  Briefcase,
  Mic,
  Lightbulb,
  ListChecks,
} from "lucide-react";
import { LoadError } from "@/components/LoadError";

export default function InterviewSetupPage() {
  const router = useRouter();
  const [options, setOptions] = useState<Options | null>(null);
  const [resumes, setResumes] = useState<Resume[]>([]);
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

  const loadData = () => {
    setLoading(true);
    setLoadError("");
    Promise.all([api.getOptions(), apiService.listResumes()])
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

  const selectedCompany = useMemo(
    () => options?.companies.find((c) => c.id === config.company),
    [options, config.company],
  );

  const selectedPersonality = useMemo(
    () => options?.personalities.find((p) => p.id === config.personality),
    [options, config.personality],
  );

  const selectedWorkflow = useMemo(
    () => options?.workflow_types.find((w) => w.id === config.workflow_type),
    [options, config.workflow_type],
  );

  const selectedStyle = useMemo(
    () => options?.interview_styles.find((s) => s.id === config.interview_style),
    [options, config.interview_style],
  );

  const selectedAvatar = useMemo(
    () => options?.avatars?.find((a) => a.id === config.avatar_id),
    [options, config.avatar_id],
  );

  const selectedScene = useMemo(
    () => options?.scenes?.find((s) => s.id === config.scene_id),
    [options, config.scene_id],
  );

  const selectedResume = useMemo(
    () => resumes.find((r) => r.id === config.resume_id),
    [resumes, config.resume_id],
  );

  const strictnessLabel =
    config.strictness <= 3 ? "友好" : config.strictness <= 6 ? "正常" : config.strictness <= 8 ? "高压" : "极限";

  const handleStart = async () => {
    setCreating(true);
    try {
      const session = await api.createSession(config);
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
                <Select label="目标岗位" value={config.role} options={options.roles} onChange={(v) => setConfig({ ...config, role: v })} />
                <Select label="职级" value={config.level} options={options.levels} onChange={(v) => setConfig({ ...config, level: v })} />
                <Select
                  label="面试类型"
                  value={config.workflow_type}
                  options={options.workflow_types.map((w) => w.id)}
                  labels={options.workflow_types.map((w) => w.name)}
                  onChange={(v) => setConfig({ ...config, workflow_type: v })}
                />
                <Select
                  label="面试风格"
                  value={config.interview_style}
                  options={options.interview_styles.map((s) => s.id)}
                  labels={options.interview_styles.map((s) => s.name)}
                  onChange={(v) =>
                    setConfig({
                      ...config,
                      interview_style: v as import("@/types").InterviewStyleId,
                    })
                  }
                />
              </div>
            </div>

            <div className="surface-card p-3.5">
              <label className="field-label !mb-2 !text-xs">目标公司</label>
              <div className="grid grid-cols-3 gap-1.5 sm:grid-cols-4 md:grid-cols-7">
                {options.companies.map((c) => {
                  const selected = config.company === c.id;
                  return (
                    <button
                      key={c.id}
                      type="button"
                      onClick={() => setConfig({ ...config, company: c.id })}
                      className={`rounded-md border px-2 py-2 text-center text-[12px] font-medium transition-all duration-base ease-google active:scale-[0.98] ${
                        selected
                          ? "border-[var(--primary)] bg-[var(--info-soft)] text-[var(--info-ink)] shadow-focus"
                          : "border-surface-border bg-surface-card text-ink-muted hover:border-[var(--primary)] hover:bg-[var(--info-soft)] hover:text-[var(--info-ink)]"
                      }`}
                    >
                      {c.name}
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="surface-card p-3.5">
              <div className="grid grid-cols-1 items-end gap-3 lg:grid-cols-[1fr_auto]">
                <div>
                  <label className="field-label !mb-2 !text-xs">面试官性格</label>
                  <div className="flex flex-wrap gap-1.5">
                    {options.personalities.map((p) => {
                      const selected = config.personality === p.id;
                      return (
                        <button
                          key={p.id}
                          type="button"
                          onClick={() => setConfig({ ...config, personality: p.id })}
                          className={`rounded-md border px-3 py-1.5 text-[12px] font-medium transition-all duration-base ease-google active:scale-[0.98] ${
                            selected
                              ? "border-[var(--primary)] bg-[var(--info-soft)] text-[var(--info-ink)] shadow-focus"
                              : "border-surface-border bg-surface-card text-ink-muted hover:border-[var(--primary)] hover:bg-[var(--info-soft)] hover:text-[var(--info-ink)]"
                          }`}
                        >
                          {p.name}
                        </button>
                      );
                    })}
                  </div>
                </div>
                <div className="lg:w-48">
                  <label className="field-label !mb-2 !text-xs">
                    严厉 {config.strictness}/10 · {strictnessLabel}
                  </label>
                  <input
                    type="range"
                    min={1}
                    max={10}
                    value={config.strictness}
                    onChange={(e) => setConfig({ ...config, strictness: Number(e.target.value) })}
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
                    onChange={(v) => setConfig({ ...config, avatar_id: v })}
                  />
                )}
                {options.scenes && options.scenes.length > 0 && (
                  <Select
                    label="面试场景"
                    value={config.scene_id || "meeting_room"}
                    options={options.scenes.map((s) => s.id)}
                    labels={options.scenes.map((s) => s.name)}
                    onChange={(v) => setConfig({ ...config, scene_id: v })}
                  />
                )}
                {resumes.length > 0 ? (
                  <Select
                    label="关联简历"
                    value={String(config.resume_id)}
                    options={resumes.map((r) => String(r.id))}
                    labels={resumes.map((r) => `${r.filename}${r.is_active ? " (投递)" : ""}`)}
                    onChange={(v) => setConfig({ ...config, resume_id: Number(v) })}
                  />
                ) : (
                  <div>
                    <label className="mb-1 block text-xs font-medium text-ink-muted">
                      关联简历
                    </label>
                    <p className="rounded-md border border-[var(--warning)]/30 bg-[var(--warning-soft)] px-2.5 py-2 text-[11px] text-[var(--warning-ink)]">
                      暂无简历,可稍后在「简历管理」上传
                    </p>
                  </div>
                )}
              </div>
            </div>

            {/* 小屏底部开始按钮 */}
            <div className="sticky bottom-0 shrink-0 bg-[var(--background)]/90 pb-1 pt-1 backdrop-blur-sm sm:hidden">
              {startButton(true)}
            </div>
          </div>

          {/* 右侧摘要(大屏) */}
          <div className="hidden min-h-0 flex-col gap-2.5 overflow-hidden lg:flex">
            <div className="surface-card p-3.5">
              <h2 className="mb-2.5 flex items-center gap-1.5 text-xs font-semibold text-ink">
                <ListChecks size={14} className="text-[var(--primary)]" />
                配置预览
              </h2>
              <div className="space-y-2 text-xs">
                <PreviewRow icon={Briefcase} label="岗位" value={`${config.role} · ${config.level}`} />
                <PreviewRow icon={Building2} label="公司" value={selectedCompany?.name ?? config.company} />
                <PreviewRow icon={Mic} label="类型" value={`${selectedWorkflow?.name ?? ""} · ${selectedStyle?.name ?? ""}`} />
                <PreviewRow
                  icon={UserCircle}
                  label="面试官"
                  value={`${selectedPersonality?.name ?? ""} · ${strictnessLabel}`}
                />
                {(selectedAvatar || selectedScene) && (
                  <PreviewRow
                    icon={UserCircle}
                    label="形象"
                    value={[
                      selectedAvatar?.name,
                      selectedAvatar?.voice
                        ? `音色 ${
                            options.tts_voices?.find((v) => v.id === selectedAvatar.voice)?.name ||
                            selectedAvatar.voice
                          }`
                        : null,
                      selectedScene?.name,
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  />
                )}
                {selectedResume && (
                  <PreviewRow icon={Briefcase} label="简历" value={selectedResume.filename} />
                )}
              </div>
            </div>

            {selectedCompany && (
              <div className="surface-card flex-1 min-h-0 overflow-y-auto p-3.5">
                <h2 className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold text-ink">
                  <Building2 size={14} className="text-[var(--primary)]" />
                  {selectedCompany.name} 面经
                </h2>
                <p className="mb-2 line-clamp-3 text-[11px] leading-snug text-ink-muted">{selectedCompany.style}</p>
                {selectedCompany.focus_areas.length > 0 && (
                  <div className="mb-2 flex flex-wrap gap-1">
                    {selectedCompany.focus_areas.slice(0, 6).map((area) => (
                      <span key={area} className="chip chip-blue !text-[10px]">
                        {area}
                      </span>
                    ))}
                  </div>
                )}
                {selectedWorkflow && selectedWorkflow.phases.length > 0 && (
                  <div className="mb-2">
                    <p className="mb-1 text-[10px] uppercase tracking-[0.08em] text-ink-subtle">
                      流程
                    </p>
                    <p className="font-mono text-[11px] leading-snug text-ink-muted">
                      {selectedWorkflow.phases.join(" → ")}
                    </p>
                  </div>
                )}
                {selectedCompany.sample_questions.length > 0 && (
                  <p className="line-clamp-3 text-[11px] leading-snug text-ink-muted">
                    <span className="text-ink-subtle">参考:</span>
                    {selectedCompany.sample_questions[0]}
                  </p>
                )}
              </div>
            )}

            <div className="surface-card shrink-0 px-3.5 py-2.5">
              <p className="flex items-start gap-1.5 text-[11px] leading-snug text-ink-muted">
                <Lightbulb size={13} className="mt-0.5 shrink-0 text-[var(--primary)]" />
                关联简历后问题更贴合项目;建议先完成 BYOK 配置。
              </p>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function Select({
  label,
  value,
  options,
  labels,
  onChange,
}: {
  label: string;
  value: string;
  options: string[];
  labels?: string[];
  onChange: (v: string) => void;
}) {
  return (
    <div>
      <label className="field-label !mb-1 !text-xs">{label}</label>
      <select value={value} onChange={(e) => onChange(e.target.value)} className="field-select !h-9 !text-xs">
        {options.map((o, i) => (
          <option key={o} value={o}>
            {labels?.[i] || o}
          </option>
        ))}
      </select>
    </div>
  );
}

function PreviewRow({
  icon: Icon,
  label,
  value,
}: {
  icon: React.ComponentType<{ size?: number; className?: string; strokeWidth?: number }>;
  label: string;
  value: string;
}) {
  return (
    <div className="flex items-start gap-1.5">
      <Icon size={12} className="mt-0.5 shrink-0 text-ink-subtle" strokeWidth={1.75} />
      <div className="min-w-0">
        <span className="text-[10px] uppercase tracking-[0.08em] text-ink-subtle">{label}</span>
        <p className="break-words text-[12px] font-medium leading-snug text-ink">{value}</p>
      </div>
    </div>
  );
}
