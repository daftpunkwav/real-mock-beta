"use client";

import { useMemo } from "react";
import { ContextGauge, EffortSelect, ModelSelect } from "@/components/ModelControls";
import { PREP_QUICK_PROMPTS } from "@/config/prepPrompts";
import {
  AskUserModal,
  AssistantBubble,
  PrepSessionList,
  UserBubble,
  usePrepChat,
} from "@/features/prep";
import {
  Send,
  BookOpen,
  Sparkles,
  FileText,
  Zap,
  ArrowDown,
} from "lucide-react";

const QUICK_PROMPTS = PREP_QUICK_PROMPTS;

export default function PrepPage() {
  const chat = usePrepChat({
    onAskUser: () => {
      /* ask_user 弹窗由页面统一渲染，状态在 hook 内部维护 */
    },
  });
  const {
    messages,
    input,
    setInput,
    loading,
    starting,
    prepError,
    prepSessionId,
    resumes,
    resumeId,
    setResumeId,
    resumeLoadError,
    chatModels,
    selectedModelId,
    setSelectedModelId,
    defaultChatProfile,
    effort,
    setEffort,
    tokenUsage,
    usage,
    showJump,
    chatScrollRef,
    handleSend,
    handleAskAnswer,
    handleQuickPrompt,
    handleNewSession,
    handleScroll,
    jumpToBottom,
    switchSession,
    startPrep,
    setAskDialog,
  } = chat;

  // 简历列表与场景模型数据在 hook 内加载；页面层只负责展示与事件转发
  const selectedResume = useMemo(
    () => resumes.find((r) => r.id === resumeId) ?? null,
    [resumes, resumeId],
  );

  return (
    <div className="page-shell !max-w-[1600px] flex h-full min-h-0 flex-col overflow-hidden !pb-4 anim-rise">
      <div className="page-header !mb-4 shrink-0">
        <div className="flex items-start gap-3">
          <span className="icon-badge icon-badge-brand">
            <BookOpen size={18} strokeWidth={1.75} />
          </span>
          <div>
            <p className="page-eyebrow">Prep Coach</p>
            <h1 className="page-title">面试准备</h1>
            <p className="page-desc">ReAct 辅导 Agent — 简历分析、面经搜索、主动出题。</p>
          </div>
        </div>
      </div>

      <div className="grid min-h-0 flex-1 grid-cols-1 gap-5 overflow-hidden lg:grid-cols-[1fr_300px]">
        {/* 左侧:对话主区 */}
        <div className="flex min-h-0 flex-col overflow-hidden">
          {!prepSessionId ? (
            <div className="surface-card flex flex-1 flex-col justify-center overflow-hidden p-8">
              <div className="mx-auto w-full max-w-md space-y-5">
                <div className="text-center">
                  <span className="icon-badge icon-badge-brand mx-auto mb-4 !h-14 !w-14">
                    <Sparkles size={22} strokeWidth={1.75} />
                  </span>
                  <h2 className="text-[18px] font-semibold tracking-tight text-ink">
                    开始你的面试辅导
                  </h2>
                  <p className="mt-1.5 text-[13px] text-ink-muted">
                    关联简历后,AI 教练将基于你的背景进行针对性辅导。
                  </p>
                </div>

                {resumeLoadError ? (
                  <div className="alert alert-error !block text-center">{resumeLoadError}</div>
                ) : resumes.length > 0 ? (
                  <div>
                    <label className="field-label">关联简历</label>
                    <select
                      className="field-select"
                      value={resumeId ?? ""}
                      onChange={(e) => setResumeId(Number(e.target.value))}
                    >
                      {resumes.map((r) => (
                        <option key={r.id} value={r.id}>
                          {r.filename}
                          {r.is_active ? " (投递)" : ""}
                        </option>
                      ))}
                    </select>
                  </div>
                ) : (
                  <div className="alert alert-warning !block text-center">
                    暂无简历,可先去「简历管理」上传,也可直接开始通用辅导
                  </div>
                )}

                {prepError && (
                  <div className="alert alert-error !block text-center">{prepError}</div>
                )}

                <button
                  type="button"
                  onClick={startPrep}
                  disabled={starting}
                  className="btn-primary !h-10 w-full"
                >
                  {starting ? (
                    <span className="block h-3.5 w-3.5 anim-spin rounded-full border-2 border-current border-t-transparent" />
                  ) : (
                    <Sparkles size={14} />
                  )}
                  {starting ? "正在连接…" : "开始辅导"}
                </button>
              </div>
            </div>
          ) : (
            <>
              <div className="relative min-h-0 flex-1">
                <div
                  ref={chatScrollRef}
                  onScroll={handleScroll}
                  className="surface-card h-full space-y-3.5 overflow-y-auto p-4"
                >
                  {messages.map((m) =>
                    m.role === "assistant" ? (
                      <AssistantBubble key={m.id} msg={m} />
                    ) : (
                      <UserBubble key={m.id} content={m.content} />
                    ),
                  )}
                </div>
                {showJump && (
                  <button
                    type="button"
                    onClick={jumpToBottom}
                    className="btn-primary absolute bottom-3 right-3 !h-9 !w-9 rounded-full !p-0 shadow-lg"
                    aria-label="回到底部"
                  >
                    <ArrowDown size={15} />
                  </button>
                )}
              </div>
              {(() => {
                const selectedModel =
                  chatModels.find((m) => m.id === selectedModelId) ??
                  (selectedModelId === null ? defaultChatProfile : null);
                const win = selectedModel?.context_window || 0;
                // 分项:按角色本地估算(与后端 len/1.5 一致);总量取后端统计与本地估算的较大值
                const est = (role: string) =>
                  messages
                    .filter((m) => m.role === role)
                    .reduce((s, m) => s + m.content.length, 0) / 1.5;
                const userEst = est("user");
                const assistantEst = est("assistant");
                const used = Math.max(tokenUsage || 0, Math.round(userEst + assistantEst));
                const systemEst = Math.max(0, used - userEst - assistantEst);
                return (
                  <div className="mt-3 flex shrink-0 items-center gap-2">
                    <input
                      className="field-input flex-1"
                      value={input}
                      onChange={(e) => setInput(e.target.value)}
                      onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleSend()}
                      placeholder={loading ? "生成中,输入将排队发送…" : "问我任何面试相关问题…"}
                    />
                    <ContextGauge
                      used={used}
                      window={win}
                      usage={usage}
                      breakdown={[
                        { label: "消息", value: userEst, color: "var(--primary)" },
                        { label: "回复", value: assistantEst, color: "#8b5cf6" },
                        { label: "系统与工具", value: systemEst, color: "#94a3b8" },
                      ]}
                    />
                    <ModelSelect
                      models={chatModels}
                      value={selectedModelId}
                      onChange={setSelectedModelId}
                      disabled={loading}
                      ariaLabel="选择模型"
                      defaultProfile={defaultChatProfile}
                    />
                    <EffortSelect
                      model={selectedModel}
                      value={effort}
                      onChange={setEffort}
                      disabled={loading}
                    />
                    <button
                      type="button"
                      onClick={handleSend}
                      className="btn-primary !h-9 !w-12 shrink-0 !px-0"
                      aria-label="发送"
                    >
                      {loading ? (
                        <span className="block h-3.5 w-3.5 anim-spin rounded-full border-2 border-current border-t-transparent" />
                      ) : (
                        <Send size={14} />
                      )}
                    </button>
                  </div>
                );
              })()}
            </>
          )}
        </div>

        {/* 右侧:上下文与快捷操作 */}
        <div className="hidden min-h-0 flex-col gap-3 overflow-y-auto pr-0.5 lg:flex">
          <div className="surface-card p-4">
            <h2 className="mb-3 flex items-center gap-2 text-[13px] font-semibold tracking-tight text-ink">
              <FileText size={14} className="text-[var(--primary)]" />
              关联简历
            </h2>
            {selectedResume ? (
              <>
                <p className="truncate text-[13px] font-medium text-ink">
                  {selectedResume.filename}
                </p>
                <p className="mt-1 text-[11px] text-ink-subtle">
                  {selectedResume.is_active ? "当前投递" : "未设为投递"}
                  {selectedResume.score != null && ` · 评分 ${selectedResume.score}`}
                </p>
              </>
            ) : (
              <p className="text-[12px] text-ink-subtle">未关联简历,将进行通用辅导</p>
            )}
          </div>

          <div className="surface-card p-4">
            <PrepSessionList
              sessions={chat.sessions}
              currentId={prepSessionId}
              disabled={loading}
              creating={starting}
              onSelect={switchSession}
              onNew={handleNewSession}
            />
          </div>

          <div className="surface-card p-4">
            <h2 className="mb-3 flex items-center gap-2 text-[13px] font-semibold tracking-tight text-ink">
              <Zap size={14} className="text-[var(--warning)]" />
              快捷提问
            </h2>
            <div className="space-y-1.5">
              {QUICK_PROMPTS.map((prompt) => (
                <button
                  key={prompt}
                  type="button"
                  onClick={() => handleQuickPrompt(prompt)}
                  disabled={loading}
                  className="w-full rounded-md border border-surface-border px-3 py-2 text-left text-[12px] leading-relaxed text-ink-muted transition-colors hover:border-[var(--primary)] hover:bg-[var(--info-soft)] hover:text-ink disabled:opacity-50"
                >
                  {prompt}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      {chat.askDialog && (
        <AskUserModal
          question={chat.askDialog.question}
          options={chat.askDialog.options}
          onAnswer={handleAskAnswer}
          onClose={() => setAskDialog(null)}
        />
      )}
    </div>
  );
}
