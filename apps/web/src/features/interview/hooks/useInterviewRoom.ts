"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import { useRouter } from "next/navigation";
import type { ChatMessage, ClientEvent, FaceAnalysis } from "@/types";
import { useAudioRecorder } from "@/features/media/useAudioRecorder";
import { useTTSPlayer } from "@/features/media/useTTSPlayer";
import { useInterviewWS } from "./useInterviewWS";
import { useInterviewRoomBootstrap } from "./useInterviewRoomBootstrap";
import { useInterviewRoomEvents } from "./useInterviewRoomEvents";
import { useInterviewRoomActions, type RecorderBridge } from "./useInterviewRoomActions";
import { useInterviewRoomSilenceTimer } from "./useInterviewRoomSilenceTimer";
import type { VideoPanelHandle } from "../components/VideoPanel";

/** 面试房间运行时：bootstrap/WS/TTS/recorder 接线 + 事件与动作组合。页面只负责组装。 */
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
  const [lastSources, setLastSources] = useState<string[]>([]);

  const hintTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const videoRef = useRef<VideoPanelHandle>(null);
  const faceRef = useRef<FaceAnalysis>({});
  const partialTextRef = useRef("");
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
  /** 服务端下发的预计作答毫秒数（turn 协议 wait_seconds；0=未提供用默认） */
  const waitMsRef = useRef(0);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const showOutlineRef = useRef(showOutline);
  const sendRef = useRef<(p: ClientEvent) => boolean>(() => false);

  const { connected, everConnected, turnState, connectionState, reconnectAttempt, send, on, retryNow } =
    useInterviewWS(sessionIdValid ? sessionId : 0);

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
    setLastSources([]);
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
    sendRef.current = send;
  }, [showOutline, send]);

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
      sendRef.current({ type: "tts_playback_done", generation: g });
    });
  }, [setOnSpeakingChange, setOnAudioLevel, setOnPlaybackBlocked, setOnPlaybackDone]);

  const micEnabled =
    connected && (turnState === "USER_SPEAKING" || turnState === "AI_SPEAKING") && !finishingUi;
  const captureEnabled = turnState === "USER_SPEAKING" && !finishingUi;
  const canInput = turnState === "USER_SPEAKING" && !finishingUi;

  useEffect(() => {
    turnStateRef.current = turnState;
    if (turnState === "AI_SPEAKING") {
      aiSpeakStartedAtRef.current = Date.now();
    }
  }, [turnState]);

  useInterviewRoomSilenceTimer({ micEnabled, sttFailUntil, silenceNudgeMs, waitMsRef, sendRef, bumpSilenceTimerRef });

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingText]);

  const { requestHint } = useInterviewRoomEvents({
    setStreamingText,
    setMessages,
    setCurrentPhase,
    setEmotion,
    setTokenUsage,
    setAudioBlocked,
    setHintLoading,
    setReferenceHint,
    setLastQuestion,
    setFinishingUi,
    setSttFailUntil,
    setLastSources,
    playbackGenRef,
    expectedPlaybackGenRef,
    lastPlaybackDoneGenRef,
    localBargeStopRef,
    waitMsRef,
    lastAssistantTextRef,
    hintTimeoutRef,
    reportNavTimerRef,
    finishingRef,
    navigatingRef,
    bumpSilenceTimerRef,
    sendRef,
    showOutlineRef,
    on,
    playBase64Mp3,
    stopTTS,
    router,
    sessionId,
  });

  const recorderRef = useRef<RecorderBridge>({ flush: () => {}, isRecording: false, partialText: "", micError: "" });

  const actions = useInterviewRoomActions({
    setInputText,
    setAudioBlocked,
    setShowOutline,
    setFinishingUi,
    turnStateRef,
    bargeLockRef,
    aiSpeakStartedAtRef,
    lastAssistantTextRef,
    partialTextRef,
    sttThrottleRef,
    finishingRef,
    navigatingRef,
    playbackGenRef,
    expectedPlaybackGenRef,
    localBargeStopRef,
    lastPlaybackDoneGenRef,
    showOutlineRef,
    videoRef,
    faceRef,
    seedCaptureFromRingRef,
    bumpSilenceTimerRef,
    sendRef,
    recorderRef,
    send,
    stopTTS,
    unlockAudio,
    flushHeldQueue,
    retryLastFailed,
    requestHint,
    micEnabled,
    turnState,
    canInput,
    inputText,
    referenceHint,
    lastQuestion,
  });

  const { flush, clearCaptureBuffers, seedCaptureFromRing, isRecording, partialText, micError } =
    useAudioRecorder(micEnabled, actions.onSilenceStable, actions.onPartialStable, actions.onSpeechActivity, actions.onBargeCandidate, captureEnabled);

  recorderRef.current = { flush, isRecording, partialText, micError };

  useEffect(() => {
    clearCaptureBuffersRef.current = clearCaptureBuffers;
    seedCaptureFromRingRef.current = seedCaptureFromRing;
  }, [clearCaptureBuffers, seedCaptureFromRing]);

  const canSend = canInput && (Boolean(inputText.trim()) || isRecording);
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
    handleSend: actions.handleSend,
    handleFinish: actions.handleFinish,
    finishingUi,
    videoRef,
    isRecording,
    voiceStatus: actions.buildVoiceStatus(),
    handleFaceAnalysis: actions.handleFaceAnalysis,
    emotion,
    aiSpeaking,
    audioLevel,
    audioUnlocked,
    audioBlocked,
    handleEnableAudio: actions.handleEnableAudio,
    showOutline,
    handleOutlineChange: actions.handleOutlineChange,
    lastQuestion,
    requestHint,
    hintLoading,
    referenceHint,
    lastSources,
    tokenUsage,
  };
}

export type InterviewRoomModel = ReturnType<typeof useInterviewRoom>;
