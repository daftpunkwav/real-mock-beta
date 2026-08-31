"use client";

/** prep 会话主 hook：组装资源 / 滚动 / token 批量 / 发送。 */

import { useCallback, useEffect, useRef, useState } from "react";
import { agentService as api } from "@/lib/api/agentService";
import type { PrepHistoryMessage, PrepSessionSummary, PrepUsageStats } from "@/types";
import type { PrepChatMessage } from "./types";
import { mapHistoryMessages } from "./history";
import { usePrepResources } from "./usePrepResources";
import { usePrepScroll } from "./usePrepScroll";
import { usePrepSend } from "./usePrepSend";
import { useTokenBatch } from "./useTokenBatch";

const RESTORE_KEY = "realmock_prep_session_id";

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
  const [prepSessionId, setPrepSessionId] = useState<number | null>(null);
  const [messages, setMessages] = useState<PrepChatMessage[]>([]);
  const [restoring, setRestoring] = useState(false);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [starting, setStarting] = useState(false);
  const [prepError, setPrepError] = useState("");
  const [tokenUsage, setTokenUsage] = useState(0);
  const [usage, setUsage] = useState<PrepUsageStats | null>(null);
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

  function usageFromSummary(s: PrepSessionSummary | undefined): PrepUsageStats | null {
    if (!s || !(s.prompt_tokens || s.completion_tokens || s.cached_tokens)) return null;
    return {
      prompt_tokens: s.prompt_tokens ?? 0,
      completion_tokens: s.completion_tokens ?? 0,
      cached_tokens: s.cached_tokens ?? 0,
    };
  }

  const mergeUsage = useCallback((u: PrepUsageStats) => {
    setUsage((prev) => ({
      prompt_tokens: (prev?.prompt_tokens ?? 0) + u.prompt_tokens,
      completion_tokens: (prev?.completion_tokens ?? 0) + u.completion_tokens,
      cached_tokens: (prev?.cached_tokens ?? 0) + u.cached_tokens,
    }));
  }, []);

  const patchMessage = useCallback((id: string, patch: Partial<PrepChatMessage>) => {
    setMessages((m) => m.map((msg) => (msg.id === id ? { ...msg, ...patch } : msg)));
  }, []);

  useEffect(() => {
    const saved = Number(window.localStorage.getItem(RESTORE_KEY) || 0);
    if (!saved) return;
    setRestoring(true);
    api
      .prepMessages(saved)
      .then((list: PrepHistoryMessage[]) => {
        const restored = mapHistoryMessages(list, nextMsgId);
        if (restored.length === 0) throw new Error("empty session");
        setPrepSessionId(saved);
        setMessages(restored);
        api
          .listPrepSessions()
          .then((ss) => {
            const hit = (Array.isArray(ss) ? ss : []).find((s) => s.id === saved);
            if (hit) {
              setTokenUsage(hit.token_usage || 0);
              setUsage(usageFromSummary(hit));
            }
          })
          .catch(() => {});
      })
      .catch(() => window.localStorage.removeItem(RESTORE_KEY))
      .finally(() => setRestoring(false));
  }, [nextMsgId]);

  const switchSession = useCallback(
    async (id: number) => {
      if (id === prepSessionId || loadingRef.current || restoring) return;
      setRestoring(true);
      try {
        const list = await api.prepMessages(id);
        const restored = mapHistoryMessages(list, nextMsgId);
        if (restored.length === 0) throw new Error("empty session");
        setPrepSessionId(id);
        setMessages(restored);
        setAskDialog(null);
        setTokenUsage(resources.sessions.find((s) => s.id === id)?.token_usage ?? 0);
        setUsage(usageFromSummary(resources.sessions.find((s) => s.id === id)));
        window.localStorage.setItem(RESTORE_KEY, String(id));
      } catch {
        window.localStorage.removeItem(RESTORE_KEY);
      } finally {
        setRestoring(false);
      }
    },
    [prepSessionId, restoring, resources.sessions, nextMsgId],
  );

  const startPrep = useCallback(async () => {
    setStarting(true);
    setPrepError("");
    try {
      const { id } = await api.createPrepSession({
        resume_id: resources.resumeId ?? undefined,
      });
      setPrepSessionId(id);
      window.localStorage.setItem(RESTORE_KEY, String(id));
      setMessages([
        {
          id: nextMsgId("a"),
          role: "assistant",
          content:
            "你好!我是你的面试准备教练。告诉我你的目标岗位,或让我帮你分析简历、出题练习。",
        },
      ]);
      resources.refreshSessions();
      return id;
    } catch (e) {
      setPrepError(e instanceof Error ? e.message : "创建辅导会话失败");
      return null;
    } finally {
      setStarting(false);
    }
  }, [nextMsgId, resources.resumeId, resources.refreshSessions]);

  const { handleSend, handleAskAnswer, handleQuickPrompt } = usePrepSend({
    prepSessionId,
    restoring,
    input,
    setInput,
    setMessages,
    setLoading,
    setTokenUsage,
    setAskDialog,
    loadingRef,
    nextMsgId,
    patchMessage,
    queueToken,
    flushPendingToken,
    stickToBottom: scroll.stickToBottom,
    mergeUsage,
    onAskUser,
    startPrep,
    chatModels: resources.chatModels,
    selectedModelId: resources.selectedModelId,
    defaultChatProfile: resources.defaultChatProfile,
    effort: resources.effort,
  });

  const handleNewSession = async () => {
    if (loadingRef.current || starting || restoring) return;
    setAskDialog(null);
    await startPrep();
  };

  return {
    messages,
    setMessages,
    input,
    setInput,
    loading,
    starting,
    restoring,
    prepError,
    prepSessionId,
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
    tokenUsage,
    usage,
    showJump: scroll.showJump,
    chatScrollRef: scroll.chatScrollRef,
    handleSend,
    handleAskAnswer,
    handleQuickPrompt,
    handleNewSession,
    handleScroll: scroll.handleScroll,
    jumpToBottom: scroll.jumpToBottom,
    switchSession,
    startPrep,
    setAskDialog,
  };
}
