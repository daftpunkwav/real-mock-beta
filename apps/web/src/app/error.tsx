"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { AlertTriangle, RotateCw, Home } from "lucide-react";

interface Props {
  error: Error & { digest?: string };
  reset: () => void;
}

/**
 * 应用根级 Error Boundary。
 *
 * - 任何未捕获渲染错误都会到这里;
 * - ``reset`` 触发该错误重新尝试渲染;
 * - 展示 ``digest``(服务端生成)便于排障。
 */
export default function GlobalError({ error, reset }: Props) {
  const router = useRouter();

  useEffect(() => {
    console.error("[app/error]", error);
  }, [error]);

  return (
    <main className="flex min-h-[70vh] flex-col items-center justify-center px-6 text-center">
      <span className="empty-state-icon !bg-[var(--warning-soft)] !text-[var(--warning-ink)]">
        <AlertTriangle size={24} />
      </span>
      <p className="page-eyebrow mt-4">Error</p>
      <h1 className="mt-1 text-[22px] font-semibold tracking-tight text-ink">页面出现异常</h1>
      <p className="mt-2 max-w-md text-[13px] leading-relaxed text-ink-muted">
        {error.message || "未知错误,请稍后再试。"}
        {error.digest && (
          <span className="mt-2 block font-mono text-[11px] text-ink-subtle">
            trace: {error.digest}
          </span>
        )}
      </p>
      <div className="mt-7 flex flex-wrap justify-center gap-2.5">
        <button type="button" onClick={() => reset()} className="btn-primary">
          <RotateCw size={14} /> 重试
        </button>
        <button type="button" onClick={() => router.push("/")} className="btn-secondary">
          <Home size={14} /> 返回首页
        </button>
      </div>
    </main>
  );
}
