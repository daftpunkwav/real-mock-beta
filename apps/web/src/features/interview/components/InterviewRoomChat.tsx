"use client";

import { Send } from "lucide-react";
import { ChatBubble } from "./ChatBubble";
import type { InterviewRoomModel } from "../hooks/room";

/** 聊天列：消息流 + streaming + 空态 + 文字/录音发送行。 */
export function InterviewRoomChat({ room }: { room: InterviewRoomModel }) {
  const {
    messages,
    streamingText,
    chatEndRef,
    sessionStatus,
    canInput,
    inputText,
    setInputText,
    canSend,
    handleSend,
    isRecording,
  } = room;

  return (
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
        {streamingText && <ChatBubble role="assistant" content={streamingText} streaming />}
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
  );
}
