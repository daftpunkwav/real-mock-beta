"use client";

import { useEffect, useState } from "react";
import type { ChatMessage } from "@/types";
import { PHASE_LABELS } from "@/config/phases";
import { interviewService as api } from "@/lib/api/interviewService";
import { toVisibleChatMessages } from "../messages";

export interface InterviewSessionMeta {
  avatar_id: string;
  scene_id: string;
  workflow_type: string;
}

const DEFAULT_META: InterviewSessionMeta = {
  avatar_id: "professional_male",
  scene_id: "meeting_room",
  workflow_type: "technical",
};

/**
 * 房间页会话引导：鉴权、历史回放、阶段文案与静默追问配置。
 * 页面仍持有实时 messages（由 WS 追加）；本 hook 只提供首次/切场次快照。
 */
export function useInterviewRoomBootstrap(sessionId: number) {
  const sessionIdValid = Number.isFinite(sessionId) && sessionId > 0;
  const [tokenMissing, setTokenMissing] = useState(false);
  const [sessionMeta, setSessionMeta] = useState<InterviewSessionMeta>(DEFAULT_META);
  const [historyMessages, setHistoryMessages] = useState<ChatMessage[]>([]);
  const [restoredPhase, setRestoredPhase] = useState("");
  const [sessionStatus, setSessionStatus] = useState("");
  const [silenceNudgeMs, setSilenceNudgeMs] = useState(25000);
  const [phaseLabels, setPhaseLabels] = useState<Record<string, string>>(PHASE_LABELS);
  const [lastAssistantContent, setLastAssistantContent] = useState("");
  const [historySessionId, setHistorySessionId] = useState<number | null>(null);

  useEffect(() => {
    if (!sessionIdValid) return;
    let cancelled = false;
    setTokenMissing(false);
    setHistoryMessages([]);
    setHistorySessionId(null);
    setRestoredPhase("");
    setSessionStatus("");
    setLastAssistantContent("");
    setSessionMeta(DEFAULT_META);

    const load = async () => {
      try {
        const session = await api.getSession(sessionId);
        if (cancelled) return;
        setTokenMissing(false);
        setSessionMeta({
          avatar_id: session.avatar_id || "professional_male",
          scene_id: session.scene_id || "meeting_room",
          workflow_type: session.workflow_type,
        });
        setRestoredPhase(session.current_phase || "");
        setSessionStatus(session.status || "");
        void import("@/features/avatar/AvatarStage").then((m) => {
          m.prefetchAvatar(session.avatar_id || "professional_male");
        });
      } catch (e) {
        if (cancelled) return;
        const status = e && typeof e === "object" && "status" in e ? Number(e.status) : 0;
        setTokenMissing(status === 403 || status === 401);
        return;
      }

      try {
        const raw = await api.getMessages(sessionId);
        if (cancelled) return;
        const visible = toVisibleChatMessages(raw);
        setHistoryMessages(visible);
        const lastAsst = [...visible].reverse().find((m) => m.role === "assistant");
        setLastAssistantContent(lastAsst?.content || "");
        setHistorySessionId(sessionId);
      } catch {
        if (!cancelled) {
          setHistoryMessages([]);
          setHistorySessionId(sessionId);
        }
      }

      try {
        const opts = await api.getOptions();
        if (cancelled) return;
        if (typeof opts.silence_nudge_seconds === "number" && opts.silence_nudge_seconds > 0) {
          setSilenceNudgeMs(opts.silence_nudge_seconds * 1000);
        }
        if (opts.phase_labels) {
          setPhaseLabels({ ...PHASE_LABELS, ...opts.phase_labels });
        }
      } catch {
        /* 离线回退 PHASE_LABELS */
      }
    };

    void load();
    return () => {
      cancelled = true;
    };
  }, [sessionId, sessionIdValid]);

  return {
    sessionIdValid,
    tokenMissing,
    sessionMeta,
    historyMessages,
    restoredPhase,
    sessionStatus,
    silenceNudgeMs,
    phaseLabels,
    lastAssistantContent,
    historySessionId,
  };
}
