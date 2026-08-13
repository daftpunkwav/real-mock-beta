/** @type {import('next').NextConfig} */
// 后端默认端口：优先环境变量 BACKEND_PORT / NEXT_PUBLIC_API_BASE，否则 8081。
// 端口规划：前端 8080 / 后端 8081；其他服务依次顺延 8082、8083…
const backendOrigin = (
  process.env.NEXT_PUBLIC_API_BASE ||
  `http://127.0.0.1:${process.env.BACKEND_PORT || "8081"}`
).replace(/\/+$/, "");

const wsOrigin = (
  process.env.NEXT_PUBLIC_WS_URL ||
  backendOrigin.replace(/^http/, "ws")
).replace(/\/+$/, "");

const streamOrigin = (
  process.env.NEXT_PUBLIC_STREAM_API_BASE || backendOrigin
).replace(/\/+$/, "");

function originHost(url) {
  try {
    return new URL(url).origin;
  } catch {
    return "";
  }
}

// api.ts 的 resolveBackendUrl 会把后端 hostname 对齐到页面 hostname（localhost ↔ 127.0.0.1），
// 因此 CSP 需同时放行两个 loopback hostname，否则本机以 localhost 打开页面时请求会被 connect-src 拦截。
function connectSrcEntries(url) {
  const origin = originHost(url);
  if (!origin) return [];
  try {
    const u = new URL(origin);
    if (u.hostname === "127.0.0.1") {
      const v = new URL(origin);
      v.hostname = "localhost";
      return [origin, v.origin];
    }
    if (u.hostname === "localhost") {
      const v = new URL(origin);
      v.hostname = "127.0.0.1";
      return [origin, v.origin];
    }
  } catch {
    /* 非标准 URL，保持单值 */
  }
  return [origin];
}

const connectSrc = [
  "'self'",
  ...connectSrcEntries(backendOrigin),
  ...connectSrcEntries(streamOrigin),
  ...connectSrcEntries(wsOrigin),
  // TalkingHead / Three 可能 fetch blob 贴图
  "blob:",
]
  .filter(Boolean)
  .filter((v, i, a) => a.indexOf(v) === i)
  .join(" ");

// 启动时打印，便于确认 CSP connect-src 锁定的后端 origin
if (process.env.NODE_ENV !== "production") {
  console.info(`[next.config] connect-src locked → ${backendOrigin}`);
}

const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  {
    key: "Permissions-Policy",
    value: "camera=(self), microphone=(self), geolocation=()",
  },
  // CSP：收紧 connect-src；TalkingHead/Three 仍需 unsafe-eval
  {
    key: "Content-Security-Policy",
    value: [
      "default-src 'self'",
      // unsafe-eval：TalkingHead / Three 运行时需要；unsafe-inline：主题初始化脚本
      "script-src 'self' 'unsafe-inline' 'unsafe-eval'",
      "style-src 'self' 'unsafe-inline'",
      "img-src 'self' data: blob: https:",
      "font-src 'self' data:",
      `connect-src ${connectSrc}`,
      "media-src 'self' blob: data:",
      "worker-src 'self' blob:",
      "frame-ancestors 'none'",
      "base-uri 'self'",
      "form-action 'self'",
    ].join("; "),
  },
];

if (process.env.NODE_ENV === "production") {
  securityHeaders.push({
    key: "Strict-Transport-Security",
    value: "max-age=63072000; includeSubDomains; preload",
  });
}

const nextConfig = {
  transpilePackages: ["@met4citizen/talkinghead", "three"],
  async headers() {
    return [
      {
        source: "/:path*",
        headers: securityHeaders,
      },
      {
        source: "/avatars/:path*",
        headers: [
          {
            key: "Cache-Control",
            value: "public, max-age=31536000, immutable",
          },
        ],
      },
    ];
  },
};

module.exports = nextConfig;
