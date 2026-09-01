"use client";

import { useCallback, useEffect, useRef } from "react";
import type { Dispatch, SetStateAction } from "react";
import type { useRouter } from "next/navigation";
import { toast } from "@/components/Toast";
import type { ChatMessage, ClientEvent, ServerEvent } from "@/types";

/** 可写 ref 的最小结构，兼容 React 18/19 useRef 的返回类型。 */
export type AnyRef<T> = { current: T };

export interface InterviewRoomEventsDeps {
  setStreamingText: Dispatch<SetStateAction<string>>;
  setMessages: Dispatch<SetStateAction<ChatMessage[]>>;
  setCurrentPhase: Dispatch<SetStateAction<string>>;
  setEmotion: Dispatch<SetStateAction<string>>;
  setTokenUsage: Dispatch<SetStateAction<number>>;
  setAudioBlocked: Dispatch<SetStateAction<boolean>>;
  setHintLoading: Dispatch<SetStateAction<boolean>>;
  setReferenceHint: Dispatch<SetStateAction<string>>;
  setLastQuestion: Dispatch<SetStateAction<string>>;
  setFinishingUi: Dispatch<SetStateAction<boolean>>;
  setSttFailUntil: Dispatch<SetStateAction<number>>;
  setLastSources: Dispatch<SetStateAction<string[]>>;
  playbackGenRef: AnyRef<number>;
  expectedPlaybackGenRef: AnyRef<number>;
  lastPlaybackDoneGenRef: AnyRef<number | null>;
  localBargeStopRef: AnyRef<boolean>;
  waitMsRef: AnyRef<number>;
  lastAssistantTextRef: AnyRef<string>;
  hintTimeoutRef: AnyRef<ReturnType<typeof setTimeout> | null>;
  finishingRef: AnyRef<boolean>;
  navigatingRef: AnyRef<boolean>;
  bumpSilenceTimerRef: AnyRef<() => void>;
  sendRef: AnyRef<(p: ClientEvent) => boolean>;
  showOutlineRef: AnyRef<boolean>;
  on: <K extends ServerEvent["type"]>(
    type: K,
    handler: (msg: Extract<ServerEvent, { type: K }>) => void,
  ) => void;
  playBase64Mp3: (data: string) => void;
  stopTTS: (opts?: { silent?: boolean }) => void;
  router: ReturnType<typeof useRouter>;
  sessionId: number;
}

/**
 * WS 事件订阅域：assistant / tts / stt / hint / phase / complete / info / error 全部
 * handler 与收尾导航、hint 超时。世代 ref、TTS、router 经 deps 注入，不复制算法。
 */
export function useInterviewRoomEvents(deps: InterviewRoomEventsDeps) {
  const depsRef = useRef(deps);
  depsRef.current = deps;

  const clearHintTimeout = useCallback(() => {
    const ref = depsRef.current.hintTimeoutRef;
    if (ref.current) {
      clearTimeout(ref.current);
      ref.current = null;
    }
  }, []);

  const requestHint = useCallback(
    (question: string) => {
      const d = depsRef.current;
      if (!d.showOutlineRef.current || !question.trim()) return;
      d.setHintLoading(true);
      d.setReferenceHint("");
      d.setLastQuestion(question);
      clearHintTimeout();
      d.hintTimeoutRef.current = setTimeout(() => {
        d.setHintLoading(false);
        d.setReferenceHint((prev) =>
          prev.trim()
            ? prev
            : "生成较慢或已超时。可先按 STAR：情境 → 任务 → 行动 → 结果（尽量量化）自行组织。",
        );
      }, 25_000);
      d.sendRef.current({ type: "request_hint", question });
    },
    [clearHintTimeout],
  );

  useEffect(() => () => clearHintTimeout(), [clearHintTimeout]);

  const { on, playBase64Mp3, router, sessionId, stopTTS } = deps;

  useEffect(() => {
    const d = depsRef.current;

    const finishOnceAndNavigate = async () => {
      if (d.navigatingRef.current) return;
      d.navigatingRef.current = true;
      d.finishingRef.current = true;
      d.setFinishingUi(true);
      d.stopTTS();
      d.sendRef.current({
        type: "tts_playback_done",
        generation: d.playbackGenRef.current,
      });
      d.router.push(`/report/${d.sessionId}`);
    };

    on("assistant_token", (msg) => d.setStreamingText((prev) => prev + msg.token));

    on("assistant_done", (msg) => {
      d.setMessages((prev) => [...prev, { role: "assistant", content: msg.content }]);
      d.setStreamingText("");
      d.setCurrentPhase(msg.phase);
      d.setEmotion(msg.emotion || "neutral");
      d.setTokenUsage((t) => t + msg.content.length);
      d.lastAssistantTextRef.current = msg.content || "";
      d.setLastSources(Array.isArray(msg.sources) ? msg.sources : []);
      if (typeof msg.playback_generation === "number") {
        d.playbackGenRef.current = msg.playback_generation;
        d.expectedPlaybackGenRef.current = Math.max(
          d.expectedPlaybackGenRef.current,
          msg.playback_generation,
        );
      }
      // 服务端预计作答时长 → 静默计时器按题型个性化，替代固定间隔
      if (typeof msg.wait_seconds === "number" && msg.wait_seconds > 0) {
        d.waitMsRef.current = Math.min(120, Math.max(15, msg.wait_seconds)) * 1000;
        d.bumpSilenceTimerRef.current();
      }
      if (!msg.is_complete) {
        requestHint(msg.content);
      }
      if (msg.is_complete) {
        void finishOnceAndNavigate();
      }
    });

    on("stt_final", (msg) => {
      if (msg.text) d.setMessages((prev) => [...prev, { role: "user", content: msg.text }]);
    });

    on("tts_audio", (msg) => {
      const gen = msg.playback_generation;
      if (typeof gen === "number") {
        if (gen < d.expectedPlaybackGenRef.current) {
          return;
        }
        d.playbackGenRef.current = gen;
        d.expectedPlaybackGenRef.current = Math.max(d.expectedPlaybackGenRef.current, gen);
      }
      playBase64Mp3(msg.data);
    });

    on("tts_failed", (msg) => {
      d.setAudioBlocked(true);
      toast.error(msg.message || "语音播放失败");
      d.setMessages((prev) => [...prev, { role: "assistant", content: `⚠️ ${msg.message}` }]);
      d.sendRef.current({
        type: "tts_playback_done",
        generation: d.playbackGenRef.current,
      });
    });

    on("tts_interrupted", (msg) => {
      if (typeof msg.playback_generation === "number") {
        d.expectedPlaybackGenRef.current = Math.max(
          d.expectedPlaybackGenRef.current,
          msg.playback_generation,
        );
        d.playbackGenRef.current = d.expectedPlaybackGenRef.current;
      }
      if (d.localBargeStopRef.current) {
        d.localBargeStopRef.current = false;
        d.stopTTS({ silent: true });
      } else {
        d.expectedPlaybackGenRef.current =
          Math.max(d.expectedPlaybackGenRef.current, d.playbackGenRef.current) + 1;
        d.playbackGenRef.current = d.expectedPlaybackGenRef.current;
        d.lastPlaybackDoneGenRef.current = null;
        d.stopTTS();
      }
      const n = msg.candidate_interrupts;
      toast.info(
        typeof n === "number"
          ? `已打断发言（累计 ${n} 次，会影响礼貌评分）`
          : "已打断面试官发言",
      );
    });

    on("silence_nudge", (msg) => {
      // LLM 拟真追问按面试官正常发言展示（不再加提示性前缀）
      d.setMessages((prev) => [...prev, { role: "assistant", content: msg.content }]);
      d.lastAssistantTextRef.current = msg.content || "";
    });

    on("reference_hint_loading", () => d.setHintLoading(true));

    on("reference_hint", (msg) => {
      const cleaned = msg.content
        .replace(/<think>[\s\S]*?<\/think>/gi, "")
        .replace(/<thinking>[\s\S]*?<\/thinking>/gi, "")
        .trim();
      clearHintTimeout();
      d.setReferenceHint(cleaned);
      d.setLastQuestion(msg.question || "");
      d.setHintLoading(false);
    });

    on("phase_changed", (msg) => {
      if (msg.phase) d.setCurrentPhase(msg.phase);
    });

    on("interview_complete", () => {
      void finishOnceAndNavigate();
    });

    on("info", (msg) => {
      if (msg.message) toast.info(String(msg.message));
    });

    on("error", (msg) => {
      d.setMessages((prev) => [...prev, { role: "assistant", content: `⚠️ ${msg.message}` }]);
      if (msg.message.includes("收尾") || msg.message.includes("结束面试")) {
        d.finishingRef.current = false;
        d.setFinishingUi(false);
      }
      if (msg.message.includes("未能识别") || msg.message.includes("语音合成失败")) {
        d.setSttFailUntil(Date.now() + 18_000);
        if (msg.message.includes("语音合成") || msg.message.includes("合成失败")) {
          d.setAudioBlocked(true);
        }
        if (msg.message.includes("未能识别")) {
          toast.error("识别失败：可改用下方文字输入继续作答");
        }
      }
    });
  }, [on, playBase64Mp3, router, sessionId, requestHint, stopTTS, clearHintTimeout]);

  return { requestHint, clearHintTimeout };
}
