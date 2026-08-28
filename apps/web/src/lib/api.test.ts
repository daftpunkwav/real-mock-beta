/**
 * ApiError 单元测试：结构化字段（code/hint/traceId/retryable）+ 兜底码语义。
 *
 * 验证 E6（错误码体系）前端契约：
 * - 网络失败/超时 status=0 -> NET0000
 * - 后端 envelope error.code 透传
 * - 缺码时按 http_{status} 兜底
 */

import { describe, expect, it } from "vitest";

import { ApiError, consumeSSE, formatApiError } from "./api/base";

describe("ApiError", () => {
  it("无 fields 时按 status 兜底 code", () => {
    const e = new ApiError("not found", 404);
    expect(e.status).toBe(404);
    expect(e.code).toBe("http_404");
    expect(e.message).toBe("not found");
    expect(e.hint).toBe("");
    expect(e.traceId).toBe("");
    expect(e.retryable).toBe(false);
  });

  it("status=0 网络失败默认 NET0000", () => {
    const e = new ApiError("unreachable", 0);
    expect(e.code).toBe("NET0000");
  });

  it("传入 fields 时透传 code/hint/traceId/retryable", () => {
    const e = new ApiError("LLM 不可用", 502, {
      code: "C0001",
      hint: "请检查 Key 与网络",
      traceId: "req-abc123",
      retryable: true,
    });
    expect(e.code).toBe("C0001");
    expect(e.hint).toBe("请检查 Key 与网络");
    expect(e.traceId).toBe("req-abc123");
    expect(e.retryable).toBe(true);
  });

  it("fields 部分缺省字段时按默认值兜底", () => {
    const e = new ApiError("rate limit", 429, { code: "A0002" });
    expect(e.code).toBe("A0002");
    expect(e.retryable).toBe(false);
    expect(e.hint).toBe("");
    expect(e.traceId).toBe("");
  });

  it("status=0 + 显式传 code 时以前者为准", () => {
    // 设计：调用方传了 code 就用调用方的（即使 status=0）
    const e = new ApiError("custom network err", 0, { code: "B0001" });
    expect(e.code).toBe("B0001");
  });

  it("name 设为 ApiError 便于 type guard", () => {
    const e = new ApiError("x", 500);
    expect(e.name).toBe("ApiError");
    expect(e instanceof Error).toBe(true);
    expect(e instanceof ApiError).toBe(true);
  });

  it("可被 try/catch 正常抛出与捕获", () => {
    expect(() => {
      throw new ApiError("boom", 500, { code: "B0001" });
    }).toThrowError(ApiError);
  });
});

describe("formatApiError", () => {
  it("ApiError 含 code+message+hint 时输出两行", () => {
    const e = new ApiError("LLM 不可用", 502, {
      code: "C0001",
      hint: "请检查 Key",
    });
    expect(formatApiError(e)).toBe("[C0001] LLM 不可用\n请检查 Key");
  });

  it("hint 为空时仅显示一行", () => {
    const e = new ApiError("not found", 404);
    expect(formatApiError(e)).toBe("[http_404] not found");
  });

  it("非 ApiError 时降级为 Error.message", () => {
    expect(formatApiError(new Error("boom"))).toBe("boom");
    expect(formatApiError("string err")).toBe("string err");
  });

  it("retryable 字段不改变 formatApiError 输出（用于上层按钮控制）", () => {
    const e = new ApiError("x", 503, { code: "B0001", retryable: true });
    expect(formatApiError(e)).toBe("[B0001] x");
  });
});

function sseResponse(chunks: string[]): Response {
  const encoder = new TextEncoder();
  let i = 0;
  const stream = new ReadableStream<Uint8Array>({
    pull(controller) {
      if (i < chunks.length) {
        controller.enqueue(encoder.encode(chunks[i]));
        i += 1;
      } else {
        controller.close();
      }
    },
  });
  return new Response(stream);
}

describe("consumeSSE", () => {
  it("刷新无换行结尾的最后一块 data 行", async () => {
    const events: { type: string; content?: string }[] = [];
    const res = sseResponse([
      'data: {"type":"token","content":"hello"}\n',
      'data: {"type":"done","content":"ok"}',
    ]);
    await consumeSSE(res, (event) => {
      events.push(event);
    });
    expect(events).toEqual([
      { type: "token", content: "hello" },
      { type: "done", content: "ok" },
    ]);
  });

  it("跳过畸形 JSON 行并继续", async () => {
    const events: { type: string }[] = [];
    const res = sseResponse(['data: not-json\ndata: {"type":"token"}\n']);
    await consumeSSE(res, (event) => {
      events.push(event);
    });
    expect(events).toEqual([{ type: "token" }]);
  });
});
