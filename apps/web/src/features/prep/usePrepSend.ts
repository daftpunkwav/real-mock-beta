"use client";

/** prep 发送：流式消息、插话排队、快捷提问。 */

import { useRef, type MutableRefObject } from "react";
import { prepCoachHttp as api } from "@/lib/api/clients";
import type { ModelProfile, PrepUsageStats, ReasoningEffort } from "@/types";
import type { PrepChatMessage, PrepStreamHandlers } from "./types";

export function usePrepSend(opts: {
  prepSessionId: number | null;
  restoring: boolean;
  input: string;
  setInput: (v: string) => void;
  setMessages: React.Dispatch<React.SetStateAction<PrepChatMessage[]>>;
  setLoading: (v: boolean) => void;
  setTokenUsage: (v: number) => void;
  setAskDialog: React.Dispatch<
    React.SetStateAction<{ question: string; options: string[] } | null>
  >;
  loadingRef: MutableRefObject<boolean>;
  nextMsgId: (prefix: string) => string;
  patchMessage: (id: string, patch: Partial<PrepChatMessage>) => void;
  queueToken: (id: string, text: string) => void;
  flushPendingToken: () => void;
  stickToBottom: () => void;
  mergeUsage: (u: PrepUsageStats) => void;
  onAskUser: (question: string, options: string[]) => void;
  startPrep: () => Promise<number | null>;
  chatModels: ModelProfile[];
  selectedModelId: number | null;
  defaultChatProfile: ModelProfile | null;
  effort: ReasoningEffort;
}) {
  const pendingSendRef = useRef<string[]>([]);
  const {
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
    stickToBottom,
    mergeUsage,
    onAskUser,
    startPrep,
    chatModels,
    selectedModelId,
    defaultChatProfile,
    effort,
  } = opts;

  const sendMessage = async (
    text: string,
    sessionId?: number,
    skipUserMessage?: boolean,
  ) => {
    const sid = sessionId ?? prepSessionId;
    if (!text.trim() || !sid) return;
    const userMsg = text.trim();

    if (loadingRef.current) {
      if (!skipUserMessage) {
        setMessages((m) => [...m, { id: nextMsgId("u"), role: "user", content: userMsg }]);
      }
      pendingSendRef.current = [...pendingSendRef.current, userMsg];
      setInput("");
      return;
    }
    if (!skipUserMessage) {
      setMessages((m) => [...m, { id: nextMsgId("u"), role: "user", content: userMsg }]);
    }
    const assistantId = nextMsgId("a");
    setInput("");
    loadingRef.current = true;
    setLoading(true);
    stickToBottom();
    setMessages((m) => [
      ...m,
      { id: assistantId, role: "assistant", content: "", streaming: true },
    ]);

    const handlers: PrepStreamHandlers = {
      onToken: (token) => queueToken(assistantId, token),
      onThinking: (chunk) => {
        setMessages((m) =>
          m.map((msg) =>
            msg.id === assistantId
              ? { ...msg, thinking: (msg.thinking ?? "") + chunk }
              : msg,
          ),
        );
      },
      onSearchResults: (groups) => {
        setMessages((m) =>
          m.map((msg) =>
            msg.id === assistantId
              ? { ...msg, searchGroups: [...(msg.searchGroups ?? []), ...groups] }
              : msg,
          ),
        );
      },
      onStatus: (status) => patchMessage(assistantId, { statusText: status }),
      onToolStep: (step) => {
        setMessages((m) =>
          m.map((msg) =>
            msg.id === assistantId
              ? { ...msg, steps: [...(msg.steps ?? []), step] }
              : msg,
          ),
        );
      },
      onAskUser: (question, options) => {
        flushPendingToken();
        patchMessage(assistantId, { statusText: "" });
        setAskDialog({ question, options });
        onAskUser(question, options);
      },
      onUsage: mergeUsage,
    };

    try {
      const selectedModel =
        chatModels.find((m) => m.id === selectedModelId) ??
        (selectedModelId === null ? defaultChatProfile : null);
      const result = await api.prepMessageStream(sid, userMsg, handlers, {
        modelProfileId: selectedModel?.id ?? null,
        reasoningEffort: selectedModel?.capabilities.reasoning ? effort : null,
      });
      flushPendingToken();
      setTokenUsage(result.token_usage);
      patchMessage(assistantId, { streaming: false, statusText: "" });
    } catch (e) {
      flushPendingToken();
      setMessages((m) =>
        m.map((msg) =>
          msg.id === assistantId
            ? {
                ...msg,
                streaming: false,
                statusText: "",
                content: msg.content || `错误:${e instanceof Error ? e.message : "失败"}`,
              }
            : msg,
        ),
      );
    } finally {
      loadingRef.current = false;
      setLoading(false);
      const [next, ...rest] = pendingSendRef.current;
      pendingSendRef.current = rest;
      if (next) {
        setTimeout(() => void sendMessage(next, undefined, true), 50);
      }
    }
  };

  const handleSend = () => {
    void sendMessage(input);
  };

  const handleAskAnswer = (text: string) => {
    setAskDialog(null);
    if (loadingRef.current) {
      setMessages((m) => [...m, { id: nextMsgId("u"), role: "user", content: text.trim() }]);
      pendingSendRef.current = [...pendingSendRef.current, text];
      return;
    }
    void sendMessage(text);
  };

  const handleQuickPrompt = async (prompt: string) => {
    if (restoring) return;
    if (!prepSessionId) {
      const id = await startPrep();
      if (!id) return;
      await sendMessage(prompt, id);
      return;
    }
    await sendMessage(prompt);
  };

  return { sendMessage, handleSend, handleAskAnswer, handleQuickPrompt };
}
