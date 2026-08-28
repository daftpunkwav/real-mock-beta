"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import { useRouter } from "next/navigation";
import type { ChatMessage, ClientEvent, FaceAnalysis } from "@/types";
import { useAudioRecorder } from "@/features/media/useAudioRecorder";
import { useTTSPlayer } from "@/features/media/useTTSPlayer";
import { toast } from "@/components/Toast";
import { useInterviewWS } from "./useInterviewWS";
import { useInterviewRoomBootstrap } from "./useInterviewRoomBootstrap";
import { isLikelyEchoOfAssistant } from "../echo";
import type { VideoPanelHandle } from "../components/VideoPanel";

export const TURN_LABELS: Record<string, string> = {
  AI_SPEAKING: "面试官发言中",
  USER_SPEAKING: "请你回答",
  PROCESSING: "思考中",
  IDLE: "待命",
};

/** 面试房间运行时：话轮、WS、录音、TTS、提纲。页面只负责组装。 */
export function useInterviewRoom(sessionId: number) {
  const router = useRouter();
  const {
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
  } = useInterviewRoomBootstrap(sessionId);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streamingText, setStreamingText] = useState("");
  const [currentPhase, setCurrentPhase] = useState("");
  const [emotion, setEmotion] = useState("neutral");
  const [aiSpeaking, setAiSpeaking] = useState(false);
  const [audioLevel, setAudioLevel] = useState(0);
  const [audioBlocked, setAudioBlocked] = useState(false);
  const [sttFailUntil, setSttFailUntil] = useState(0);
  const [showOutline, setShowOutline] = useState(true);
  const [tokenUsage, setTokenUsage] = useState(0);
  const [inputText, setInputText] = useState("");
  const [referenceHint, setReferenceHint] = useState("");
  const [hintLoading, setHintLoading] = useState(false);
  const [lastQuestion, setLastQuestion] = useState("");
  const [finishingUi, setFinishingUi] = useState(false);
  const hintTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const videoRef = useRef<VideoPanelHandle>(null);
  const faceRef = useRef<FaceAnalysis>({});
  const partialTextRef = useRef("");
  const silenceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const bumpSilenceTimerRef = useRef<() => void>(() => {});
  const turnStateRef = useRef<string>("IDLE");
  const bargeLockRef = useRef(false);
  const aiSpeakStartedAtRef = useRef(0);
  const lastAssistantTextRef = useRef("");
  const clearCaptureBuffersRef = useRef<() => void>(() => {});
  const seedCaptureFromRingRef = useRef<() => void>(() => {});
  const sttThrottleRef = useRef(0);
  const reportNavTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const finishingRef = useRef(false);
  const navigatingRef = useRef(false);
  const playbackGenRef = useRef(0);
  const expectedPlaybackGenRef = useRef(0);
  const localBargeStopRef = useRef(false);
  const lastPlaybackDoneGenRef = useRef<number | null>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const showOutlineRef = useRef(showOutline);
  const sendRef = useRef<(p: ClientEvent) => boolean>(() => false);

  const {
    connected,
    everConnected,
    turnState,
    connectionState,
    reconnectAttempt,
    send,
    on,
    retryNow,
  } = useInterviewWS(sessionIdValid ? sessionId : 0);
  const {
    playBase64Mp3,
    setOnSpeakingChange,
    setOnAudioLevel,
    setOnPlaybackBlocked,
    setOnPlaybackDone,
    unlockAudio,
    retryLastFailed,
    flushHeldQueue,
    stop: stopTTS,
    audioUnlocked,
  } = useTTSPlayer();

  useEffect(() => {
    setStreamingText("");
    setFinishingUi(false);
    setTokenUsage(0);
    setInputText("");
    setReferenceHint("");
    setHintLoading(false);
    setLastQuestion("");
    setMessages([]);
    setCurrentPhase("");
    finishingRef.current = false;
    navigatingRef.current = false;
    playbackGenRef.current = 0;
    expectedPlaybackGenRef.current = 0;
    lastPlaybackDoneGenRef.current = null;
    lastAssistantTextRef.current = "";
  }, [sessionId]);

  useEffect(() => {
    if (historySessionId !== sessionId) return;
    if (historyMessages.length > 0) {
      setMessages(historyMessages);
      const chars = historyMessages
        .filter((m) => m.role === "assistant")
        .reduce((n, m) => n + m.content.length, 0);
      setTokenUsage(chars);
    }
    if (restoredPhase) setCurrentPhase(restoredPhase);
    if (lastAssistantContent) {
      lastAssistantTextRef.current = lastAssistantContent;
      setLastQuestion(lastAssistantContent);
    }
  }, [historySessionId, sessionId, historyMessages, restoredPhase, lastAssistantContent]);

  useEffect(() => {
    showOutlineRef.current = showOutline;
  }, [showOutline]);
  useEffect(() => {
    sendRef.current = send;
  }, [send]);

  useEffect(() => {
    return () => {
      if (reportNavTimerRef.current) clearTimeout(reportNavTimerRef.current);
      stopTTS();
    };
  }, [stopTTS]);

  useEffect(() => {
    setOnSpeakingChange(setAiSpeaking);
    setOnAudioLevel(setAudioLevel);
    setOnPlaybackBlocked(setAudioBlocked);
    setOnPlaybackDone(() => {
      const g = playbackGenRef.current;
      if (lastPlaybackDoneGenRef.current === g) return;
      lastPlaybackDoneGenRef.current = g;
      sendRef.current({
        type: "tts_playback_done",
        generation: g,
      });
    });
  }, [setOnSpeakingChange, setOnAudioLevel, setOnPlaybackBlocked, setOnPlaybackDone]);

  const submitUserMessageRef = useRef<(text: string, pcm?: string, sampleRate?: number) => void>(() => {});

  const submitUserMessage = useCallback((text: string, pcmBase64 = "", sampleRate = 16000) => {
    const trimmed = text.trim();
    if (!trimmed && !pcmBase64) return;
    const imageBase64 = videoRef.current?.captureFrame() ?? undefined;
    const payload = {
      text: trimmed,
      face_analysis: faceRef.current,
      image_base64: imageBase64,
    };
    if (pcmBase64) {
      const sr = Number.isFinite(sampleRate) && sampleRate >= 8000 && sampleRate <= 96000
        ? Math.round(sampleRate)
        : 16000;
      send({ type: "user_turn_end", pcm: pcmBase64, sample_rate: sr, ...payload });
    } else {
      send({ type: "user_text", ...payload });
    }
    partialTextRef.current = "";
  }, [send]);

  useEffect(() => {
    submitUserMessageRef.current = submitUserMessage;
  }, [submitUserMessage]);

  const onSilenceStable = useCallback((pcm: string, partial: string, sampleRate = 16000) => {
    if (turnStateRef.current !== "USER_SPEAKING") return;
    const cleaned = (partial || "").trim();
    if (cleaned && isLikelyEchoOfAssistant(cleaned, lastAssistantTextRef.current)) {
      console.warn("丢弃疑似回采的 STT 文本");
      return;
    }
    partialTextRef.current = partial;
    submitUserMessageRef.current(partial, pcm, sampleRate);
  }, []);

  const onPartialStable = useCallback((text: string) => {
    if (turnStateRef.current !== "USER_SPEAKING") return;
    if (isLikelyEchoOfAssistant(text, lastAssistantTextRef.current)) return;
    partialTextRef.current = text;
    const now = Date.now();
    if (now - sttThrottleRef.current >= 500) {
      sttThrottleRef.current = now;
      sendRef.current({ type: "stt_text", text });
    }
    bumpSilenceTimerRef.current();
  }, []);

  const onSpeechActivity = useCallback(() => {
    if (turnStateRef.current !== "USER_SPEAKING") return;
    bumpSilenceTimerRef.current();
  }, []);

  const onBargeCandidate = useCallback(() => {
    if (turnStateRef.current !== "AI_SPEAKING" || bargeLockRef.current) return;
    if (Date.now() - aiSpeakStartedAtRef.current < 900) return;
    bargeLockRef.current = true;
    expectedPlaybackGenRef.current =
      Math.max(expectedPlaybackGenRef.current, playbackGenRef.current) + 1;
    playbackGenRef.current = expectedPlaybackGenRef.current;
    localBargeStopRef.current = true;
    lastPlaybackDoneGenRef.current = null;
    stopTTS();
    seedCaptureFromRingRef.current();
    sendRef.current({ type: "barge_in" });
    window.setTimeout(() => {
      bargeLockRef.current = false;
    }, 2500);
  }, [stopTTS]);

  const clearHintTimeout = useCallback(() => {
    if (hintTimeoutRef.current) {
      clearTimeout(hintTimeoutRef.current);
      hintTimeoutRef.current = null;
    }
  }, []);

  const requestHint = useCallback((question: string) => {
    if (!showOutlineRef.current || !question.trim()) return;
    setHintLoading(true);
    setReferenceHint("");
    setLastQuestion(question);
    clearHintTimeout();
    hintTimeoutRef.current = setTimeout(() => {
      setHintLoading(false);
      setReferenceHint((prev) =>
        prev.trim()
          ? prev
          : "生成较慢或已超时。可先按 STAR：情境 → 任务 → 行动 → 结果（尽量量化）自行组织。",
      );
    }, 25_000);
    sendRef.current({ type: "request_hint", question });
  }, [clearHintTimeout]);

  useEffect(() => () => clearHintTimeout(), [clearHintTimeout]);

  const micEnabled =
    connected &&
    (turnState === "USER_SPEAKING" || turnState === "AI_SPEAKING") &&
    !finishingUi;
  const captureEnabled = turnState === "USER_SPEAKING" && !finishingUi;
  const canInput = turnState === "USER_SPEAKING" && !finishingUi;

  useEffect(() => {
    turnStateRef.current = turnState;
    if (turnState === "AI_SPEAKING") {
      aiSpeakStartedAtRef.current = Date.now();
    }
  }, [turnState]);

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
      }, silenceNudgeMs);
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
  }, [micEnabled, sttFailUntil, silenceNudgeMs]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingText]);

  useEffect(() => {
    const finishOnceAndNavigate = async () => {
      if (navigatingRef.current) return;
      navigatingRef.current = true;
      finishingRef.current = true;
      setFinishingUi(true);
      stopTTS();
      sendRef.current({
        type: "tts_playback_done",
        generation: playbackGenRef.current,
      });
      if (reportNavTimerRef.current) clearTimeout(reportNavTimerRef.current);
      router.push(`/report/${sessionId}`);
    };

    on("assistant_token", (msg) => setStreamingText((prev) => prev + msg.token));
    on("assistant_done", (msg) => {
      setMessages((prev) => [...prev, { role: "assistant", content: msg.content }]);
      setStreamingText("");
      setCurrentPhase(msg.phase);
      setEmotion(msg.emotion || "neutral");
      setTokenUsage((t) => t + msg.content.length);
      lastAssistantTextRef.current = msg.content || "";
      if (typeof msg.playback_generation === "number") {
        playbackGenRef.current = msg.playback_generation;
        expectedPlaybackGenRef.current = Math.max(
          expectedPlaybackGenRef.current,
          msg.playback_generation,
        );
      }
      if (!msg.is_complete) {
        requestHint(msg.content);
      }
      if (msg.is_complete) {
        void finishOnceAndNavigate();
      }
    });
    on("stt_final", (msg) => {
      if (msg.text) setMessages((prev) => [...prev, { role: "user", content: msg.text }]);
    });
    on("tts_audio", (msg) => {
      const gen = msg.playback_generation;
      if (typeof gen === "number") {
        if (gen < expectedPlaybackGenRef.current) {
          return;
        }
        playbackGenRef.current = gen;
        expectedPlaybackGenRef.current = Math.max(expectedPlaybackGenRef.current, gen);
      }
      playBase64Mp3(msg.data);
    });
    on("tts_failed", (msg) => {
      setAudioBlocked(true);
      toast.error(msg.message || "语音播放失败");
      setMessages((prev) => [...prev, { role: "assistant", content: `⚠️ ${msg.message}` }]);
      sendRef.current({
        type: "tts_playback_done",
        generation: playbackGenRef.current,
      });
    });
    on("tts_interrupted", (msg) => {
      if (typeof msg.playback_generation === "number") {
        expectedPlaybackGenRef.current = Math.max(
          expectedPlaybackGenRef.current,
          msg.playback_generation,
        );
        playbackGenRef.current = expectedPlaybackGenRef.current;
      }
      if (localBargeStopRef.current) {
        localBargeStopRef.current = false;
        stopTTS({ silent: true });
      } else {
        expectedPlaybackGenRef.current =
          Math.max(expectedPlaybackGenRef.current, playbackGenRef.current) + 1;
        playbackGenRef.current = expectedPlaybackGenRef.current;
        lastPlaybackDoneGenRef.current = null;
        stopTTS();
      }
      const n = msg.candidate_interrupts;
      toast.info(
        typeof n === "number"
          ? `已打断发言（累计 ${n} 次，会影响礼貌评分）`
          : "已打断面试官发言",
      );
    });
    on("silence_nudge", (msg) => {
      setMessages((prev) => [...prev, { role: "assistant", content: `[追问] ${msg.content}` }]);
    });
    on("reference_hint_loading", () => setHintLoading(true));
    on("reference_hint", (msg) => {
      const cleaned = msg.content
        .replace(/<think>[\s\S]*?<\/think>/gi, "")
        .replace(/<thinking>[\s\S]*?<\/thinking>/gi, "")
        .trim();
      clearHintTimeout();
      setReferenceHint(cleaned);
      setLastQuestion(msg.question || "");
      setHintLoading(false);
    });
    on("phase_changed", (msg) => {
      if (msg.phase) setCurrentPhase(msg.phase);
    });
    on("interview_complete", () => {
      void finishOnceAndNavigate();
    });
    on("info", (msg) => {
      if (msg.message) toast.info(String(msg.message));
    });
    on("error", (msg) => {
      setMessages((prev) => [...prev, { role: "assistant", content: `⚠️ ${msg.message}` }]);
      if (msg.message.includes("收尾") || msg.message.includes("结束面试")) {
        finishingRef.current = false;
        setFinishingUi(false);
      }
      if (msg.message.includes("未能识别") || msg.message.includes("语音合成失败")) {
        setSttFailUntil(Date.now() + 18_000);
        if (msg.message.includes("语音合成") || msg.message.includes("合成失败")) {
          setAudioBlocked(true);
        }
        if (msg.message.includes("未能识别")) {
          toast.error("识别失败：可改用下方文字输入继续作答");
        }
      }
    });
  }, [on, playBase64Mp3, router, sessionId, requestHint, stopTTS, clearHintTimeout]);

  const { flush, clearCaptureBuffers, seedCaptureFromRing, isRecording, partialText, micError } =
    useAudioRecorder(
      micEnabled,
      onSilenceStable,
      onPartialStable,
      onSpeechActivity,
      onBargeCandidate,
      captureEnabled,
    );

  useEffect(() => {
    clearCaptureBuffersRef.current = clearCaptureBuffers;
  }, [clearCaptureBuffers]);

  useEffect(() => {
    seedCaptureFromRingRef.current = seedCaptureFromRing;
  }, [seedCaptureFromRing]);

  const handleFaceAnalysis = useCallback((analysis: FaceAnalysis) => {
    faceRef.current = analysis;
    send({ type: "vision_update", face_analysis: analysis });
  }, [send]);

  const canSend = canInput && (Boolean(inputText.trim()) || isRecording);

  const handleEnableAudio = async () => {
    const ok = await unlockAudio();
    if (ok) {
      setAudioBlocked(false);
      toast.success("声音已启用");
      if (!flushHeldQueue()) {
        retryLastFailed();
      }
    } else {
      toast.error("无法启用声音，请检查浏览器权限");
    }
  };

  const handleSend = () => {
    if (!canInput) return;
    if (inputText.trim()) {
      submitUserMessage(inputText.trim());
      setInputText("");
    } else if (isRecording) {
      flush();
    }
  };

  const handleFinish = () => {
    if (finishingRef.current || navigatingRef.current) return;
    finishingRef.current = true;
    setFinishingUi(true);
    stopTTS();
    send({
      type: "tts_playback_done",
      generation: playbackGenRef.current,
    });
    const ok = send({ type: "request_finish" });
    if (!ok) {
      finishingRef.current = false;
      setFinishingUi(false);
      toast.error("连接已断开，无法结束面试，请重试");
      return;
    }
    toast.success("面试官正在做收尾评价…");
  };

  const handleOutlineChange = (checked: boolean) => {
    setShowOutline(checked);
    showOutlineRef.current = checked;
    if (!checked) setReferenceHint("");
    else if (lastQuestion) requestHint(lastQuestion);
  };

  const voiceStatus = micError
    ? `错误：${micError}`
    : !micEnabled
      ? "等待你的回合"
      : turnState === "AI_SPEAKING"
        ? partialText
          ? `可打断 · 识别「${partialText}」`
          : "面试官发言中 · 开口即可打断（影响礼貌分）"
        : partialText
          ? `识别中「${partialText}」`
          : isRecording
            ? "正在聆听，说完停顿约 1 秒自动发送；也可点发送"
            : "麦克风启动中…";

  const goSetup = useCallback(() => {
    router.push("/interview");
  }, [router]);

  return {
    sessionId,
    sessionIdValid,
    tokenMissing,
    goSetup,
    sessionMeta,
    sessionStatus,
    phaseLabels,
    currentPhase,
    turnState,
    connected,
    everConnected,
    connectionState,
    reconnectAttempt,
    retryNow,
    messages,
    streamingText,
    chatEndRef,
    inputText,
    setInputText,
    canInput,
    canSend,
    handleSend,
    handleFinish,
    finishingUi,
    videoRef,
    isRecording,
    voiceStatus,
    handleFaceAnalysis,
    emotion,
    aiSpeaking,
    audioLevel,
    audioUnlocked,
    audioBlocked,
    handleEnableAudio,
    showOutline,
    handleOutlineChange,
    lastQuestion,
    requestHint,
    hintLoading,
    referenceHint,
    tokenUsage,
  };
}

export type InterviewRoomModel = ReturnType<typeof useInterviewRoom>;
