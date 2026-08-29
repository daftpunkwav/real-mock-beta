"use client";

import type { ReactNode } from "react";
import { AvatarStage } from "@/features/avatar/AvatarStage";
import { Flag, Send, WifiOff, Radio, Volume2, AlertTriangle, RefreshCw } from "lucide-react";
import { cn } from "@/lib/utils";
import { ChatBubble } from "./ChatBubble";
import { VideoPanel } from "./VideoPanel";
import { TURN_LABELS, type InterviewRoomModel } from "../hooks/useInterviewRoom";

export function InterviewRoomView({ room }: { room: InterviewRoomModel }) {
  const {
    sessionId,
    sessionIdValid,
    tokenMissing,
    goSetup,
    sessionMeta,
    sessionStatus,
    phaseLabels,
    currentPhase,
    turnState,
    connected,
    everConnected,
    connectionState,
    reconnectAttempt,
    retryNow,
    messages,
    streamingText,
    chatEndRef,
    inputText,
    setInputText,
    canInput,
    canSend,
    handleSend,
    handleFinish,
    finishingUi,
    videoRef,
    isRecording,
    voiceStatus,
    handleFaceAnalysis,
    emotion,
    aiSpeaking,
    audioLevel,
    audioUnlocked,
    audioBlocked,
    handleEnableAudio,
    showOutline,
    handleOutlineChange,
    lastQuestion,
    requestHint,
    hintLoading,
    referenceHint,
    tokenUsage,
  } = room;

  if (!sessionIdValid) {
    return (
      <Gate
        icon={<AlertTriangle size={24} />}
        title="无效的会话 ID"
        desc="请从「面试配置」页重新开始一场面试。"
        tone="warning"
        onPrimary={goSetup}
        primaryLabel="返回配置页"
      />
    );
  }

  if (tokenMissing) {
    return (
      <Gate
        icon={<AlertTriangle size={24} />}
        title="会话无效或无权访问"
        desc="请从「面试配置」页重新开始一场面试。直接打开历史链接可能缺少能力令牌 Cookie。"
        tone="warning"
        onPrimary={goSetup}
        primaryLabel="返回配置页"
      />
    );
  }

  if (!everConnected && connectionState === "failed") {
    return (
      <Gate
        icon={<WifiOff size={24} />}
        title="无法连接到面试服务"
        desc="已尝试 5 次仍失败,请确认后端已启动(默认 :8081)或检查网络。"
        tone="danger"
        onPrimary={retryNow}
        primaryLabel="重新连接"
        onSecondary={goSetup}
        secondaryLabel="返回配置"
      />
    );
  }

  if (!everConnected && !connected) {
    return (
      <div className="h-screen flex flex-col items-center justify-center gap-3 bg-[var(--background)] text-ink-muted">
        <span className="block h-6 w-6 anim-spin rounded-full border-2 border-[var(--primary)] border-t-transparent" />
        <p className="text-[13px]">
          {connectionState === "reconnecting" ? "重新连接中…" : "连接面试服务…"}
        </p>
      </div>
    );
  }

  return (
    <div className="h-screen flex flex-col bg-[var(--background)] text-[var(--foreground)] relative">
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
                onClick={() => retryNow()}
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
            <Radio size={11} className={turnState === "USER_SPEAKING" ? "anim-pulse-dot text-[var(--success)]" : "text-ink-subtle"} />
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

      <div className="flex-1 grid grid-cols-1 lg:grid-cols-[minmax(280px,1fr)_minmax(0,1.8fr)] gap-2 p-2 min-h-0 overflow-hidden">
        <div className="grid grid-rows-[minmax(140px,0.9fr)_minmax(180px,1.1fr)] lg:grid-rows-[1.618fr_1fr] gap-2 min-h-0 order-2 lg:order-1">
          <VideoPanel
            ref={videoRef}
            enabled
            variant="dark"
            micActive={isRecording}
            voiceStatus={voiceStatus}
            onFaceAnalysis={handleFaceAnalysis}
          />

          <div className="rounded-lg border border-surface-border bg-surface-card flex flex-col min-h-0">
            <div className="flex-1 overflow-y-auto p-3 space-y-3">
              {messages.length === 0 && !streamingText && (
                <p className="text-xs text-ink-subtle text-center py-6">
                  {sessionStatus === "active"
                    ? "已恢复会话，等待你的回答"
                    : "面试即将开始,请保持镜头对准自己"}
                </p>
              )}
              {messages.map((m, i) => (
                <ChatBubble key={i} role={m.role} content={m.content} />
              ))}
              {streamingText && (
                <ChatBubble role="assistant" content={streamingText} streaming />
              )}
              <div ref={chatEndRef} />
            </div>

            <div className="border-t border-surface-border p-2 flex gap-2 shrink-0">
              <input
                className="flex-1 rounded-md border border-surface-border bg-surface-card px-3 py-2.5 text-[13px] text-ink placeholder:text-ink-subtle focus:border-[var(--primary)] focus:shadow-focus focus:outline-none disabled:opacity-40"
                placeholder={canInput ? "输入文字回答,或开麦说话…" : "等待面试官…"}
                value={inputText}
                onChange={(e) => setInputText(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleSend()}
                disabled={!canInput}
              />
              <button
                type="button"
                onClick={handleSend}
                disabled={!canSend}
                className="btn-primary !h-10 !w-10 shrink-0 !px-0 disabled:!bg-surface-muted disabled:!text-ink-subtle"
                title={inputText.trim() ? "发送文字" : isRecording ? "发送语音" : "请输入或说话"}
              >
                <Send size={14} />
              </button>
            </div>
          </div>
        </div>

        <div className="grid grid-rows-[minmax(180px,1.4fr)_minmax(120px,0.85fr)] lg:grid-rows-[1.618fr_1fr] gap-2 min-h-0 order-1 lg:order-2">
          <AvatarStage
            avatarId={sessionMeta.avatar_id}
            sceneId={sessionMeta.scene_id}
            emotion={emotion}
            speaking={aiSpeaking}
            audioLevel={audioLevel}
          />
          <div className="rounded-lg border border-surface-border bg-surface-card p-3.5 sm:p-4 overflow-y-auto flex flex-col min-h-0">
            <div className="flex items-center justify-between mb-3 shrink-0 gap-2">
              <h3 className="text-[13px] font-medium text-ink">参考提纲</h3>
              <div className="flex items-center gap-2">
                {showOutline && (
                  <button
                    type="button"
                    onClick={() => requestHint(lastQuestion)}
                    disabled={!lastQuestion || hintLoading}
                    className="inline-flex items-center gap-1 rounded-full border border-surface-border px-2 py-0.5 text-[11px] text-ink-muted transition-colors hover:bg-surface-alt hover:text-ink disabled:opacity-40"
                    title="根据面试官最近的问题重新生成参考回答"
                  >
                    <RefreshCw size={11} className={hintLoading ? "anim-spin" : ""} />
                    重新生成
                  </button>
                )}
                <label className="flex items-center gap-1.5 text-[11px] text-ink-muted cursor-pointer select-none">
                  <input
                    type="checkbox"
                    className="rounded border-surface-border bg-surface-card text-[var(--primary)] focus:ring-[var(--primary)] focus:ring-offset-0"
                    checked={showOutline}
                    onChange={(e) => handleOutlineChange(e.target.checked)}
                  />
                  显示参考
                </label>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-2 text-[11px] text-ink-muted mb-3 shrink-0">
              <div className="kpi-card !p-2.5">
                <span className="kpi-label">阶段</span>
                <p className="mt-1 text-[13px] font-semibold text-ink">
                  {phaseLabels[currentPhase] || "—"}
                </p>
              </div>
              <div className="kpi-card !p-2.5">
                <span className="kpi-label">回复字数</span>
                <p className="mt-1 font-mono text-[13px] font-semibold text-ink num-tabular">
                  {tokenUsage}
                </p>
              </div>
            </div>

            {!showOutline && (
              <p className="text-[11px] leading-relaxed text-ink-subtle">
                参考提纲已隐藏 — 高难度模式,靠自己发挥
              </p>
            )}
            {showOutline && hintLoading && (
              <div className="flex items-center gap-2 text-[11px] text-ink-muted">
                <span className="block h-3.5 w-3.5 anim-spin rounded-full border-2 border-[var(--primary)] border-t-transparent" />
                AI 正在生成参考回答…
              </div>
            )}
            {showOutline && !hintLoading && referenceHint && (
              <div className="flex-1 overflow-y-auto min-h-0">
                {lastQuestion && (
                  <p className="mb-2 line-clamp-2 text-[11px] leading-relaxed text-[var(--info-ink)]">
                    针对:{lastQuestion}
                  </p>
                )}
                <div className="rounded-md border border-surface-border bg-surface-alt p-3 text-[11px] leading-relaxed text-ink whitespace-pre-wrap">
                  {referenceHint}
                </div>
              </div>
            )}
            {showOutline && !hintLoading && !referenceHint && (
              <p className="text-[11px] leading-relaxed text-ink-subtle">
                面试官提问后,AI 将根据你的简历生成参考回答要点。
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function Gate({
  icon,
  title,
  desc,
  tone,
  onPrimary,
  primaryLabel,
  onSecondary,
  secondaryLabel,
}: {
  icon: ReactNode;
  title: string;
  desc: string;
  tone: "warning" | "danger";
  onPrimary: () => void;
  primaryLabel: string;
  onSecondary?: () => void;
  secondaryLabel?: string;
}) {
  const iconClass =
    tone === "danger"
      ? "!bg-[var(--danger-soft)] !text-[var(--danger-ink)]"
      : "!bg-[var(--warning-soft)] !text-[var(--warning-ink)]";
  return (
    <div className="h-screen flex flex-col items-center justify-center gap-4 bg-[var(--background)] px-6 text-center">
      <span className={`empty-state-icon ${iconClass}`}>{icon}</span>
      <div>
        <p className="text-[16px] font-medium text-ink">{title}</p>
        <p className="mt-1.5 max-w-sm text-[13px] text-ink-muted">{desc}</p>
      </div>
      <div className="mt-1 flex flex-wrap items-center justify-center gap-2.5">
        <button type="button" onClick={onPrimary} className="btn-primary">
          {primaryLabel}
        </button>
        {onSecondary && secondaryLabel ? (
          <button type="button" onClick={onSecondary} className="btn-secondary">
            {secondaryLabel}
          </button>
        ) : null}
      </div>
    </div>
  );
}
