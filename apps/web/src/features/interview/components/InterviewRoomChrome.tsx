"use client";

import { Flag, Radio, Volume2, WifiOff } from "lucide-react";
import { cn } from "@/lib/utils";
import { TURN_LABELS } from "../hooks/turnLabels";
import type { InterviewRoomModel } from "../hooks/room";

/** 音频解锁遮罩 / 断线条 / 无声条 / 顶栏（会话信息 + 话轮 + 结束按钮）。 */
export function InterviewRoomChrome({ room }: { room: InterviewRoomModel }) {
  const {
    sessionId,
    phaseLabels,
    currentPhase,
    turnState,
    connected,
    connectionState,
    reconnectAttempt,
    audioUnlocked,
    audioBlocked,
    handleEnableAudio,
    finishingUi,
    handleFinish,
  } = room;

  return (
    <>
      {!audioUnlocked && (
        <div className="absolute inset-0 z-50 flex items-center justify-center bg-[var(--background)]/85 p-6 backdrop-blur-md">
          <div className="max-w-sm w-full rounded-lg border border-surface-border bg-surface-card px-6 py-8 text-center shadow-lg">
            <span className="icon-badge icon-badge-brand mx-auto mb-3 !h-12 !w-12">
              <Volume2 size={20} strokeWidth={1.75} />
            </span>
            <h2 className="text-[18px] font-semibold tracking-tight text-ink">启用面试官声音</h2>
            <p className="mt-2 text-[13px] leading-relaxed text-ink-muted">
              浏览器禁止无手势自动播放。请点击下方按钮解锁音频,面试官开场白才会出声。
            </p>
            <button
              type="button"
              onClick={() => void handleEnableAudio()}
              className="btn-primary mt-5 w-full !h-10"
            >
              点击启用声音并开始
            </button>
          </div>
        </div>
      )}
      {!connected && (
        <div className="absolute inset-x-0 top-0 z-30 flex items-center justify-center gap-2 border-b border-[var(--warning)]/30 bg-[var(--warning-soft)] px-3 py-2 text-[var(--warning-ink)] text-xs font-medium shadow-sm">
          {connectionState === "failed" ? (
            <>
              <WifiOff size={14} />
              连接已断开
              <button
                type="button"
                onClick={() => room.retryNow()}
                className="ml-2 underline underline-offset-2 hover:opacity-80"
              >
                重试
              </button>
            </>
          ) : (
            <>
              <span className="block h-3 w-3 anim-spin rounded-full border-2 border-current border-t-transparent" />
              连接中断,正在重连…
              {reconnectAttempt > 0 ? `(第 ${reconnectAttempt} 次)` : ""}
            </>
          )}
        </div>
      )}
      {audioBlocked && (
        <div className="absolute inset-x-0 top-0 z-40 flex items-center justify-center gap-2 border-b border-[var(--danger)]/40 bg-[var(--danger-soft)] px-3 py-2 text-[var(--danger-ink)] text-xs font-medium shadow-sm">
          无声?浏览器可能拦截了自动播放
          <button
            type="button"
            onClick={() => void handleEnableAudio()}
            className="ml-1 inline-flex items-center gap-1 underline underline-offset-2 hover:opacity-80"
          >
            <Volume2 size={12} />
            点击启用并重试
          </button>
        </div>
      )}
      <header className="flex shrink-0 items-center justify-between gap-3 border-b border-surface-border bg-surface-card/80 px-3 backdrop-blur-md py-2.5 sm:px-4">
        <div className="flex min-w-0 items-center gap-2 text-sm sm:gap-3">
          <span className="shrink-0 font-medium text-ink">面试 #{sessionId}</span>
          <span className="truncate rounded-full bg-[var(--info-soft)] px-2 py-0.5 text-xs text-[var(--info-ink)]">
            {phaseLabels[currentPhase] || currentPhase || "准备中"}
          </span>
          <span
            className={cn(
              "hidden sm:inline-flex items-center gap-1 rounded-full border border-surface-border px-2 py-0.5 text-xs",
              turnState === "USER_SPEAKING"
                ? "bg-[var(--success-soft)] text-[var(--success-ink)]"
                : turnState === "AI_SPEAKING"
                  ? "bg-[var(--warning-soft)] text-[var(--warning-ink)]"
                  : "bg-surface-alt text-ink-muted",
            )}
          >
            <Radio
              size={11}
              className={turnState === "USER_SPEAKING" ? "anim-pulse-dot text-[var(--success)]" : "text-ink-subtle"}
            />
            {TURN_LABELS[turnState] || turnState}
          </span>
          {audioUnlocked && !audioBlocked && (
            <button
              type="button"
              onClick={() => void handleEnableAudio()}
              className="hidden rounded-full border border-surface-border px-2 py-0.5 text-[11px] text-ink-muted transition-colors hover:bg-surface-alt hover:text-ink md:inline-flex"
            >
              重新解锁声音
            </button>
          )}
          {!audioUnlocked && (
            <button
              type="button"
              onClick={() => void handleEnableAudio()}
              className="hidden rounded-full border border-[var(--warning)]/40 px-2 py-0.5 text-[11px] text-[var(--warning-ink)] transition-colors hover:bg-[var(--warning-soft)] md:inline-flex"
            >
              启用声音
            </button>
          )}
        </div>
        <button
          type="button"
          onClick={handleFinish}
          disabled={finishingUi}
          className="btn-secondary !text-[var(--danger-ink)] hover:!border-[var(--danger)]/40 hover:!bg-[var(--danger-soft)] shrink-0 !h-8 !text-xs"
        >
          {finishingUi ? (
            <>
              <span className="block h-3 w-3 anim-spin rounded-full border-2 border-current border-t-transparent" />
              收尾评价中…
            </>
          ) : (
            <>
              <Flag size={13} />
              结束面试
            </>
          )}
        </button>
      </header>
    </>
  );
}
