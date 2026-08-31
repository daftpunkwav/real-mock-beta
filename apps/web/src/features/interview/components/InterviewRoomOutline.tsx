"use client";

import { RefreshCw } from "lucide-react";
import { AvatarStage } from "@/features/avatar/AvatarStage";
import type { InterviewRoomModel } from "../hooks/useInterviewRoom";

/** 右侧列：AvatarStage + 参考提纲卡片（loading/空态/依据/隐藏态）。 */
export function InterviewRoomOutline({ room }: { room: InterviewRoomModel }) {
  const {
    sessionMeta,
    emotion,
    aiSpeaking,
    audioLevel,
    showOutline,
    handleOutlineChange,
    requestHint,
    lastQuestion,
    hintLoading,
    referenceHint,
    lastSources,
    phaseLabels,
    currentPhase,
    tokenUsage,
  } = room;

  return (
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
        {showOutline && lastSources.length > 0 && lastSources[0] !== "none" && (
          <p className="mb-2 text-[11px] text-ink-subtle">
            依据：
            {lastSources
              .map((s) =>
                s === "resume"
                  ? "简历"
                  : s === "github"
                    ? "GitHub"
                    : s === "company_kb"
                      ? "企业知识库"
                      : null,
              )
              .filter(Boolean)
              .join("、")}
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
  );
}
