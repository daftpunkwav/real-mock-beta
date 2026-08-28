/** API 客户端基础层
 *
 * fetch 封装 / SSE 解析 / 错误规范化 / URL 解析。
 * 三个业务域 client（apiService / agentService / interviewService）共享本层。
 *
 * 所有接口**直连后端**（``NEXT_PUBLIC_API_BASE`` / ``STREAM_API_BASE``），
 * ``credentials: "include"`` 以携带 HttpOnly Cookie；错误解析兼容 FastAPI
 * 的 ``{detail: ...}`` 与统一 ``{error:{code,message,trace_id}}`` envelope。
 */

import { getEnv } from "@/lib/env";

const LOOPBACK_HOSTS = new Set(["localhost", "127.0.0.1", "[::1]", "::1"]);

/**
 * 解析直连后端最终 URL（Cookie 与 WS 同 host）。
 *
 * 本机场景把 STREAM_API_BASE 的 hostname 对齐到页面 hostname
 * （localhost ↔ 127.0.0.1），降低 CORS / PNA 失败概率。
 */
export function resolveBackendUrl(apiPath: string): string {
  const path = apiPath.startsWith("/") ? apiPath : `/${apiPath}`;
  const base = getEnv().STREAM_API_BASE;
  if (typeof window === "undefined") {
    return `${base}${path}`;
  }
  try {
    const u = new URL(base);
    const pageHost = window.location.hostname.toLowerCase();
    if (LOOPBACK_HOSTS.has(u.hostname) && LOOPBACK_HOSTS.has(pageHost)) {
      u.hostname = pageHost === "[::1]" || pageHost === "::1" ? "localhost" : pageHost;
    }
    return `${u.origin}${path}`;
  } catch {
    return `${base}${path}`;
  }
}

export interface ApiErrorOptions {
  code?: string;
  hint?: string;
  traceId?: string;
  retryable?: boolean;
}

export class ApiError extends Error {
  status: number;
  code: string;
  hint: string;
  traceId: string;
  retryable: boolean;

  constructor(message: string, status: number, options: ApiErrorOptions = {}) {
    super(message);
    this.status = status;
    this.code = options.code ?? (status === 0 ? "NET0000" : `http_${status}`);
    this.hint = options.hint ?? "";
    this.traceId = options.traceId ?? "";
    this.retryable = options.retryable ?? false;
    this.name = "ApiError";
  }
}

export function formatApiError(error: unknown): string {
  if (!(error instanceof ApiError)) {
    return error instanceof Error ? error.message : String(error);
  }
  return `[${error.code}] ${error.message}${error.hint ? `\n${error.hint}` : ""}`;
}

interface ParsedApiError extends ApiErrorOptions {
  message: string;
}

export async function parseStructuredErrorResponse(res: Response): Promise<ParsedApiError> {
  const text = await res.text();
  if (!text) return { message: `请求失败: ${res.status}` };
  try {
    const data = JSON.parse(text) as {
      detail?: unknown;
      message?: string;
      error?: {
        code?: string;
        message?: string;
        hint?: string;
        trace_id?: string;
        retryable?: boolean;
      };
    };
    if (data.error?.message) {
      return {
        message: data.error.message,
        code: data.error.code,
        hint: data.error.hint,
        traceId: data.error.trace_id,
        retryable: data.error.retryable,
      };
    }
    if (typeof data.detail === "string") return { message: data.detail };
    if (Array.isArray(data.detail)) {
      return {
        message: data.detail
          .map((item) =>
            typeof item === "object" && item && "msg" in item
              ? String((item as { msg: string }).msg)
              : String(item),
          )
          .join("; "),
      };
    }
    if (data.detail) return { message: JSON.stringify(data.detail) };
    if (data.message) return { message: data.message };
  } catch {
    // 非 JSON 响应继续走文本兜底。
  }
  return { message: text.length > 300 ? `${text.slice(0, 300)}…` : text };
}

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
  } catch (e) {
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

interface SSERawEvent {
  type?: unknown;
  content?: unknown;
  token_usage?: unknown;
  message?: unknown;
  report?: unknown;
}

function isSsePayload(value: unknown): value is SSERawEvent {
  return typeof value === "object" && value !== null;
}

function dispatchSseLine<TEvent extends { type: string }>(
  line: string,
  onEvent: (event: TEvent) => void,
): void {
  const trimmed = line.trim();
  if (!trimmed.startsWith("data: ")) return;
  let payload: unknown;
  try {
    payload = JSON.parse(trimmed.slice(6));
  } catch {
    return; // 跳过畸形行而不是中断整个流
  }
  if (!isSsePayload(payload)) return;
  onEvent(payload as TEvent);
}

/** 流式 SSE 解析器：消费 ``onEvent`` 回调；遇到错误抛 ``ApiError``。 */
export async function consumeSSE<TEvent extends { type: string }>(
  res: Response,
  onEvent: (event: TEvent) => void,
): Promise<void> {
  if (!res.body) throw new ApiError("流式响应不可用", res.status);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      buffer += decoder.decode();
      if (buffer.trim()) {
        for (const line of buffer.split("\n")) {
          dispatchSseLine(line, onEvent);
        }
      }
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) {
      dispatchSseLine(line, onEvent);
    }
  }
}
