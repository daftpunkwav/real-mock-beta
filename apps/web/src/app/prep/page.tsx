"use client";

import { useMemo } from "react";
import { BookOpen, ArrowDown } from "lucide-react";
import {
  AskUserModal,
  AssistantBubble,
  PrepComposer,
  PrepEmptyState,
  PrepSidePanel,
  UserBubble,
  usePrepChat,
} from "@/features/prep";

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
            <PrepEmptyState
              resumeLoadError={resumeLoadError}
              resumes={resumes}
              resumeId={resumeId}
              onResumeChange={setResumeId}
              prepError={prepError}
              starting={starting}
              onStart={startPrep}
            />
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
              <PrepComposer
                messages={messages}
                tokenUsage={tokenUsage}
                usage={usage}
                chatModels={chatModels}
                selectedModelId={selectedModelId}
                onModelChange={setSelectedModelId}
                defaultChatProfile={defaultChatProfile}
                effort={effort}
                onEffortChange={setEffort}
                loading={loading}
                input={input}
                onInputChange={setInput}
                onSend={handleSend}
              />
            </>
          )}
        </div>

        {/* 右侧:上下文与快捷操作 */}
        <PrepSidePanel
          selectedResume={selectedResume}
          sessions={chat.sessions}
          prepSessionId={prepSessionId}
          loading={loading}
          starting={starting}
          onSelectSession={switchSession}
          onNewSession={handleNewSession}
          onQuickPrompt={handleQuickPrompt}
        />
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
