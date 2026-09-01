"use client";

/** prep 会话主 hook：组装资源 / 会话生命周期 / 滚动 / token 批量 / 发送。 */

import { useCallback, useRef, useState } from "react";
import type { PrepSessionSummary, PrepUsageStats } from "@/types";
import type { PrepChatMessage } from "./types";
import { usePrepResources } from "./usePrepResources";
import { usePrepScroll } from "./usePrepScroll";
import { usePrepSend } from "./usePrepSend";
import { useTokenBatch } from "./useTokenBatch";
import { usePrepChatSession } from "./usePrepChatSession";

export interface UsePrepChatOptions {
  onAskUser: (question: string, options: string[]) => void;
}

export interface UsePrepChat {
  messages: PrepChatMessage[];
  setMessages: React.Dispatch<React.SetStateAction<PrepChatMessage[]>>;
  input: string;
  setInput: (v: string) => void;
  loading: boolean;
  starting: boolean;
  restoring: boolean;
  prepError: string;
  prepSessionId: number | null;
  resumes: ReturnType<typeof usePrepResources>["resumes"];
  resumeId: number | null;
  setResumeId: (v: number | null) => void;
  resumeLoadError: string;
  sessions: PrepSessionSummary[];
  askDialog: { question: string; options: string[] } | null;
  chatModels: ReturnType<typeof usePrepResources>["chatModels"];
  selectedModelId: number | null;
  setSelectedModelId: (v: number | null) => void;
  defaultChatProfile: ReturnType<typeof usePrepResources>["defaultChatProfile"];
  effort: ReturnType<typeof usePrepResources>["effort"];
  setEffort: ReturnType<typeof usePrepResources>["setEffort"];
  tokenUsage: number;
  usage: PrepUsageStats | null;
  showJump: boolean;
  chatScrollRef: React.RefObject<HTMLDivElement | null>;
  handleSend: () => void;
  handleAskAnswer: (text: string) => void;
  handleQuickPrompt: (prompt: string) => Promise<void>;
  handleNewSession: () => Promise<void>;
  handleScroll: () => void;
  jumpToBottom: () => void;
  switchSession: (id: number) => Promise<void>;
  startPrep: () => Promise<number | null>;
  setAskDialog: React.Dispatch<
    React.SetStateAction<{ question: string; options: string[] } | null>
  >;
}

export function usePrepChat({ onAskUser }: UsePrepChatOptions): UsePrepChat {
  const resources = usePrepResources();
  const [messages, setMessages] = useState<PrepChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [askDialog, setAskDialog] = useState<{
    question: string;
    options: string[];
  } | null>(null);

  const msgSeqRef = useRef(0);
  const loadingRef = useRef(false);
  const scroll = usePrepScroll(messages.length);
  const { flushPendingToken, queueToken } = useTokenBatch(setMessages);

  const nextMsgId = useCallback((prefix: string) => {
    msgSeqRef.current += 1;
    return `${prefix}-${msgSeqRef.current}`;
  }, []);

  const patchMessage = useCallback((id: string, patch: Partial<PrepChatMessage>) => {
    setMessages((m) => m.map((msg) => (msg.id === id ? { ...msg, ...patch } : msg)));
  }, []);

  const session = usePrepChatSession({
    setMessages,
    setAskDialog,
    nextMsgId,
    loadingRef,
    sessions: resources.sessions,
    resumeId: resources.resumeId,
    refreshSessions: resources.refreshSessions,
  });

  const { handleSend, handleAskAnswer, handleQuickPrompt } = usePrepSend({
    prepSessionId: session.prepSessionId,
    restoring: session.restoring,
    input,
    setInput,
    setMessages,
    setLoading,
    setTokenUsage: session.setTokenUsage,
    setAskDialog,
    loadingRef,
    nextMsgId,
    patchMessage,
    queueToken,
    flushPendingToken,
    stickToBottom: scroll.stickToBottom,
    mergeUsage: session.mergeUsage,
    onAskUser,
    startPrep: session.startPrep,
    chatModels: resources.chatModels,
    selectedModelId: resources.selectedModelId,
    defaultChatProfile: resources.defaultChatProfile,
    effort: resources.effort,
  });

  return {
    messages,
    setMessages,
    input,
    setInput,
    loading,
    starting: session.starting,
    restoring: session.restoring,
    prepError: session.prepError,
    prepSessionId: session.prepSessionId,
    resumes: resources.resumes,
    resumeId: resources.resumeId,
    setResumeId: resources.setResumeId,
    resumeLoadError: resources.resumeLoadError,
    sessions: resources.sessions,
    askDialog,
    chatModels: resources.chatModels,
    selectedModelId: resources.selectedModelId,
    setSelectedModelId: resources.setSelectedModelId,
    defaultChatProfile: resources.defaultChatProfile,
    effort: resources.effort,
    setEffort: resources.setEffort,
    tokenUsage: session.tokenUsage,
    usage: session.usage,
    showJump: scroll.showJump,
    chatScrollRef: scroll.chatScrollRef,
    handleSend,
    handleAskAnswer,
    handleQuickPrompt,
    handleNewSession: session.handleNewSession,
    handleScroll: scroll.handleScroll,
    jumpToBottom: scroll.jumpToBottom,
    switchSession: session.switchSession,
    startPrep: session.startPrep,
    setAskDialog,
  };
}
