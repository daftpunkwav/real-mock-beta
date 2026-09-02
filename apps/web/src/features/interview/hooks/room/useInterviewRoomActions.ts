"use client";

import { useCallback, useEffect, useRef } from "react";
import type { Dispatch, SetStateAction } from "react";
import { toast } from "@/components/Toast";
import type { ClientEvent, FaceAnalysis } from "@/types";
import { isLikelyEchoOfAssistant } from "../../echo";
import type { VideoPanelHandle } from "../../components/VideoPanel";
import type { AnyRef } from "./useInterviewRoomEvents";

/** recorder 产物桥：回调先于 recorder 定义，动作经此读 recorder 状态/能力。 */
export interface RecorderBridge {
  flush: () => void;
  isRecording: boolean;
  partialText: string;
  micError: string;
}

export interface InterviewRoomActionsDeps {
  setInputText: Dispatch<SetStateAction<string>>;
  setAudioBlocked: Dispatch<SetStateAction<boolean>>;
  setShowOutline: Dispatch<SetStateAction<boolean>>;
  setFinishingUi: Dispatch<SetStateAction<boolean>>;
  turnStateRef: AnyRef<string>;
  bargeLockRef: AnyRef<boolean>;
  aiSpeakStartedAtRef: AnyRef<number>;
  lastAssistantTextRef: AnyRef<string>;
  partialTextRef: AnyRef<string>;
  sttThrottleRef: AnyRef<number>;
  finishingRef: AnyRef<boolean>;
  navigatingRef: AnyRef<boolean>;
  playbackGenRef: AnyRef<number>;
  expectedPlaybackGenRef: AnyRef<number>;
  localBargeStopRef: AnyRef<boolean>;
  lastPlaybackDoneGenRef: AnyRef<number | null>;
  showOutlineRef: AnyRef<boolean>;
  videoRef: AnyRef<VideoPanelHandle | null>;
  faceRef: AnyRef<FaceAnalysis>;
  seedCaptureFromRingRef: AnyRef<() => void>;
  bumpSilenceTimerRef: AnyRef<() => void>;
  sendRef: AnyRef<(p: ClientEvent) => boolean>;
  recorderRef: AnyRef<RecorderBridge>;
  send: (p: ClientEvent) => boolean;
  stopTTS: (opts?: { silent?: boolean }) => void;
  unlockAudio: () => Promise<boolean>;
  flushHeldQueue: () => boolean;
  retryLastFailed: () => boolean;
  requestHint: (question: string) => void;
  micEnabled: boolean;
  turnState: string;
  canInput: boolean;
  inputText: string;
  referenceHint: string;
  lastQuestion: string;
}

/** 用户动作域：提交、barge、打断候选、静默/回采回调、手动操作与语音状态拼装。 */
export function useInterviewRoomActions(deps: InterviewRoomActionsDeps) {
  const depsRef = useRef(deps);
  depsRef.current = deps;

  const { send, stopTTS, unlockAudio, flushHeldQueue, retryLastFailed } = deps;

  const submitUserMessageRef = useRef<(text: string, pcm?: string, sampleRate?: number) => void>(
    () => {},
  );

  const submitUserMessage = useCallback(
    (text: string, pcmBase64 = "", sampleRate = 16000) => {
      const d = depsRef.current;
      const trimmed = text.trim();
      if (!trimmed && !pcmBase64) return;
      const imageBase64 = d.videoRef.current?.captureFrame() ?? undefined;
      const payload = {
        text: trimmed,
        face_analysis: d.faceRef.current,
        image_base64: imageBase64,
      };
      if (pcmBase64) {
        const sr =
          Number.isFinite(sampleRate) && sampleRate >= 8000 && sampleRate <= 96000
            ? Math.round(sampleRate)
            : 16000;
        send({ type: "user_turn_end", pcm: pcmBase64, sample_rate: sr, ...payload });
      } else {
        send({ type: "user_text", ...payload });
      }
      d.partialTextRef.current = "";
    },
    [send],
  );

  useEffect(() => {
    submitUserMessageRef.current = submitUserMessage;
  }, [submitUserMessage]);

  const onSilenceStable = useCallback((pcm: string, partial: string, sampleRate = 16000) => {
    const d = depsRef.current;
    if (d.turnStateRef.current !== "USER_SPEAKING") return;
    const cleaned = (partial || "").trim();
    if (cleaned && isLikelyEchoOfAssistant(cleaned, d.lastAssistantTextRef.current)) {
      console.warn("丢弃疑似回采的 STT 文本");
      return;
    }
    d.partialTextRef.current = partial;
    submitUserMessageRef.current(partial, pcm, sampleRate);
  }, []);

  const onPartialStable = useCallback((text: string) => {
    const d = depsRef.current;
    if (d.turnStateRef.current !== "USER_SPEAKING") return;
    if (isLikelyEchoOfAssistant(text, d.lastAssistantTextRef.current)) return;
    d.partialTextRef.current = text;
    const now = Date.now();
    if (now - d.sttThrottleRef.current >= 500) {
      d.sttThrottleRef.current = now;
      d.sendRef.current({ type: "stt_text", text });
    }
    d.bumpSilenceTimerRef.current();
  }, []);

  const onSpeechActivity = useCallback(() => {
    const d = depsRef.current;
    if (d.turnStateRef.current !== "USER_SPEAKING") return;
    d.bumpSilenceTimerRef.current();
  }, []);

  const onBargeCandidate = useCallback(() => {
    const d = depsRef.current;
    if (d.turnStateRef.current !== "AI_SPEAKING" || d.bargeLockRef.current) return;
    if (Date.now() - d.aiSpeakStartedAtRef.current < 900) return;
    d.bargeLockRef.current = true;
    d.expectedPlaybackGenRef.current =
      Math.max(d.expectedPlaybackGenRef.current, d.playbackGenRef.current) + 1;
    d.playbackGenRef.current = d.expectedPlaybackGenRef.current;
    d.localBargeStopRef.current = true;
    d.lastPlaybackDoneGenRef.current = null;
    stopTTS();
    d.seedCaptureFromRingRef.current();
    d.sendRef.current({ type: "barge_in" });
    window.setTimeout(() => {
      d.bargeLockRef.current = false;
    }, 2500);
  }, [stopTTS]);

  const handleFaceAnalysis = useCallback(
    (analysis: FaceAnalysis) => {
      depsRef.current.faceRef.current = analysis;
      send({ type: "vision_update", face_analysis: analysis });
    },
    [send],
  );

  const handleEnableAudio = async () => {
    const ok = await unlockAudio();
    if (ok) {
      depsRef.current.setAudioBlocked(false);
      toast.success("声音已启用");
      if (!flushHeldQueue()) {
        retryLastFailed();
      }
    } else {
      toast.error("无法启用声音，请检查浏览器权限");
    }
  };

  const handleSend = () => {
    const d = depsRef.current;
    if (!d.canInput) return;
    if (d.inputText.trim()) {
      submitUserMessage(d.inputText.trim());
      d.setInputText("");
    } else if (d.recorderRef.current.isRecording) {
      d.recorderRef.current.flush();
    }
  };

  const handleFinish = () => {
    const d = depsRef.current;
    if (d.finishingRef.current || d.navigatingRef.current) return;
    d.finishingRef.current = true;
    d.setFinishingUi(true);
    d.stopTTS();
    d.send({ type: "tts_playback_done", generation: d.playbackGenRef.current });
    const ok = d.send({ type: "request_finish" });
    if (!ok) {
      d.finishingRef.current = false;
      d.setFinishingUi(false);
      toast.error("连接已断开，无法结束面试，请重试");
      return;
    }
    toast.success("面试官正在做收尾评价…");
  };

  const handleOutlineChange = (checked: boolean) => {
    const d = depsRef.current;
    d.setShowOutline(checked);
    d.showOutlineRef.current = checked;
    // 关闭仅隐藏，保留已生成的参考答案；重新打开时直接展示缓存
    if (!checked) return;
    if (!d.referenceHint && d.lastQuestion) d.requestHint(d.lastQuestion);
  };

  /** 在 return 组装时调用，确保读到本次渲染已同步的 recorder 状态。 */
  const buildVoiceStatus = () => {
    const d = depsRef.current;
    const rec = d.recorderRef.current;
    return rec.micError
      ? `错误：${rec.micError}`
      : !d.micEnabled
        ? "等待你的回合"
        : d.turnState === "AI_SPEAKING"
          ? rec.partialText
            ? `可打断 · 识别「${rec.partialText}」`
            : "面试官发言中 · 开口即可打断（影响礼貌分）"
          : rec.partialText
            ? `识别中「${rec.partialText}」`
            : rec.isRecording
              ? "正在聆听，说完停顿约 1 秒自动发送；也可点发送"
              : "麦克风启动中…";
  };

  return {
    submitUserMessage,
    onSilenceStable,
    onPartialStable,
    onSpeechActivity,
    onBargeCandidate,
    handleFaceAnalysis,
    handleEnableAudio,
    handleSend,
    handleFinish,
    handleOutlineChange,
    buildVoiceStatus,
  };
}
