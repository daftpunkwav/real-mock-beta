"use client";

/** prep 输入条:token 估算 + 上下文表 + 模型/思考强度选择 + 发送。 */

import { Send } from "lucide-react";
import { ContextGauge, EffortSelect, ModelSelect } from "@/components/ModelControls";
import type { ModelProfile, PrepUsageStats, ReasoningEffort } from "@/types";
import type { PrepChatMessage } from "../types";

interface PrepComposerProps {
  messages: PrepChatMessage[];
  tokenUsage: number;
  usage: PrepUsageStats | null;
  chatModels: ModelProfile[];
  selectedModelId: number | null;
  onModelChange: (id: number | null) => void;
  defaultChatProfile: ModelProfile | null;
  effort: ReasoningEffort;
  onEffortChange: (e: ReasoningEffort) => void;
  loading: boolean;
  input: string;
  onInputChange: (v: string) => void;
  onSend: () => void;
}

export function PrepComposer({
  messages,
  tokenUsage,
  usage,
  chatModels,
  selectedModelId,
  onModelChange,
  defaultChatProfile,
  effort,
  onEffortChange,
  loading,
  input,
  onInputChange,
  onSend,
}: PrepComposerProps) {
  const selectedModel =
    chatModels.find((m) => m.id === selectedModelId) ??
    (selectedModelId === null ? defaultChatProfile : null);
  const win = selectedModel?.context_window || 0;
  // 分项:按角色本地估算(与后端 len/1.5 一致);总量取后端统计与本地估算的较大值
  const est = (role: string) =>
    messages.filter((m) => m.role === role).reduce((s, m) => s + m.content.length, 0) / 1.5;
  const userEst = est("user");
  const assistantEst = est("assistant");
  const used = Math.max(tokenUsage || 0, Math.round(userEst + assistantEst));
  const systemEst = Math.max(0, used - userEst - assistantEst);
  return (
    <div className="mt-3 flex shrink-0 items-center gap-2">
      <input
        className="field-input flex-1"
        value={input}
        onChange={(e) => onInputChange(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && onSend()}
        placeholder={loading ? "生成中,输入将排队发送…" : "问我任何面试相关问题…"}
      />
      <ContextGauge
        used={used}
        window={win}
        usage={usage}
        breakdown={[
          { label: "消息", value: userEst, color: "var(--primary)" },
          { label: "回复", value: assistantEst, color: "#8b5cf6" },
          { label: "系统与工具", value: systemEst, color: "#94a3b8" },
        ]}
      />
      <ModelSelect
        models={chatModels}
        value={selectedModelId}
        onChange={onModelChange}
        disabled={loading}
        ariaLabel="选择模型"
        defaultProfile={defaultChatProfile}
      />
      <EffortSelect
        model={selectedModel}
        value={effort}
        onChange={onEffortChange}
        disabled={loading}
      />
      <button
        type="button"
        onClick={onSend}
        className="btn-primary !h-9 !w-12 shrink-0 !px-0"
        aria-label="发送"
      >
        {loading ? (
          <span className="block h-3.5 w-3.5 anim-spin rounded-full border-2 border-current border-t-transparent" />
        ) : (
          <Send size={14} />
        )}
      </button>
    </div>
  );
}
