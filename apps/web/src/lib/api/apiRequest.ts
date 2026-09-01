/** fetch 封装：超时组合 signal、credentials、直连后端。 */

import { resolveBackendUrl } from "./apiUrl";
import { ApiError, parseStructuredErrorResponse } from "./apiError";

const DEFAULT_REQUEST_TIMEOUT_MS = 30_000;
/** 深度评价 / 长 LLM 任务：模型推理 + 长 JSON 常需 1–3 分钟 */
export const LLM_HEAVY_TIMEOUT_MS = 180_000;

export async function request<T>(
  path: string,
  options: RequestInit & {
    timeoutMs?: number;
    signal?: AbortSignal;
    /** @deprecated 已默认直连后端 */
    direct?: boolean;
  } = {},
): Promise<T> {
  const {
    timeoutMs = DEFAULT_REQUEST_TIMEOUT_MS,
    signal: externalSignal,
    direct: _direct = false,
    ...rest
  } = options;
  void _direct; // 保留 @deprecated direct 参数签名，但不透传给 fetch
  // 组合外部 signal 与超时 signal，任一触发即取消。
  const controller = new AbortController();
  let timedOut = false;
  const timeoutId = setTimeout(() => {
    timedOut = true;
    controller.abort(new Error("request timeout"));
  }, timeoutMs);
  const onExternalAbort = () => controller.abort(externalSignal?.reason);
  if (externalSignal) {
    if (externalSignal.aborted) {
      clearTimeout(timeoutId);
      throw new ApiError("请求已取消", 0);
    }
    externalSignal.addEventListener("abort", onExternalAbort, { once: true });
  }
  // 一律直连后端，确保 HttpOnly Cookie 与 WS 同 host
  const url = resolveBackendUrl(`/api${path}`);
  let res: Response;
  try {
    res = await fetch(url, {
      ...rest,
      credentials: "include",
      headers: { "Content-Type": "application/json", ...rest.headers },
      signal: controller.signal,
    });
  } catch {
    if (controller.signal.aborted) {
      if (timedOut) {
        throw new ApiError(
          timeoutMs > DEFAULT_REQUEST_TIMEOUT_MS
            ? `请求超时（${Math.round(timeoutMs / 1000)}s）。深度评价等 LLM 任务较慢，请稍后重试或检查模型/网络`
            : `请求超时（${Math.round(timeoutMs / 1000)}s）。请确认 backend 已启动（NEXT_PUBLIC_API_BASE / STREAM_API_BASE）`,
          0,
        );
      }
      throw new ApiError("请求已取消", 0);
    }
    throw new ApiError(
      `无法直连后端（${url}）。请确认 backend 已启动，且 NEXT_PUBLIC_STREAM_API_BASE 端口正确`,
      0,
    );
  } finally {
    clearTimeout(timeoutId);
    externalSignal?.removeEventListener("abort", onExternalAbort);
  }
  if (!res.ok) {
    const error = await parseStructuredErrorResponse(res);
    throw new ApiError(error.message, res.status, error);
  }
  const text = await res.text();
  if (!text) return undefined as T;
  try {
    return JSON.parse(text) as T;
  } catch {
    throw new ApiError("服务器返回了无效的 JSON 响应", res.status);
  }
}
