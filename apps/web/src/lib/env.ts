/**
 * 集中读取 NEXT_PUBLIC_* 变量，模块加载时校验，避免：
 *
 * - 多个文件散落重复的 fallback 拼接；
 * - 缺失关键变量时静默回退 localhost 导致线上请求失败。
 *
 * 协议一致性：``NEXT_PUBLIC_API_BASE`` 为 https 时 ``NEXT_PUBLIC_WS_URL``
 * 必须是 ``wss://``；反之亦然。避免混合内容/降级失败。
 */

interface Env {
  API_BASE: string;
  WS_BASE: string;
  STREAM_API_BASE: string;
}

let _cached: Env | null = null;

function readEnv(): Env {
  if (_cached) return _cached;
  const isDev = process.env.NODE_ENV !== "production";

  const apiBase = process.env.NEXT_PUBLIC_API_BASE;
  const wsBase = process.env.NEXT_PUBLIC_WS_URL;
  const streamBase = process.env.NEXT_PUBLIC_STREAM_API_BASE;

  // 生产环境强制要求显式提供
  if (!isDev) {
    const missing: string[] = [];
    if (!apiBase) missing.push("NEXT_PUBLIC_API_BASE");
    if (!wsBase) missing.push("NEXT_PUBLIC_WS_URL");
    if (!streamBase) missing.push("NEXT_PUBLIC_STREAM_API_BASE");
    if (missing.length > 0) {
      throw new Error(
        `[env] 生产环境必须设置: ${missing.join(", ")}。参考 frontend/.env.example`,
      );
    }

    // 协议一致性校验：https ↔ wss、http ↔ ws 必须匹配。
    const apiIsHttps = apiBase!.startsWith("https://");
    const wsIsSecure = wsBase!.startsWith("wss://");
    const streamIsHttps = streamBase!.startsWith("https://");
    if (apiIsHttps !== wsIsSecure) {
      throw new Error(
        `[env] API_BASE 与 WS_URL 协议不一致: api=${apiBase}, ws=${wsBase}`,
      );
    }
    if (apiIsHttps !== streamIsHttps) {
      throw new Error(
        `[env] API_BASE 与 STREAM_API_BASE 协议不一致: api=${apiBase}, stream=${streamBase}`,
      );
    }
  }

  _cached = {
    API_BASE: (apiBase || "http://localhost:8081").replace(/\/+$/, ""),
    WS_BASE: (wsBase || "ws://localhost:8081").replace(/\/+$/, ""),
    STREAM_API_BASE: (streamBase || "http://localhost:8081").replace(/\/+$/, ""),
  };
  return _cached;
}

/** 获取已校验的环境变量对象。模块首次调用时执行校验。 */
export function getEnv(): Env {
  return readEnv();
}
