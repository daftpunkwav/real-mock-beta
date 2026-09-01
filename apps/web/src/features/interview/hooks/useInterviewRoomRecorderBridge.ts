"use client";

import { useEffect } from "react";
import { useAudioRecorder } from "@/features/media/useAudioRecorder";
import type { RecorderBridge } from "./useInterviewRoomActions";
import type { AnyRef } from "./useInterviewRoomEvents";

export interface InterviewRoomRecorderBridgeDeps {
  micEnabled: boolean;
  captureEnabled: boolean;
  onSilenceStable: (pcm: string, partial: string, sampleRate: number) => void;
  onPartialStable: (text: string) => void;
  onSpeechActivity: () => void;
  onBargeCandidate: () => void;
  recorderRef: AnyRef<RecorderBridge>;
  clearCaptureBuffersRef: AnyRef<() => void>;
  seedCaptureFromRingRef: AnyRef<() => void>;
}

/** recorder 接线：回调经 bridge ref 暴露给动作域，采集能力注入 clear/seed ref。 */
export function useInterviewRoomRecorderBridge(deps: InterviewRoomRecorderBridgeDeps) {
  const recorder = useAudioRecorder(
    deps.micEnabled,
    deps.onSilenceStable,
    deps.onPartialStable,
    deps.onSpeechActivity,
    deps.onBargeCandidate,
    deps.captureEnabled,
  );

  deps.recorderRef.current = {
    flush: recorder.flush,
    isRecording: recorder.isRecording,
    partialText: recorder.partialText,
    micError: recorder.micError,
  };

  useEffect(() => {
    deps.clearCaptureBuffersRef.current = recorder.clearCaptureBuffers;
    deps.seedCaptureFromRingRef.current = recorder.seedCaptureFromRing;
  }, [recorder.clearCaptureBuffers, recorder.seedCaptureFromRing, deps.clearCaptureBuffersRef, deps.seedCaptureFromRingRef]);

  return {
    isRecording: recorder.isRecording,
    partialText: recorder.partialText,
    micError: recorder.micError,
  };
}
