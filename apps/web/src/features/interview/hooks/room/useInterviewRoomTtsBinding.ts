"use client";

import { useEffect } from "react";
import type { Dispatch, SetStateAction } from "react";
import type { ClientEvent } from "@/types";
import { useTTSPlayer } from "@/features/media/useTTSPlayer";
import type { AnyRef } from "./useInterviewRoomEvents";

export interface InterviewRoomTtsBindingDeps {
  playbackGenRef: AnyRef<number>;
  lastPlaybackDoneGenRef: AnyRef<number | null>;
  sendRef: AnyRef<(p: ClientEvent) => boolean>;
  setAiSpeaking: Dispatch<SetStateAction<boolean>>;
  setAudioLevel: Dispatch<SetStateAction<number>>;
  setAudioBlocked: Dispatch<SetStateAction<boolean>>;
}

/** TTS 播放器实例 + 回调绑定：口型/阻塞回调、同 gen 去重的 playback_done，卸载时停播并清导航计时。 */
export function useInterviewRoomTtsBinding(deps: InterviewRoomTtsBindingDeps) {
  const {
    playBase64Mp3,
    setOnSpeakingChange,
    setOnAudioLevel,
    setOnPlaybackBlocked,
    setOnPlaybackDone,
    unlockAudio,
    flushHeldQueue,
    retryLastFailed,
    stop,
    audioUnlocked,
  } = useTTSPlayer();

  const { setAiSpeaking, setAudioLevel, setAudioBlocked } = deps;

  useEffect(() => {
    setOnSpeakingChange(setAiSpeaking);
    setOnAudioLevel(setAudioLevel);
    setOnPlaybackBlocked(setAudioBlocked);
    setOnPlaybackDone(() => {
      const g = deps.playbackGenRef.current;
      if (deps.lastPlaybackDoneGenRef.current === g) return;
      deps.lastPlaybackDoneGenRef.current = g;
      deps.sendRef.current({ type: "tts_playback_done", generation: g });
    });
  }, [
    setOnSpeakingChange,
    setOnAudioLevel,
    setOnPlaybackBlocked,
    setOnPlaybackDone,
    setAiSpeaking,
    setAudioLevel,
    setAudioBlocked,
    deps.playbackGenRef,
    deps.lastPlaybackDoneGenRef,
    deps.sendRef,
  ]);

  useEffect(() => {
    return () => {
      stop();
    };
  }, [stop]);

  return {
    playBase64Mp3,
    unlockAudio,
    flushHeldQueue,
    retryLastFailed,
    stopTTS: stop,
    audioUnlocked,
  };
}
