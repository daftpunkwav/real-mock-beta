/** 直连后端 URL 解析：本机 hostname 对齐（localhost ↔ 127.0.0.1）。 */

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
