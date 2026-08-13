/**
 * LLM Provider 基础配置
 *
 * 设置页不再预置具体模型供应商，用户在三个处理器中分别填写供应商名称、
 * Base URL、协议、密钥和模型。真实的 URL 校验仍由后端完成。
 */
export interface LLMProviderPreset {
  /** 数据库保存的 provider id */
  id: string;
  /** 用户可见名称 */
  name: string;
  /** 默认 API 基础地址（不含 /chat/completions 后缀） */
  base: string;
}

export const LLM_PROVIDERS: readonly LLMProviderPreset[] = [
  { id: "custom", name: "自定义供应商", base: "" },
] as const;

export const DEFAULT_LLM_PROVIDER_ID = "custom";
