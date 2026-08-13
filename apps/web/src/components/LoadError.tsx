"use client";

import { AlertCircle, RefreshCw } from "lucide-react";
import { getEnv } from "@/lib/env";

/** API 加载失败提示 · Google alert 风格 */
export function LoadError({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  let backendHint = "（未配置）";
  try {
    const env = getEnv();
    backendHint = env.STREAM_API_BASE || env.API_BASE;
  } catch {
    backendHint = "请检查 NEXT_PUBLIC_* 环境变量";
  }

  return (
    <div className="alert alert-error">
      <span className="icon-badge icon-badge-danger shrink-0">
        <AlertCircle size={16} strokeWidth={1.75} />
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-[13px] font-semibold">加载失败</p>
        <p className="mt-1 break-words text-[13px] leading-relaxed opacity-90">
          {message}
        </p>
        <p className="mt-2 text-[11px] leading-relaxed opacity-70">
          请确认后端已启动(当前配置:
          <code className="mx-1 rounded border border-[var(--danger)]/30 bg-surface-card px-1.5 py-0.5 font-mono text-[11px] text-[var(--danger-ink)]">
            {backendHint}
          </code>
          )。若刚改过端口,请重启 frontend。
        </p>
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="mt-3 inline-flex h-8 items-center gap-1.5 rounded-md border border-[var(--danger)]/30 bg-surface-card px-3 text-[12px] font-medium text-[var(--danger-ink)] transition-colors hover:bg-surface-alt"
          >
            <RefreshCw size={13} />
            重试
          </button>
        )}
      </div>
    </div>
  );
}
