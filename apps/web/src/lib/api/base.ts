/** API 客户端基础层（聚合 re-export）
 *
 * fetch 封装 / SSE 解析 / 错误规范化 / URL 解析。
 * 三个业务域 client（apiService / agentService / interviewService）共享本层。
 * 实现分散在 apiUrl / apiError / apiRequest / apiSse 四个子模块。
 *
 * 所有接口**直连后端**（``NEXT_PUBLIC_API_BASE`` / ``STREAM_API_BASE``），
 * ``credentials: "include"`` 以携带 HttpOnly Cookie；错误解析兼容 FastAPI
 * 的 ``{detail: ...}`` 与统一 ``{error:{code,message,trace_id}}`` envelope。
 */

export { resolveBackendUrl } from "./apiUrl";
export {
  ApiError,
  formatApiError,
  parseStructuredErrorResponse,
  type ApiErrorOptions,
  type ParsedApiError,
} from "./apiError";
export { LLM_HEAVY_TIMEOUT_MS, request } from "./apiRequest";
export { consumeSSE } from "./apiSse";
