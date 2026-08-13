"use client";

import { useEffect, useState } from "react";
import { apiService as api } from "@/lib/api/apiService";
import type {
  LLMTestResponse,
  StageConfig,
  StageConfigs,
  StageFallbackConfig,
  StageModelCapabilities,
} from "@/types";
import {
  Save,
  Zap,
  CheckCircle,
  XCircle,
  Settings2,
  Brain,
  Mic,
  Volume2,
  Eye,
  EyeOff,
  KeyRound,
  Cpu,
  ArrowRight,
} from "lucide-react";
import { LoadError } from "@/components/LoadError";
import { CollapsibleSection } from "@/components/CollapsibleSection";

type StageKey = "recognize" | "reason" | "speak";

const KEEP = "keep";

const EMPTY_STAGE = (stage: StageKey): StageConfig => ({
  stage,
  provider: "",
  api_base: "",
  protocol: "openai_chat",
  model: "",
  max_tokens: 4096,
  context_window: 128000,
  capabilities: {
    supports_vision: false,
    supports_audio_input: false,
    supports_audio_output: false,
    supports_video_input: false,
  },
  fallback: { handler: "", mode: "" },
  extras: {},
  has_api_key: false,
});

function hydrateStage(stage: StageKey, incoming: StageConfig): StageConfig {
  const base = EMPTY_STAGE(stage);
  const config = {
    ...base,
    ...incoming,
    capabilities: { ...base.capabilities, ...incoming.capabilities },
    fallback: { ...base.fallback, ...incoming.fallback },
    extras: incoming.extras || {},
    api_key: "",
  };
  const isUnconfigured = !config.provider && !config.api_base && !config.model;
  if (isUnconfigured && stage === "recognize") {
    config.capabilities.supports_audio_input = true;
  }
  if (isUnconfigured && stage === "reason") {
    config.capabilities.supports_audio_output = true;
  }
  return config;
}

const STAGE_META: Record<
  StageKey,
  { icon: typeof Mic; title: string; hint: string; tone: string }
> = {
  recognize: { icon: Mic, title: "语音识别处理器", hint: "听麦 → 文字", tone: "brand" },
  reason: { icon: Brain, title: "面试思考处理器", hint: "必须是文本 LLM", tone: "warning" },
  speak: { icon: Volume2, title: "语音输出处理器", hint: "可降级为仅字幕", tone: "success" },
};

const PROTOCOL_OPTIONS: { value: StageConfig["protocol"]; label: string }[] = [
  { value: "openai_chat", label: "Chat Completions (/chat/completions)" },
  { value: "anthropic_messages", label: "Anthropic Messages (/v1/messages)" },
  { value: "openai_responses", label: "OpenAI Responses (/responses)" },
];

export default function SettingsPage() {
  const [configs, setConfigs] = useState<StageConfigs | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [saving, setSaving] = useState<StageKey | null>(null);
  const [testing, setTesting] = useState<StageKey | null>(null);
  const [testResults, setTestResults] = useState<Partial<Record<StageKey, LLMTestResponse>>>({});
  const [messages, setMessages] = useState<Partial<Record<StageKey, string>>>({});
  const [showKey, setShowKey] = useState<Partial<Record<StageKey, boolean>>>({});

  const scrollToStage = (stage: StageKey) => {
    const el = document.getElementById(`stage-${stage}`);
    if (!el) return;
    el.scrollIntoView({ behavior: "smooth", block: "start" });
    // 高亮提示
    el.classList.add("ring-google");
    window.setTimeout(() => el.classList.remove("ring-google"), 1600);
  };

  const loadSettings = () => {
    setLoading(true);
    setLoadError("");
    api
      .getStageConfigs()
      .then((s) => {
        setConfigs({
          recognize: hydrateStage("recognize", s.recognize),
          reason: hydrateStage("reason", s.reason),
          speak: hydrateStage("speak", s.speak),
          updated_at: s.updated_at,
        });
      })
      .catch((e) => setLoadError(e instanceof Error ? e.message : "加载失败"))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadSettings();
  }, []);

  const updateStage = (stage: StageKey, patch: Partial<StageConfig>) => {
    setConfigs((prev) => {
      if (!prev) return prev;
      return { ...prev, [stage]: { ...prev[stage], ...patch } };
    });
  };

  const updateCapabilities = (
    stage: StageKey,
    patch: Partial<StageModelCapabilities>
  ) => {
    setConfigs((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        [stage]: {
          ...prev[stage],
          capabilities: { ...prev[stage].capabilities, ...patch },
        },
      };
    });
  };

  const updateFallback = (
    stage: StageKey,
    patch: Partial<StageFallbackConfig>
  ) => {
    setConfigs((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        [stage]: {
          ...prev[stage],
          fallback: { ...prev[stage].fallback, ...patch },
        },
      };
    });
  };

  const handleSave = async (stage: StageKey) => {
    if (!configs) return;
    setSaving(stage);
    setMessages((m) => ({ ...m, [stage]: "" }));
    try {
      const payload = configs[stage];
      const updated = await api.updateStageConfig(stage, {
        provider: payload.provider,
        api_base: payload.api_base,
        api_key: payload.api_key || KEEP,
        protocol: payload.protocol,
        model: payload.model,
        max_tokens: payload.max_tokens,
        context_window: payload.context_window,
        capabilities: payload.capabilities,
        fallback: payload.fallback,
        extras: payload.extras,
      });
      setConfigs((prev) =>
        prev
          ? {
              ...prev,
              [stage]: { ...updated, api_key: "" },
            }
          : prev
      );
      setMessages((m) => ({ ...m, [stage]: "已保存" }));
      setTimeout(() => setMessages((m) => ({ ...m, [stage]: "" })), 2000);
    } catch (e) {
      setMessages((m) => ({
        ...m,
        [stage]: e instanceof Error ? e.message : "保存失败",
      }));
    } finally {
      setSaving(null);
    }
  };

  const handleTest = async (stage: StageKey) => {
    setTesting(stage);
    setMessages((m) => ({ ...m, [stage]: "" }));
    try {
      const result = await api.testPipelineStage(stage);
      setTestResults((prev) => ({ ...prev, [stage]: result }));
      if (result.audio_base64 && stage === "speak") {
        try {
          const bin = atob(result.audio_base64);
          const bytes = new Uint8Array(bin.length);
          for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
          const isWav = bytes.length >= 4 && bytes[0] === 0x52 && bytes[1] === 0x49 && bytes[2] === 0x46 && bytes[3] === 0x46;
          const blob = new Blob([bytes], { type: isWav ? "audio/wav" : "audio/mpeg" });
          const url = URL.createObjectURL(blob);
          const audio = new Audio(url);
          void audio.play().finally(() => URL.revokeObjectURL(url));
        } catch {
          /* 试听失败不影响测试结果展示 */
        }
      }
    } catch (e) {
      setTestResults((prev) => ({
        ...prev,
        [stage]: {
          success: false,
          message: e instanceof Error ? e.message : "测试失败",
        },
      }));
    } finally {
      setTesting(null);
    }
  };

  return (
    <div className="page-shell !max-w-6xl anim-rise">
      <div className="page-header">
        <div className="flex items-start gap-3">
          <span className="icon-badge">
            <Settings2 size={18} strokeWidth={1.75} />
          </span>
          <div>
            <p className="page-eyebrow">Pipeline</p>
            <h1 className="page-title">三处理器设置</h1>
            <p className="page-desc">
              语音识别 → 面试思考 → 语音输出,各自独立指派;密钥本地加密。
            </p>
          </div>
        </div>
      </div>

      {/* Pipeline Overview · 可点击跳转 */}
      <div className="surface-card mb-6 overflow-hidden">
        <div className="flex items-center justify-between border-b border-surface-border bg-surface-alt px-4 py-2.5">
          <div className="flex items-center gap-2">
            <Cpu size={13} className="text-ink-muted" />
            <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-ink-muted">
              Pipeline Overview
            </span>
          </div>
          <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-ink-subtle">
            点击跳转
          </span>
        </div>
        <div className="grid grid-cols-1 divide-y divide-surface-border sm:grid-cols-3 sm:divide-x sm:divide-y-0">
          {(Object.keys(STAGE_META) as StageKey[]).map((stage, idx) => {
            const meta = STAGE_META[stage];
            const configured = !!configs?.[stage]?.provider;
            return (
              <button
                key={stage}
                type="button"
                onClick={() => scrollToStage(stage)}
                className="group relative flex items-center gap-3 px-5 py-4 text-left transition-colors duration-base ease-google hover:bg-[var(--info-soft)]"
              >
                <span className="icon-badge icon-badge-muted transition-colors group-hover:icon-badge-brand">
                  <meta.icon size={15} strokeWidth={1.75} />
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-[11px] font-semibold text-ink-subtle">
                      {String(idx + 1).padStart(2, "0")}
                    </span>
                    <p className="truncate text-[13px] font-medium text-ink">{meta.title}</p>
                  </div>
                  <p className="mt-0.5 truncate text-[11px] text-ink-subtle">{meta.hint}</p>
                </div>
                <div className="flex items-center gap-1.5">
                  <span className={configured ? "chip chip-green" : "chip chip-gray"}>
                    {configured ? "已配置" : "未配置"}
                  </span>
                  <ArrowRight
                    size={13}
                    className="text-ink-subtle transition-transform duration-base group-hover:translate-x-0.5 group-hover:text-[var(--primary)]"
                  />
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center gap-2 py-16 text-[13px] text-ink-muted">
          <span className="block h-4 w-4 anim-spin rounded-full border-2 border-current border-t-transparent" />
          加载设置…
        </div>
      ) : loadError ? (
        <LoadError message={loadError} onRetry={loadSettings} />
      ) : configs ? (
        <div className="space-y-5">
          <div className="alert alert-info">
            <KeyRound size={14} className="mt-0.5 shrink-0" />
            <span className="text-[13px] leading-relaxed">
              管道顺序:语音识别 → 面试思考(文本 LLM)→ 语音输出;各阶段凭证相互独立保存与测试。
            </span>
          </div>

          {(Object.keys(STAGE_META) as StageKey[]).map((stage) => (
            <div key={stage} id={`stage-${stage}`} className="rounded-lg transition-shadow duration-slow">
              <StageSection
                stage={stage}
                config={configs[stage]}
                testing={testing === stage}
                saving={saving === stage}
                message={messages[stage] || ""}
                showKey={showKey[stage] || false}
                testResult={testResults[stage]}
                onUpdate={(patch) => updateStage(stage, patch)}
                onUpdateCapabilities={(patch) => updateCapabilities(stage, patch)}
                onUpdateFallback={(patch) => updateFallback(stage, patch)}
                onToggleKey={() =>
                  setShowKey((prev) => ({ ...prev, [stage]: !prev[stage] }))
                }
                onSave={() => handleSave(stage)}
                onTest={() => handleTest(stage)}
              />
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function StageSection({
  stage,
  config,
  testing,
  saving,
  message,
  showKey,
  testResult,
  onUpdate,
  onUpdateCapabilities,
  onUpdateFallback,
  onToggleKey,
  onSave,
  onTest,
}: {
  stage: StageKey;
  config: StageConfig;
  testing: boolean;
  saving: boolean;
  message: string;
  showKey: boolean;
  testResult?: LLMTestResponse;
  onUpdate: (patch: Partial<StageConfig>) => void;
  onUpdateCapabilities: (patch: Partial<StageModelCapabilities>) => void;
  onUpdateFallback: (patch: Partial<StageFallbackConfig>) => void;
  onToggleKey: () => void;
  onSave: () => void;
  onTest: () => void;
}) {
  const meta = STAGE_META[stage];
  const Icon = meta.icon;

  const isRecognize = stage === "recognize";
  const isReason = stage === "reason";
  const isSpeak = stage === "speak";

  return (
    <section className="surface-card overflow-hidden">
      <header className="flex flex-wrap items-start justify-between gap-3 border-b border-surface-border bg-surface-alt px-5 py-3.5">
        <div className="flex items-center gap-2.5">
          <span className="icon-badge icon-badge-brand">
            <Icon size={15} strokeWidth={1.75} />
          </span>
          <div>
            <h2 className="text-[14px] font-semibold tracking-tight text-ink">{meta.title}</h2>
            {meta.hint && (
              <p className="mt-0.5 text-[11px] text-ink-subtle">{meta.hint}</p>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {message && (
            <span
              className={`text-[12px] font-medium ${
                message.includes("失败") ? "text-[var(--danger-ink)]" : "text-[var(--success-ink)]"
              }`}
            >
              {message}
            </span>
          )}
          <button type="button" onClick={onTest} disabled={testing} className="btn-secondary">
            {testing ? (
              <span className="block h-3.5 w-3.5 anim-spin rounded-full border-2 border-current border-t-transparent" />
            ) : (
              <Zap size={13} />
            )}
            测试
          </button>
          <button type="button" onClick={onSave} disabled={saving} className="btn-primary">
            {saving ? (
              <span className="block h-3.5 w-3.5 anim-spin rounded-full border-2 border-current border-t-transparent" />
            ) : (
              <Save size={13} />
            )}
            保存
          </button>
        </div>
      </header>

      <div className="grid grid-cols-1 gap-4 p-5 sm:grid-cols-2">
        <Field
          label="供应商名称"
          value={config.provider}
          onChange={(v) => onUpdate({ provider: v })}
          placeholder="例如:小米 MiMo"
          className="sm:col-span-2"
        />
        <Field
          label="Base URL"
          value={config.api_base}
          onChange={(v) => onUpdate({ api_base: v })}
          className="sm:col-span-2"
        />

        <div className="sm:col-span-2">
          <label className="field-label">API 格式</label>
          <select
            className="field-select"
            value={config.protocol}
            onChange={(e) =>
              onUpdate({ protocol: e.target.value as StageConfig["protocol"] })
            }
          >
            {PROTOCOL_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>

        <div className="sm:col-span-2">
          <label className="field-label">API Key</label>
          <div className="relative">
            <input
              className="field-input pr-10 font-mono text-[13px]"
              type={showKey ? "text" : "password"}
              value={config.api_key || ""}
              onChange={(e) => onUpdate({ api_key: e.target.value })}
              placeholder={config.has_api_key ? "已配置(留空保持)" : "输入 API Key"}
            />
            <button
              type="button"
              onClick={onToggleKey}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-ink-muted hover:text-ink"
              aria-label={showKey ? "隐藏密钥" : "显示密钥"}
            >
              {showKey ? <EyeOff size={15} /> : <Eye size={15} />}
            </button>
          </div>
          <p className="field-hint">密钥仅保存在本地,从不离开你的设备。</p>
        </div>

        <Field
          label="模型名称"
          value={config.model}
          onChange={(v) => onUpdate({ model: v })}
          className="sm:col-span-2"
        />

        <Field
          label="上下文窗口"
          value={String(config.context_window)}
          onChange={(v) => onUpdate({ context_window: Number(v) || 0 })}
          type="number"
        />
        <Field
          label="最大输出"
          value={String(config.max_tokens)}
          onChange={(v) => onUpdate({ max_tokens: Number(v) || 0 })}
          type="number"
        />
        {isSpeak && (
          <>
            <div>
              <label className="field-label">播报模式</label>
              <select
                className="field-select"
                value={String(config.extras.speech_speak_mode || "tts_from_text")}
                onChange={(e) =>
                  onUpdate({
                    extras: { ...config.extras, speech_speak_mode: e.target.value },
                  })
                }
              >
                <option value="tts_from_text">文本转语音</option>
                <option value="text_only">仅字幕</option>
              </select>
            </div>
            <Field
              label="音色 / Voice ID"
              value={String(
                config.extras.tts_voice
                  || (config.provider === "edge"
                    ? "zh-CN-XiaoxiaoNeural"
                    : "mimo_default")
              )}
              onChange={(v) =>
                onUpdate({ extras: { ...config.extras, tts_voice: v } })
              }
              placeholder="mimo_default"
            />
          </>
        )}
      </div>

      <div className="mx-5 mb-5 rounded-md border border-surface-border bg-surface-alt p-4">
        <h3 className="mb-3 text-[12px] font-semibold uppercase tracking-[0.08em] text-ink-muted">
          模型能力
        </h3>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <CapabilityToggle
            label="图片输入"
            checked={config.capabilities.supports_vision}
            onChange={(v) => onUpdateCapabilities({ supports_vision: v })}
          />
          <CapabilityToggle
            label="视频输入"
            checked={config.capabilities.supports_video_input}
            onChange={(v) => onUpdateCapabilities({ supports_video_input: v })}
          />
          <CapabilityToggle
            label="语音输入"
            checked={config.capabilities.supports_audio_input}
            onChange={(v) => onUpdateCapabilities({ supports_audio_input: v })}
          />
          <CapabilityToggle
            label="语音输出"
            checked={config.capabilities.supports_audio_output}
            onChange={(v) => onUpdateCapabilities({ supports_audio_output: v })}
          />
        </div>
      </div>

      {!isReason && (
        <div className="mx-5 mb-5 rounded-md border border-dashed border-surface-border p-4">
          <h3 className="mb-2 text-[12px] font-semibold uppercase tracking-[0.08em] text-ink-muted">
            降级处理
          </h3>
          <p className="mb-3 text-[12px] text-ink-muted">
            主模型失败时继续面试:识别默认回退本地 Whisper,播报默认回退 Edge TTS。
          </p>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Field
              label="降级处理者"
              value={config.fallback.handler}
              onChange={(v) => onUpdateFallback({ handler: v })}
              placeholder={isRecognize ? "local" : "edge"}
            />
            <Field
              label="降级模式"
              value={config.fallback.mode}
              onChange={(v) => onUpdateFallback({ mode: v })}
              placeholder={isRecognize ? "transcribe" : "tts_from_text"}
            />
          </div>
        </div>
      )}

      {testResult && (
        <div className={`alert mx-5 mb-5 ${testResult.success ? "alert-success" : "alert-error"}`}>
          {testResult.success ? (
            <CheckCircle size={14} className="mt-0.5 shrink-0" />
          ) : (
            <XCircle size={14} className="mt-0.5 shrink-0" />
          )}
          <span className="break-words text-[13px] leading-relaxed">{testResult.message}</span>
        </div>
      )}
    </section>
  );
}

function CapabilityToggle({
  label,
  checked,
  onChange,
  disabled,
}: {
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <label
      className={`flex items-center gap-2 rounded-md border border-surface-border bg-surface-card px-3 py-2 text-[13px] ${
        checked ? "border-[var(--primary)] bg-[var(--info-soft)] text-[var(--info-ink)]" : "text-ink-muted"
      } ${disabled ? "cursor-not-allowed opacity-60" : "cursor-pointer hover:border-[var(--primary)]"}`}
    >
      <input
        type="checkbox"
        className="h-3.5 w-3.5 rounded border-surface-border text-[var(--primary)] focus:ring-[var(--primary)]"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span className="font-medium">{label}</span>
      <span
        className={`ml-auto inline-flex h-1.5 w-1.5 rounded-full ${
          checked ? "bg-[var(--primary)]" : "bg-[var(--muted-foreground)] opacity-40"
        }`}
        aria-hidden
      />
    </label>
  );
}

function Field({
  label,
  value,
  onChange,
  type = "text",
  placeholder,
  className = "",
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
  placeholder?: string;
  className?: string;
}) {
  return (
    <div className={className}>
      <label className="field-label">{label}</label>
      <input
        className="field-input font-mono text-[13px]"
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
      />
    </div>
  );
}
