"use client";

/** prep 会话生命周期：localStorage 恢复 / 切换会话 / 新建会话。 */

import { useCallback, useEffect, useState, type MutableRefObject } from "react";
import { agentService as api } from "@/lib/api/agentService";
import type { PrepHistoryMessage, PrepSessionSummary, PrepUsageStats } from "@/types";
import type { PrepChatMessage } from "./types";
import { mapHistoryMessages } from "./history";

const RESTORE_KEY = "realmock_prep_session_id";

interface UsePrepChatSessionOptions {
  setMessages: React.Dispatch<React.SetStateAction<PrepChatMessage[]>>;
  setAskDialog: React.Dispatch<
    React.SetStateAction<{ question: string; options: string[] } | null>
  >;
  nextMsgId: (prefix: string) => string;
  loadingRef: MutableRefObject<boolean>;
  sessions: PrepSessionSummary[];
  resumeId: number | null;
  refreshSessions: () => void;
}

export function usePrepChatSession({
  setMessages,
  setAskDialog,
  nextMsgId,
  loadingRef,
  sessions,
  resumeId,
  refreshSessions,
}: UsePrepChatSessionOptions) {
  const [prepSessionId, setPrepSessionId] = useState<number | null>(null);
  const [restoring, setRestoring] = useState(false);
  const [starting, setStarting] = useState(false);
  const [prepError, setPrepError] = useState("");
  const [tokenUsage, setTokenUsage] = useState(0);
  const [usage, setUsage] = useState<PrepUsageStats | null>(null);

  function usageFromSummary(s: PrepSessionSummary | undefined): PrepUsageStats | null {
    if (!s || !(s.prompt_tokens || s.completion_tokens || s.cached_tokens)) return null;
    return {
      prompt_tokens: s.prompt_tokens ?? 0,
      completion_tokens: s.completion_tokens ?? 0,
      cached_tokens: s.cached_tokens ?? 0,
    };
  }

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
  }, [nextMsgId, setMessages]);

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
        setTokenUsage(sessions.find((s) => s.id === id)?.token_usage ?? 0);
        setUsage(usageFromSummary(sessions.find((s) => s.id === id)));
        window.localStorage.setItem(RESTORE_KEY, String(id));
      } catch {
        window.localStorage.removeItem(RESTORE_KEY);
      } finally {
        setRestoring(false);
      }
    },
    [prepSessionId, restoring, sessions, nextMsgId, setMessages, setAskDialog, loadingRef],
  );

  const startPrep = useCallback(async () => {
    setStarting(true);
    setPrepError("");
    try {
      const { id } = await api.createPrepSession({
        resume_id: resumeId ?? undefined,
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
      refreshSessions();
      return id;
    } catch (e) {
      setPrepError(e instanceof Error ? e.message : "创建辅导会话失败");
      return null;
    } finally {
      setStarting(false);
    }
  }, [nextMsgId, resumeId, refreshSessions, setMessages]);

  const handleNewSession = async () => {
    if (loadingRef.current || starting || restoring) return;
    setAskDialog(null);
    await startPrep();
  };

  const mergeUsage = useCallback((u: PrepUsageStats) => {
    setUsage((prev) => ({
      prompt_tokens: (prev?.prompt_tokens ?? 0) + u.prompt_tokens,
      completion_tokens: (prev?.completion_tokens ?? 0) + u.completion_tokens,
      cached_tokens: (prev?.cached_tokens ?? 0) + u.cached_tokens,
    }));
  }, []);

  return {
    prepSessionId,
    restoring,
    starting,
    prepError,
    tokenUsage,
    setTokenUsage,
    usage,
    mergeUsage,
    switchSession,
    startPrep,
    handleNewSession,
  };
}
