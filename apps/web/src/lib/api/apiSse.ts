/** 流式 SSE 解析：按行 ``data: `` 解析、畸形行跳过。 */

import { ApiError } from "./apiError";

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
