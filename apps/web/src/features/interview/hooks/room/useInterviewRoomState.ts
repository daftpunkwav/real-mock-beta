"use client";

import { useEffect, useRef, useState } from "react";
import type { ChatMessage } from "@/lib/api/contract";
import type { ClientEvent, FaceAnalysis } from "@/types";
import type { VideoPanelHandle } from "../../components/VideoPanel";

export interface InterviewRoomStateDeps {
  sessionId: number;
  historySessionId: number | null;
  historyMessages: ChatMessage[];
  restoredPhase: string;
  lastAssistantContent: string;
  turnState: string;
  send: (p: ClientEvent) => boolean;
}

/** 房间状态域：页面/子 hook 共享的全部 state 与 ref，含 sessionId 切换重置与历史恢复。 */
export function useInterviewRoomState(deps: InterviewRoomStateDeps) {
  const {
    sessionId,
    historySessionId,
    historyMessages,
    restoredPhase,
    lastAssistantContent,
    turnState,
    send,
  } = deps;

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

  /** sessionId 切换：state/ref 重置（原样保留） */
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

  /** 历史恢复：切回已加载过的会话时回放消息与最后一句面试官内容 */
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
    turnStateRef.current = turnState;
    if (turnState === "AI_SPEAKING") {
      aiSpeakStartedAtRef.current = Date.now();
    }
  }, [turnState]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingText]);

  return {
    state: {
      messages,
      streamingText,
      currentPhase,
      emotion,
      aiSpeaking,
      audioLevel,
      audioBlocked,
      sttFailUntil,
      showOutline,
      tokenUsage,
      inputText,
      referenceHint,
      hintLoading,
      lastQuestion,
      finishingUi,
      lastSources,
    },
    set: {
      setMessages,
      setStreamingText,
      setCurrentPhase,
      setEmotion,
      setAiSpeaking,
      setAudioLevel,
      setAudioBlocked,
      setSttFailUntil,
      setShowOutline,
      setTokenUsage,
      setInputText,
      setReferenceHint,
      setHintLoading,
      setLastQuestion,
      setFinishingUi,
      setLastSources,
    },
    refs: {
      hintTimeoutRef,
      videoRef,
      faceRef,
      partialTextRef,
      bumpSilenceTimerRef,
      turnStateRef,
      bargeLockRef,
      aiSpeakStartedAtRef,
      lastAssistantTextRef,
      clearCaptureBuffersRef,
      seedCaptureFromRingRef,
      sttThrottleRef,
      finishingRef,
      navigatingRef,
      playbackGenRef,
      expectedPlaybackGenRef,
      localBargeStopRef,
      lastPlaybackDoneGenRef,
      waitMsRef,
      chatEndRef,
      showOutlineRef,
      sendRef,
    },
  };
}
