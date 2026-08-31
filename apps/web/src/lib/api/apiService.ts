/** 基础 API 服务客户端（对应后端 ``api_service``：档案 / 简历 / 处理器配置） */

import type {
  LLMSettings,
  LLMTestResponse,
  Resume,
  ResumeActivateResponse,
  ResumeAnalysis,
  UserProfile,
} from "@/types";
import { LLM_HEAVY_TIMEOUT_MS, ApiError, parseStructuredErrorResponse, request, resolveBackendUrl } from "@/lib/api/base";

export const apiService = {
  /* LLM 设置（新版按阶段） */
  getStageConfigs: () => request<import("@/types").StageConfigs>("/v1/settings/stages"),
  updateStageConfig: (stage: "recognize" | "reason" | "speak", data: Partial<import("@/types").StageConfig>) =>
    request<import("@/types").StageConfig>(`/v1/settings/stages/${stage}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  /* 兼容旧版 */
  getLLMSettings: () => request<LLMSettings>("/v1/settings/llm"),
  updateLLMSettings: (data: Partial<import("@/types").LLMSettingsWrite>) =>
    request<LLMSettings>("/v1/settings/llm", {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  testLLM: () => request<LLMTestResponse>("/v1/settings/llm/test", { method: "POST" }),
  getVoiceCatalog: () =>
    request<import("@/types").VoiceCatalog>("/v1/settings/catalog"),
  testPipelineStage: (stage: "recognize" | "reason" | "speak") =>
    request<LLMTestResponse>(`/v1/settings/test/${stage}`, { method: "POST" }),

  /* 模型条目体系（能力声明制） */
  listModelOptions: () =>
    request<{ models: import("@/types").ModelProfile[] }>("/v1/settings/models"),
  listProviders: () =>
    request<{ providers: import("@/types").ProviderWithModels[] }>("/v1/settings/providers"),
  createProvider: (data: import("@/types").ProviderWrite) =>
    request<{ id: number }>("/v1/settings/providers", { method: "POST", body: JSON.stringify(data) }),
  updateProvider: (id: number, data: import("@/types").ProviderWrite) =>
    request<{ id: number }>(`/v1/settings/providers/${id}`, { method: "PUT", body: JSON.stringify(data) }),
  deleteProvider: (id: number) =>
    request<{ deleted: number }>(`/v1/settings/providers/${id}`, { method: "DELETE" }),
  createModel: (providerId: number, data: import("@/types").ModelProfileWrite) =>
    request<import("@/types").ModelProfile>(`/v1/settings/providers/${providerId}/models`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  updateModel: (id: number, data: Partial<import("@/types").ModelProfileWrite>) =>
    request<import("@/types").ModelProfile>(`/v1/settings/models/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  deleteModel: (id: number) =>
    request<{ deleted: number }>(`/v1/settings/models/${id}`, { method: "DELETE" }),
  testModel: (id: number) =>
    request<LLMTestResponse>(`/v1/settings/test/model/${id}`, { method: "POST" }),
  getBindings: () =>
    request<import("@/types").TaskBindings>("/v1/settings/bindings"),
  updateBinding: (
    task: "chat" | "stt" | "tts",
    data: { profile_id: number; fallback_handler?: string; fallback_mode?: string },
  ) =>
    request<import("@/types").TaskBindings>(`/v1/settings/bindings/${task}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  /* 档案 */
  getProfile: () => request<UserProfile>("/v1/profile"),
  updateProfile: (data: Partial<UserProfile>) =>
    request<UserProfile>("/v1/profile", { method: "PUT", body: JSON.stringify(data) }),

  /* 简历 */
  uploadResume: async (file: File): Promise<Resume> => {
    let res: Response;
    try {
      const form = new FormData();
      form.append("file", file);
      res = await fetch(resolveBackendUrl("/api/v1/resume/upload"), {
        method: "POST",
        body: form,
        credentials: "include",
      });
    } catch {
      throw new ApiError("无法连接后端服务", 0);
    }
    if (!res.ok) {
      const error = await parseStructuredErrorResponse(res);
      throw new ApiError(error.message, res.status, error);
    }
    const text = await res.text();
    if (!text) throw new ApiError("服务器返回了空响应", res.status);
    try {
      return JSON.parse(text) as Resume;
    } catch {
      throw new ApiError("服务器返回了无效的 JSON 响应", res.status);
    }
  },
  listResumes: () => request<Resume[]>("/v1/resume/list"),
  activateResume: (id: number) =>
    request<ResumeActivateResponse>(`/v1/resume/${id}/activate`, { method: "POST" }),
  deleteResume: (id: number) =>
    request<{ ok: boolean; id: number }>(`/v1/resume/${id}`, { method: "DELETE" }),
  analyzeResume: (id: number) =>
    request<ResumeAnalysis>(`/v1/resume/${id}/analyze`, {
      method: "POST",
      timeoutMs: LLM_HEAVY_TIMEOUT_MS,
    }),
};
