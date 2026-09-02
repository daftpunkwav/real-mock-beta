"use client";

import { useEffect, useRef } from "react";
import type { ClientEvent } from "@/types";
import type { AnyRef } from "./useInterviewRoomEvents";

export interface InterviewRoomSilenceTimerOpts {
  micEnabled: boolean;
  sttFailUntil: number;
  silenceNudgeMs: number;
  waitMsRef: AnyRef<number>;
  sendRef: AnyRef<(p: ClientEvent) => boolean>;
  /** 必须是房间 hook 持有的同一份 ref：事件/STT 回调靠它 bump。 */
  bumpSilenceTimerRef: AnyRef<() => void>;
}

/** 静默追问计时：开启采集时的 grace 预置与作答中可 bump 的定时器。 */
export function useInterviewRoomSilenceTimer(opts: InterviewRoomSilenceTimerOpts) {
  const { micEnabled, sttFailUntil, silenceNudgeMs, waitMsRef, sendRef, bumpSilenceTimerRef } =
    opts;
  const silenceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const clear = () => {
      if (silenceTimerRef.current) {
        clearTimeout(silenceTimerRef.current);
        silenceTimerRef.current = null;
      }
    };
    bumpSilenceTimerRef.current = () => {
      if (!micEnabled || Date.now() < sttFailUntil) return;
      clear();
      silenceTimerRef.current = setTimeout(() => {
        sendRef.current({ type: "silence_timeout" });
      }, waitMsRef.current || silenceNudgeMs);
    };
    if (!micEnabled || Date.now() < sttFailUntil) {
      clear();
      return;
    }
    const graceMs = Math.min(12_000, Math.max(4_000, Math.floor(silenceNudgeMs * 0.45)));
    silenceTimerRef.current = setTimeout(() => {
      bumpSilenceTimerRef.current();
    }, graceMs);
    return clear;
  }, [micEnabled, sttFailUntil, silenceNudgeMs, waitMsRef, sendRef, bumpSilenceTimerRef]);
}
