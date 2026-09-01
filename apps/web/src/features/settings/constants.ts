/** 设置页共享常量与类型（能力声明制三层数据）。 */

import type { LLMProtocol, ModelProfile } from "@/types";

export const PROTOCOL_OPTIONS: { value: LLMProtocol; label: string }[] = [
  { value: "openai_chat", label: "OpenAI Chat Completions" },
  { value: "anthropic_messages", label: "Anthropic Messages (/v1/messages)" },
  { value: "openai_responses", label: "OpenAI Responses" },
];

export const CAP_OPTIONS: { key: keyof ModelProfile["capabilities"]; label: string }[] = [
  { key: "chat", label: "对话/思考" },
  { key: "vision", label: "视觉输入" },
  { key: "audio_input", label: "语音输入" },
  { key: "audio_output", label: "语音输出" },
  { key: "reasoning", label: "思考强度" },
];

export const TASK_META: {
  task: "chat" | "stt" | "tts";
  label: string;
  hint: string;
  capKey: keyof ModelProfile["capabilities"];
}[] = [
  { task: "chat", label: "思考(chat)", hint: "面试教练 / 模拟面试对话 / 简历评价的默认模型", capKey: "chat" },
  { task: "stt", label: "语音输入(stt)", hint: "面试语音识别;失败时按降级策略回退", capKey: "audio_input" },
  { task: "tts", label: "语音输出(tts)", hint: "面试官播报;失败时按降级策略回退", capKey: "audio_output" },
];

/** 把条目列表按任务能力分桶,供绑定下拉用 */
export function modelsForTask(models: ModelProfile[], capKey: keyof ModelProfile["capabilities"]) {
  return models.filter((m) => m.capabilities?.[capKey]);
}

export function formatWindow(n: number) {
  if (!n) return "—";
  return n >= 1000 ? `${Math.round(n / 1000)}K` : String(n);
}

export interface ModelDraft {
  model: string;
  display_name: string;
  context_window: string;
  max_output: string;
  capabilities: ModelProfile["capabilities"];
  extras_text: string;
}

export const EMPTY_DRAFT: ModelDraft = {
  model: "",
  display_name: "",
  context_window: "128000",
  max_output: "4096",
  capabilities: { chat: true, vision: false, audio_input: false, audio_output: false, reasoning: false },
  extras_text: "",
};
