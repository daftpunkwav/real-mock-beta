/** API 错误规范化：ApiError / 格式化 / FastAPI 响应解析。 */

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

export interface ParsedApiError extends ApiErrorOptions {
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
