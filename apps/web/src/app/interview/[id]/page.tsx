"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import type { ChatMessage, ClientEvent, FaceAnalysis } from "@/types";
import { VideoPanel, type VideoPanelHandle } from "@/components/interview/VideoPanel";
import { TalkingHeadAvatar } from "@/features/avatar/TalkingHeadAvatar";
import { useInterviewWS } from "@/features/media/useInterviewWS";
import { useAudioRecorder } from "@/features/media/useAudioRecorder";
import { useTTSPlayer } from "@/features/media/useTTSPlayer";
import { interviewService as api } from "@/lib/api/interviewService";
import { PHASE_LABELS } from "@/config/phases";
import { toast } from "@/components/Toast";
import { Flag, Loader2, Send, WifiOff, Radio, Volume2, AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils";
/** 去掉标点空白，用于回采相似度判断。 */
function normalizeEchoText(s: string): string {
  return s
    .replace(/[\s\*\#`~，。！？、,.!?;:：；""''\-—…（）()【】\[\]]/g, "")
    .toLowerCase();
}

/** 候选人文本是否高度像上一句面试官发言（扬声器回采）。 */
function isLikelyEchoOfAssistant(userText: string, assistantText: string): boolean {
  const u = normalizeEchoText(userText);
  const a = normalizeEchoText(assistantText);
  if (u.length < 12 || a.length < 12) return false;
  if (u.includes(a.slice(0, Math.min(40, a.length))) || a.includes(u.slice(0, Math.min(40, u.length)))) {
    return true;
  }
  // 简易字符重叠率
  const window = Math.min(u.length, a.length, 80);
  let hit = 0;
  for (let i = 0; i < window; i++) {
    if (u[i] === a[i]) hit += 1;
  }
  if (hit / window >= 0.55) return true;
  // 滑动：用户串是否大量出现在助理串中
  const probe = u.slice(0, Math.min(24, u.length));
  if (probe.length >= 12 && a.includes(probe)) return true;
  return false;
}

export default function InterviewRoomPage() {
  const params = useParams();
  const router = useRouter();
  const sessionId = Number(params.id);
  const sessionIdValid = Number.isFinite(sessionId) && sessionId > 0;
  const [tokenMissing, setTokenMissing] = useState(false);
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
  // 静默追问触发毫秒数：从后端配置读取，默认 25s
  const [silenceNudgeMs, setSilenceNudgeMs] = useState(25000);
  const hintTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [sessionMeta, setSessionMeta] = useState({
    avatar_id: "professional_male",
    scene_id: "meeting_room",
    workflow_type: "technical",
  });
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
  // stt_text 上行节流：最多 2 次/秒（500ms 最小间隔），避免频繁刷服务端缓冲
  const sttThrottleRef = useRef(0);
  const reportNavTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const finishingRef = useRef(false);
  const navigatingRef = useRef(false);
  const playbackGenRef = useRef(0);
  /** 客户端期望的播放世代；低于此值的 tts_audio 丢弃（打断后防鬼畜） */
  const expectedPlaybackGenRef = useRef(0);
  /** 本地 barge 已 stop 并上报过 done，tts_interrupted 时静默再停 */
  const localBargeStopRef = useRef(false);
  /** playback_done 按 generation 去重 */
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
  } = useInterviewWS(sessionId);
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
    let cancelled = false;
    api
      .getSession(sessionId)
      .then(() => {
        if (!cancelled) setTokenMissing(false);
      })
      .catch((e) => {
        if (cancelled) return;
        const status = e && typeof e === "object" && "status" in e ? Number(e.status) : 0;
        setTokenMissing(status === 403 || status === 401);
      });
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

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

  useEffect(() => {
    api.getSession(sessionId).then((s) => {
      setSessionMeta({
        avatar_id: s.avatar_id || "professional_male",
        scene_id: s.scene_id || "meeting_room",
        workflow_type: s.workflow_type,
      });
      void import("@/features/avatar/TalkingHeadAvatar").then((m) => {
        m.prefetchAvatarGlb(s.avatar_id || "professional_male");
      });
    }).catch(() => {});
    // 读取后端 silence_nudge_seconds，对齐前端静默追问计时器
    api.getOptions().then((opts) => {
      if (opts.silence_nudge_seconds) {
        setSilenceNudgeMs(opts.silence_nudge_seconds * 1000);
      }
    }).catch(() => {});
  }, [sessionId]);

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
    // 仅候选人话轮可提交；AI 发言期的回采一律丢弃
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
    // 节流：500ms 内只发一次 stt_text，避免高频刷服务端
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
    // AI 刚开口的宽限期：扬声器回声最强，禁止打断
    if (Date.now() - aiSpeakStartedAtRef.current < 900) return;
    bargeLockRef.current = true;
    // 提升期望世代，丢弃旧 TTS；保留打断前环形 PCM
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
    // 客户端兜底：后端超时/早退/丢包时避免永久转圈
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

  // 全双工：AI 说话时也开麦（仅打断能量），PROCESSING 时短暂关麦防误触
  const micEnabled =
    connected &&
    (turnState === "USER_SPEAKING" || turnState === "AI_SPEAKING") &&
    !finishingUi;
  /** 仅候选人话轮才录音/STT；AI 发言期只监听打断，避免回采 */
  const captureEnabled = turnState === "USER_SPEAKING" && !finishingUi;
  const canInput = turnState === "USER_SPEAKING" && !finishingUi;
  useEffect(() => {
    turnStateRef.current = turnState;
    if (turnState === "AI_SPEAKING") {
      aiSpeakStartedAtRef.current = Date.now();
    }
  }, [turnState]);

  // 静默追问：有语音活动（能量或 STT）时重置；开麦后先给宽限期
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
    // 开麦后宽限，避免刚轮到候选人就追问
    const graceMs = Math.min(12_000, Math.max(4_000, Math.floor(silenceNudgeMs * 0.45)));
    silenceTimerRef.current = setTimeout(() => {
      bumpSilenceTimerRef.current();
    }, graceMs);
    return clear;
  }, [micEnabled, sttFailUntil, silenceNudgeMs]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingText]);

  /* 服务端事件的强类型订阅（on() 风格，handler 中 ``msg`` 已按 ``type`` 收窄）。 */
  useEffect(() => {
    const finishOnceAndNavigate = async () => {
      if (navigatingRef.current) return;
      navigatingRef.current = true;
      finishingRef.current = true;
      setFinishingUi(true);
      stopTTS();
      // stopTTS 已通过 onPlaybackDone 回传；再显式发一次防竞态
      sendRef.current({
        type: "tts_playback_done",
        generation: playbackGenRef.current,
      });
      // 不再 await finishInterview：报告由 WS 后台生成，报告页轮询承接
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
      // 收尾完成语不再请求参考提纲
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
        // 低于期望世代的旧包直接丢弃，避免打断后鬼畜重播
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
      // 无音频可播时仍通知服务端，避免一直卡在等播完
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
        // 本地 barge 已 stop 并上报 done，此处只清播放队列
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
      // 重放 unlock 前缓冲 / 自动播放失败的整段
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
    // 打断当前播报，让收尾发言重新排队；并放行服务端播完等待
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

  const turnLabel: Record<string, string> = {
    AI_SPEAKING: "面试官发言中",
    USER_SPEAKING: "请你回答",
    PROCESSING: "思考中",
    IDLE: "待命",
  };

  // 非法会话 ID / 首次连接失败:整页错误;曾连上后断线:保留房间 UI,避免摄像头卸载闪屏
  if (!sessionIdValid) {
    return (
      <div className="h-screen flex flex-col items-center justify-center gap-4 bg-[var(--background)] px-6 text-center">
        <span className="empty-state-icon !bg-[var(--warning-soft)] !text-[var(--warning-ink)]">
          <AlertTriangle size={24} />
        </span>
        <div>
          <p className="text-[16px] font-medium text-ink">无效的会话 ID</p>
          <p className="mt-1.5 max-w-sm text-[13px] text-ink-muted">
            请从「面试配置」页重新开始一场面试。
          </p>
        </div>
        <button
          type="button"
          onClick={() => router.push("/interview")}
          className="btn-primary"
        >
          返回配置页
        </button>
      </div>
    );
  }

  if (tokenMissing) {
    return (
      <div className="h-screen flex flex-col items-center justify-center gap-4 bg-[var(--background)] px-6 text-center">
        <span className="empty-state-icon !bg-[var(--warning-soft)] !text-[var(--warning-ink)]">
          <AlertTriangle size={24} />
        </span>
        <div>
          <p className="text-[16px] font-medium text-ink">会话无效或无权访问</p>
          <p className="mt-1.5 max-w-sm text-[13px] text-ink-muted">
            请从「面试配置」页重新开始一场面试。直接打开历史链接可能缺少能力令牌 Cookie。
          </p>
        </div>
        <button
          type="button"
          onClick={() => router.push("/interview")}
          className="btn-primary"
        >
          返回配置页
        </button>
      </div>
    );
  }

  if (!everConnected && connectionState === "failed") {
    return (
      <div className="h-screen flex flex-col items-center justify-center gap-4 bg-[var(--background)] px-6 text-center">
        <span className="empty-state-icon !bg-[var(--danger-soft)] !text-[var(--danger-ink)]">
          <WifiOff size={24} />
        </span>
        <div>
          <p className="text-[16px] font-medium text-ink">无法连接到面试服务</p>
          <p className="mt-1.5 max-w-sm text-[13px] text-ink-muted">
            已尝试 5 次仍失败,请确认后端已启动(默认 :8081)或检查网络。
          </p>
        </div>
        <div className="mt-1 flex flex-wrap items-center justify-center gap-2.5">
          <button
            type="button"
            onClick={() => retryNow()}
            className="btn-primary"
          >
            重新连接
          </button>
          <button
            type="button"
            onClick={() => router.push("/interview")}
            className="btn-secondary"
          >
            返回配置
          </button>
        </div>
      </div>
    );
  }

  if (!everConnected && !connected) {
    return (
      <div className="h-screen flex flex-col items-center justify-center gap-3 bg-[var(--background)] text-ink-muted">
        <span className="block h-6 w-6 anim-spin rounded-full border-2 border-[var(--primary)] border-t-transparent" />
        <p className="text-[13px]">
          {connectionState === "reconnecting" ? "重新连接中…" : "连接面试服务…"}
        </p>
      </div>
    );
  }

  return (
    <div className="h-screen flex flex-col bg-[var(--background)] text-[var(--foreground)] relative">
      {/* 进房强制手势解锁:跨页导航会丢失自动播放权限 */}
      {!audioUnlocked && (
        <div className="absolute inset-0 z-50 flex items-center justify-center bg-[var(--background)]/85 p-6 backdrop-blur-md">
          <div className="max-w-sm w-full rounded-lg border border-surface-border bg-surface-card px-6 py-8 text-center shadow-lg">
            <span className="icon-badge icon-badge-brand mx-auto mb-3 !h-12 !w-12">
              <Volume2 size={20} strokeWidth={1.75} />
            </span>
            <h2 className="text-[18px] font-semibold tracking-tight text-ink">启用面试官声音</h2>
            <p className="mt-2 text-[13px] leading-relaxed text-ink-muted">
              浏览器禁止无手势自动播放。请点击下方按钮解锁音频,面试官开场白才会出声。
            </p>
            <button
              type="button"
              onClick={() => void handleEnableAudio()}
              className="btn-primary mt-5 w-full !h-10"
            >
              点击启用声音并开始
            </button>
          </div>
        </div>
      )}
      {/* 断线重连条:不卸载主 UI / 摄像头 */}
      {!connected && (
        <div className="absolute inset-x-0 top-0 z-30 flex items-center justify-center gap-2 border-b border-[var(--warning)]/30 bg-[var(--warning-soft)] px-3 py-2 text-[var(--warning-ink)] text-xs font-medium shadow-sm">
          {connectionState === "failed" ? (
            <>
              <WifiOff size={14} />
              连接已断开
              <button
                type="button"
                onClick={() => retryNow()}
                className="ml-2 underline underline-offset-2 hover:opacity-80"
              >
                重试
              </button>
            </>
          ) : (
            <>
              <span className="block h-3 w-3 anim-spin rounded-full border-2 border-current border-t-transparent" />
              连接中断,正在重连…
              {reconnectAttempt > 0 ? `(第 ${reconnectAttempt} 次)` : ""}
            </>
          )}
        </div>
      )}
      {audioBlocked && (
        <div className="absolute inset-x-0 top-0 z-40 flex items-center justify-center gap-2 border-b border-[var(--danger)]/40 bg-[var(--danger-soft)] px-3 py-2 text-[var(--danger-ink)] text-xs font-medium shadow-sm">
          无声?浏览器可能拦截了自动播放
          <button
            type="button"
            onClick={() => void handleEnableAudio()}
            className="ml-1 inline-flex items-center gap-1 underline underline-offset-2 hover:opacity-80"
          >
            <Volume2 size={12} />
            点击启用并重试
          </button>
        </div>
      )}
      <header className="flex shrink-0 items-center justify-between gap-3 border-b border-surface-border bg-surface-card/80 px-3 backdrop-blur-md py-2.5 sm:px-4">
        <div className="flex min-w-0 items-center gap-2 text-sm sm:gap-3">
          <span className="shrink-0 font-medium text-ink">面试 #{sessionId}</span>
          <span className="truncate rounded-full bg-[var(--info-soft)] px-2 py-0.5 text-xs text-[var(--info-ink)]">
            {PHASE_LABELS[currentPhase] || currentPhase || "准备中"}
          </span>
          <span
            className={cn(
              "hidden sm:inline-flex items-center gap-1 rounded-full border border-surface-border px-2 py-0.5 text-xs",
              turnState === "USER_SPEAKING"
                ? "bg-[var(--success-soft)] text-[var(--success-ink)]"
                : turnState === "AI_SPEAKING"
                  ? "bg-[var(--warning-soft)] text-[var(--warning-ink)]"
                  : "bg-surface-alt text-ink-muted",
            )}
          >
            <Radio size={11} className={turnState === "USER_SPEAKING" ? "anim-pulse-dot text-[var(--success)]" : "text-ink-subtle"} />
            {turnLabel[turnState] || turnState}
          </span>
          {audioUnlocked && !audioBlocked && (
            <button
              type="button"
              onClick={() => void handleEnableAudio()}
              className="hidden rounded-full border border-surface-border px-2 py-0.5 text-[11px] text-ink-muted transition-colors hover:bg-surface-alt hover:text-ink md:inline-flex"
            >
              重新解锁声音
            </button>
          )}
          {!audioUnlocked && (
            <button
              type="button"
              onClick={() => void handleEnableAudio()}
              className="hidden rounded-full border border-[var(--warning)]/40 px-2 py-0.5 text-[11px] text-[var(--warning-ink)] transition-colors hover:bg-[var(--warning-soft)] md:inline-flex"
            >
              启用声音
            </button>
          )}
        </div>
        <button
          type="button"
          onClick={handleFinish}
          disabled={finishingUi}
          className="btn-secondary !text-[var(--danger-ink)] hover:!border-[var(--danger)]/40 hover:!bg-[var(--danger-soft)] shrink-0 !h-8 !text-xs"
        >
          {finishingUi ? (
            <>
              <span className="block h-3 w-3 anim-spin rounded-full border-2 border-current border-t-transparent" />
              收尾评价中…
            </>
          ) : (
            <>
              <Flag size={13} />
              结束面试
            </>
          )}
        </button>
      </header>

      <div className="flex-1 grid grid-cols-1 lg:grid-cols-[minmax(280px,1fr)_minmax(0,1.8fr)] gap-2 p-2 min-h-0 overflow-hidden">
        {/* 左侧:摄像头 + 对话 */}
        <div className="grid grid-rows-[minmax(140px,0.9fr)_minmax(180px,1.1fr)] lg:grid-rows-[1.2fr_1fr] gap-2 min-h-0 order-2 lg:order-1">
          <VideoPanel
            ref={videoRef}
            enabled
            variant="dark"
            micActive={isRecording}
            voiceStatus={voiceStatus}
            onFaceAnalysis={handleFaceAnalysis}
          />

          <div className="rounded-lg border border-surface-border bg-surface-card flex flex-col min-h-0">
            <div className="flex-1 overflow-y-auto p-3 space-y-3">
              {messages.length === 0 && !streamingText && (
                <p className="text-xs text-ink-subtle text-center py-6">
                  面试即将开始,请保持镜头对准自己
                </p>
              )}
              {messages.map((m, i) => (
                <ChatBubble key={i} role={m.role} content={m.content} />
              ))}
              {streamingText && (
                <ChatBubble role="assistant" content={streamingText} streaming />
              )}
              <div ref={chatEndRef} />
            </div>

            <div className="border-t border-surface-border p-2 flex gap-2 shrink-0">
              <input
                className="flex-1 rounded-md border border-surface-border bg-surface-card px-3 py-2.5 text-[13px] text-ink placeholder:text-ink-subtle focus:border-[var(--primary)] focus:shadow-focus focus:outline-none disabled:opacity-40"
                placeholder={canInput ? "输入文字回答,或开麦说话…" : "等待面试官…"}
                value={inputText}
                onChange={(e) => setInputText(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleSend()}
                disabled={!canInput}
              />
              <button
                type="button"
                onClick={handleSend}
                disabled={!canSend}
                className="btn-primary !h-10 !w-10 shrink-0 !px-0 disabled:!bg-surface-muted disabled:!text-ink-subtle"
                title={inputText.trim() ? "发送文字" : isRecording ? "发送语音" : "请输入或说话"}
              >
                <Send size={14} />
              </button>
            </div>
          </div>
        </div>

        {/* 右侧:面试官 + 提纲 */}
        <div className="grid grid-rows-[minmax(180px,1.4fr)_minmax(120px,0.85fr)] lg:grid-rows-[1.618fr_1fr] gap-2 min-h-0 order-1 lg:order-2">
          <TalkingHeadAvatar
            avatarId={sessionMeta.avatar_id}
            sceneId={sessionMeta.scene_id}
            emotion={emotion}
            speaking={aiSpeaking}
            audioLevel={audioLevel}
          />
          <div className="rounded-lg border border-surface-border bg-surface-card p-3.5 sm:p-4 overflow-y-auto flex flex-col min-h-0">
            <div className="flex items-center justify-between mb-3 shrink-0 gap-2">
              <h3 className="text-[13px] font-medium text-ink">参考提纲</h3>
              <label className="flex items-center gap-1.5 text-[11px] text-ink-muted cursor-pointer select-none">
                <input
                  type="checkbox"
                  className="rounded border-surface-border bg-surface-card text-[var(--primary)] focus:ring-[var(--primary)] focus:ring-offset-0"
                  checked={showOutline}
                  onChange={(e) => {
                    setShowOutline(e.target.checked);
                    if (!e.target.checked) setReferenceHint("");
                    else if (lastQuestion) requestHint(lastQuestion);
                  }}
                />
                显示参考
              </label>
            </div>
            <div className="grid grid-cols-2 gap-2 text-[11px] text-ink-muted mb-3 shrink-0">
              <div className="kpi-card !p-2.5">
                <span className="kpi-label">阶段</span>
                <p className="mt-1 text-[13px] font-semibold text-ink">
                  {PHASE_LABELS[currentPhase] || "—"}
                </p>
              </div>
              <div className="kpi-card !p-2.5">
                <span className="kpi-label">Token 约</span>
                <p className="mt-1 font-mono text-[13px] font-semibold text-ink num-tabular">
                  {tokenUsage}
                </p>
              </div>
            </div>

            {!showOutline && (
              <p className="text-[11px] leading-relaxed text-ink-subtle">
                参考提纲已隐藏 — 高难度模式,靠自己发挥
              </p>
            )}
            {showOutline && hintLoading && (
              <div className="flex items-center gap-2 text-[11px] text-ink-muted">
                <span className="block h-3.5 w-3.5 anim-spin rounded-full border-2 border-[var(--primary)] border-t-transparent" />
                AI 正在生成参考回答…
              </div>
            )}
            {showOutline && !hintLoading && referenceHint && (
              <div className="flex-1 overflow-y-auto min-h-0">
                {lastQuestion && (
                  <p className="mb-2 line-clamp-2 text-[11px] leading-relaxed text-[var(--info-ink)]">
                    针对:{lastQuestion}
                  </p>
                )}
                <div className="rounded-md border border-surface-border bg-surface-alt p-3 text-[11px] leading-relaxed text-ink whitespace-pre-wrap">
                  {referenceHint}
                </div>
              </div>
            )}
            {showOutline && !hintLoading && !referenceHint && (
              <p className="text-[11px] leading-relaxed text-ink-subtle">
                面试官提问后,AI 将根据你的简历生成参考回答要点。
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function ChatBubble({
  role,
  content,
  streaming = false,
}: {
  role: string;
  content: string;
  streaming?: boolean;
}) {
  const isUser = role === "user";
  const isNudge = content.startsWith("[追问]");

  return (
    <div className={cn("flex gap-2", isUser ? "flex-row-reverse" : "flex-row")}>
      <span
        className={cn(
          "flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-[11px] font-bold text-white",
          isUser
            ? "bg-[var(--primary)]"
            : "bg-[var(--info)] text-[var(--info-ink)]",
        )}
      >
        {isUser ? "我" : "AI"}
      </span>
      <div className={cn("flex max-w-[85%] flex-col", isUser ? "items-end" : "items-start")}>
        <span className="mb-0.5 px-0.5 text-[10px] text-ink-subtle">
          {isUser ? "候选人" : isNudge ? "面试官 · 追问" : "面试官"}
          {streaming && " · 输入中"}
        </span>
        <div
          className={cn(
            "rounded-md px-3 py-2 text-[13px] leading-relaxed",
            isUser
              ? "rounded-tr-sm bg-[var(--primary)] text-white"
              : isNudge
                ? "rounded-tl-sm border border-[var(--warning)]/30 bg-[var(--warning-soft)] text-[var(--warning-ink)]"
                : "rounded-tl-sm border border-surface-border bg-surface-alt text-ink",
          )}
        >
          {content}
          {streaming && (
            <span className="ml-0.5 inline-block h-3.5 w-1.5 anim-pulse-dot rounded-sm bg-[var(--primary)] align-middle" />
          )}
        </div>
      </div>
    </div>
  );
}
