"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/** 30 MB:长会话下录音 chunks 上限,超过时丢弃最早的 chunk 防止内存泄漏。 */
const MAX_CHUNKS_BYTES = 30 * 1024 * 1024;
/** 静音触发最少需要累积的 chunk 数,防止首字节就被切。 */
const MIN_CHUNKS_BEFORE_SILENCE = 2;
/** 默认静音时长：思考停顿不误切。 */
const SILENCE_TRIGGER_MS = 1800;
/** 句末快提交：最近有 isFinal 且标点/interim 已空。 */
const SILENCE_FAST_MS = 1000;
/** RMS 阈值,低于此视为静音。 */
const SILENCE_RMS_THRESHOLD = 0.006;
/** 打断专用：更高能量，避免扬声器回声/环境噪音误打断。 */
const BARGE_RMS_THRESHOLD = 0.028;
/** 连续高能量达到此时长才触发打断候选。 */
const BARGE_SUSTAIN_MS = 700;
/** 至少约 1.2s 语音能量才允许静音提交（4096@16k ≈ 256ms/块）。 */
const MIN_SPEECH_CHUNKS = 5;
/** 文本足够长时可放宽能量门槛。 */
const MIN_TEXT_CHARS = 8;
/** interim 仍在更新时禁止提交。 */
const INTERIM_ACTIVE_MS = 600;
/** final 后 interim 清空需稳定多久才可走快路径。 */
const FINAL_SETTLE_MS = 400;
/** 语音活动回调节流（用于静音追问计时，不用于打断）。 */
const SPEECH_ACTIVITY_THROTTLE_MS = 400;
const TARGET_SAMPLE_RATE = 16000;
/** AI 期环形缓冲时长（秒），打断后作为下一轮采集起点。 */
const RING_BUFFER_SEC = 2.5;
const RING_BUFFER_MAX_BYTES = Math.floor(TARGET_SAMPLE_RATE * 2 * RING_BUFFER_SEC);

/** 开启发言采集前的短暂静默，避开扬声器余响。 */
const CAPTURE_ARM_DELAY_MS = 450;
/** 打断后缩短武装延时（环缓已含触发语音）。 */
const CAPTURE_ARM_AFTER_BARGE_MS = 200;

const SENTENCE_END_RE = /[。！？.!?]$/;

/** 估算拉丁字母占比，用于中英识别语言切换。 */
function latinLetterRatio(text: string): number {
  const letters = text.replace(/[^A-Za-z\u4e00-\u9fff]/g, "");
  if (!letters.length) return 0;
  const latin = (letters.match(/[A-Za-z]/g) || []).length;
  return latin / letters.length;
}

/** 安全关闭 AudioContext，避免重复 close 抛 InvalidStateError。 */
function safeCloseAudioContext(ctx: AudioContext | null) {
  if (ctx && ctx.state !== "closed") {
    void ctx.close().catch(() => {});
  }
}

/** 将 Int16 PCM 重采样到 16k，供 Whisper 兜底。 */
function downsampleTo16k(input: Int16Array, inputRate: number): Int16Array {
  if (!input.length || inputRate === TARGET_SAMPLE_RATE) return input;
  if (inputRate < 8000) return input;
  const ratio = inputRate / TARGET_SAMPLE_RATE;
  const outLen = Math.max(1, Math.floor(input.length / ratio));
  const out = new Int16Array(outLen);
  for (let i = 0; i < outLen; i++) {
    out[i] = input[Math.min(input.length - 1, Math.floor(i * ratio))] ?? 0;
  }
  return out;
}

function trimRing(
  chunks: Int16Array[],
  bytesRef: { current: number },
  maxBytes: number,
) {
  while (chunks.length > 1 && bytesRef.current > maxBytes) {
    const dropped = chunks.shift();
    if (dropped) bytesRef.current -= dropped.byteLength;
  }
}

/** 基于能量的简易 VAD + PCM 录制，静默触发回调。 */
export function useAudioRecorder(
  enabled: boolean,
  onSilence: (pcmBase64: string, partialText: string, sampleRate: number) => void,
  onPartial?: (text: string) => void,
  onSpeechActivity?: () => void,
  /** AI 发言中：持续高能量才回调，供全双工打断（比 onSpeechActivity 更严）。 */
  onBargeCandidate?: () => void,
  /**
   * false=仅监听打断能量（AI 发言中），不录音/不 STT/不提交，避免把面试官声音当候选人发言。
   * true=正常采集（USER_SPEAKING）。
   */
  captureEnabled: boolean = true,
) {
  const ctxRef = useRef<AudioContext | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Int16Array[]>([]);
  const chunksBytesRef = useRef(0);
  const speechChunksRef = useRef(0);
  const silenceStartRef = useRef<number | null>(null);
  const recognitionRef = useRef<SpeechRecognition | null>(null);
  const sessionRef = useRef(0);
  const finalsRef = useRef("");
  const interimRef = useRef("");
  const lastSpeechActivityRef = useRef(0);
  const bargeLoudSinceRef = useRef<number | null>(null);
  const lastBargeEmitRef = useRef(0);
  const asrLangRef = useRef<"zh-CN" | "en-US">("zh-CN");
  const captureEnabledRef = useRef(captureEnabled);
  const captureArmAtRef = useRef(0);
  const asrAllowedRef = useRef(false);
  const startAsrRef = useRef<() => void>(() => {});
  const onSilenceRef = useRef(onSilence);
  const onPartialRef = useRef(onPartial);
  const onSpeechActivityRef = useRef(onSpeechActivity);
  const onBargeCandidateRef = useRef(onBargeCandidate);
  /** AI 期环形 PCM */
  const ringChunksRef = useRef<Int16Array[]>([]);
  const ringBytesRef = useRef(0);
  /** barge 后待注入的采集种子 */
  const pendingSeedRef = useRef<Int16Array[] | null>(null);
  const lastInterimUpdateRef = useRef(0);
  const lastFinalAtRef = useRef(0);
  const [isRecording, setIsRecording] = useState(false);
  const [partialText, setPartialText] = useState("");
  const [micError, setMicError] = useState("");

  useEffect(() => {
    onSilenceRef.current = onSilence;
  }, [onSilence]);

  useEffect(() => {
    onPartialRef.current = onPartial;
  }, [onPartial]);

  useEffect(() => {
    onSpeechActivityRef.current = onSpeechActivity;
  }, [onSpeechActivity]);

  useEffect(() => {
    onBargeCandidateRef.current = onBargeCandidate;
  }, [onBargeCandidate]);

  const clearCaptureBuffers = useCallback(() => {
    chunksRef.current = [];
    chunksBytesRef.current = 0;
    speechChunksRef.current = 0;
    silenceStartRef.current = null;
    bargeLoudSinceRef.current = null;
    finalsRef.current = "";
    interimRef.current = "";
    lastInterimUpdateRef.current = 0;
    lastFinalAtRef.current = 0;
    setPartialText("");
  }, []);

  /** 打断瞬间：把 AI 期环缓拷贝为下一轮采集种子。 */
  const seedCaptureFromRing = useCallback(() => {
    const seed = ringChunksRef.current.map((c) => c.slice());
    pendingSeedRef.current = seed.length ? seed : null;
  }, []);

  const isCapturing = () =>
    captureEnabledRef.current && Date.now() >= captureArmAtRef.current;

  const stopAsr = useCallback(() => {
    asrAllowedRef.current = false;
    try {
      const rec = recognitionRef.current;
      if (rec) {
        rec.onend = null;
        rec.stop();
      }
    } catch {
      /* ignore */
    }
    recognitionRef.current = null;
  }, []);

  // AI 发言 ↔ 候选人发言：开启采集时短暂延时再武装；打断种子优先于清空
  useEffect(() => {
    captureEnabledRef.current = captureEnabled;
    if (!captureEnabled) {
      clearCaptureBuffers();
      // 新一轮 AI 发言：环缓从空开始
      ringChunksRef.current = [];
      ringBytesRef.current = 0;
      stopAsr();
      return;
    }
    const seed = pendingSeedRef.current;
    pendingSeedRef.current = null;
    const armMs = seed?.length ? CAPTURE_ARM_AFTER_BARGE_MS : CAPTURE_ARM_DELAY_MS;
    if (seed?.length) {
      chunksRef.current = seed;
      let bytes = 0;
      for (const c of seed) bytes += c.byteLength;
      chunksBytesRef.current = bytes;
      speechChunksRef.current = Math.max(MIN_SPEECH_CHUNKS, Math.min(seed.length, 8));
      silenceStartRef.current = null;
      bargeLoudSinceRef.current = null;
      finalsRef.current = "";
      interimRef.current = "";
      setPartialText("");
      ringChunksRef.current = [];
      ringBytesRef.current = 0;
    } else {
      clearCaptureBuffers();
      ringChunksRef.current = [];
      ringBytesRef.current = 0;
    }
    captureArmAtRef.current = Date.now() + armMs;
    const t = window.setTimeout(() => {
      if (!captureEnabledRef.current || !streamRef.current) return;
      asrAllowedRef.current = true;
      try {
        startAsrRef.current();
      } catch {
        /* ignore */
      }
    }, armMs);
    return () => clearTimeout(t);
  }, [captureEnabled, clearCaptureBuffers, stopAsr]);

  const floatTo16BitPCM = (float32: Float32Array): Int16Array => {
    const out = new Int16Array(float32.length);
    for (let i = 0; i < float32.length; i++) {
      const s = Math.max(-1, Math.min(1, float32[i] ?? 0));
      out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
    }
    return out;
  };

  const encodeBase64 = (arrays: Int16Array[], sampleRate: number): string => {
    if (!arrays.length) return "";
    const total = arrays.reduce((s, a) => s + a.length, 0);
    const merged = new Int16Array(total);
    let offset = 0;
    for (const a of arrays) {
      merged.set(a, offset);
      offset += a.length;
    }
    const pcm16k = downsampleTo16k(merged, sampleRate);
    const bytes = new Uint8Array(pcm16k.buffer, pcm16k.byteOffset, pcm16k.byteLength);
    let binary = "";
    for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i] ?? 0);
    return btoa(binary);
  };

  const currentText = () => `${finalsRef.current}${interimRef.current}`.trim();

  const shouldCommitOnSilence = (): boolean => {
    if (!silenceStartRef.current) return false;
    const silenceMs = Date.now() - silenceStartRef.current;
    if (chunksRef.current.length <= MIN_CHUNKS_BEFORE_SILENCE) return false;
    const text = currentText();
    const enoughSpeech =
      speechChunksRef.current >= MIN_SPEECH_CHUNKS || text.length >= MIN_TEXT_CHARS;
    if (!enoughSpeech) return false;

    // interim 仍在跳动：说话途中短停，禁止提交
    if (
      interimRef.current &&
      Date.now() - lastInterimUpdateRef.current < INTERIM_ACTIVE_MS
    ) {
      return false;
    }

    const now = Date.now();
    const hasRecentFinal =
      lastFinalAtRef.current > 0 && now - lastFinalAtRef.current < 8000;
    const endsWithPunct = SENTENCE_END_RE.test(text);
    const interimEmptySettled =
      !interimRef.current &&
      lastFinalAtRef.current > 0 &&
      now - lastFinalAtRef.current >= FINAL_SETTLE_MS;
    const fastPath = hasRecentFinal && (endsWithPunct || interimEmptySettled);
    const threshold = fastPath ? SILENCE_FAST_MS : SILENCE_TRIGGER_MS;
    return silenceMs > threshold;
  };

  // 保持 emitSilence 闭包引用最新
  const emitSilenceRef = useRef(() => {});
  emitSilenceRef.current = () => {
    if (!isCapturing()) {
      clearCaptureBuffers();
      return;
    }
    const text = currentText();
    const hasSpeech =
      speechChunksRef.current >= MIN_SPEECH_CHUNKS || text.length >= MIN_TEXT_CHARS;
    const nativeRate = ctxRef.current?.sampleRate || TARGET_SAMPLE_RATE;
    const b64 = hasSpeech ? encodeBase64(chunksRef.current, nativeRate) : "";
    chunksRef.current = [];
    chunksBytesRef.current = 0;
    speechChunksRef.current = 0;
    silenceStartRef.current = null;
    finalsRef.current = "";
    interimRef.current = "";
    lastInterimUpdateRef.current = 0;
    lastFinalAtRef.current = 0;
    setPartialText("");
    if (b64 || text) {
      onSilenceRef.current(b64, text, TARGET_SAMPLE_RATE);
    }
  };

  const stop = useCallback(() => {
    sessionRef.current += 1;
    setIsRecording(false);

    processorRef.current?.disconnect();
    processorRef.current = null;

    sourceRef.current?.disconnect();
    sourceRef.current = null;

    safeCloseAudioContext(ctxRef.current);
    ctxRef.current = null;

    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;

    try {
      const rec = recognitionRef.current;
      if (rec) {
        rec.onend = null;
        rec.stop();
      }
    } catch {
      /* 识别器可能已停止 */
    }
    recognitionRef.current = null;

    chunksRef.current = [];
    chunksBytesRef.current = 0;
    speechChunksRef.current = 0;
    silenceStartRef.current = null;
    bargeLoudSinceRef.current = null;
    ringChunksRef.current = [];
    ringBytesRef.current = 0;
    pendingSeedRef.current = null;
    asrLangRef.current = "zh-CN";
  }, []);

  const flush = useCallback(() => {
    if (!streamRef.current) return;
    emitSilenceRef.current();
  }, []);

  // 仅在 enabled 变化时启停录音，避免回调引用变化导致反复重启
  useEffect(() => {
    if (!enabled) {
      stop();
      finalsRef.current = "";
      interimRef.current = "";
      setPartialText("");
      return;
    }

    stop();
    const session = sessionRef.current;
    setMicError("");
    finalsRef.current = "";
    interimRef.current = "";
    setPartialText("");

    (async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          audio: {
            echoCancellation: true,
            noiseSuppression: true,
            autoGainControl: true,
          },
        });
        if (session !== sessionRef.current) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }

        streamRef.current = stream;
        const ctx = new AudioContext({ sampleRate: TARGET_SAMPLE_RATE });
        ctxRef.current = ctx;
        if (ctx.state === "suspended") {
          await ctx.resume();
        }

        const source = ctx.createMediaStreamSource(stream);
        sourceRef.current = source;

        const processor = ctx.createScriptProcessor(4096, 1, 1);
        processorRef.current = processor;

        processor.onaudioprocess = (e) => {
          if (session !== sessionRef.current) return;

          const input = e.inputBuffer.getChannelData(0);
          let sum = 0;
          for (let i = 0; i < input.length; i++) sum += (input[i] ?? 0) * (input[i] ?? 0);
          const rms = Math.sqrt(sum / input.length);
          const now = Date.now();
          const pcm = floatTo16BitPCM(input);

          // AI 发言期：环形缓冲 + 打断能量检测（不提交、不开 ASR）
          if (!captureEnabledRef.current) {
            ringChunksRef.current.push(pcm);
            ringBytesRef.current += pcm.byteLength;
            trimRing(ringChunksRef.current, ringBytesRef, RING_BUFFER_MAX_BYTES);

            if (rms >= BARGE_RMS_THRESHOLD) {
              if (bargeLoudSinceRef.current == null) {
                bargeLoudSinceRef.current = now;
              } else if (
                now - bargeLoudSinceRef.current >= BARGE_SUSTAIN_MS &&
                now - lastBargeEmitRef.current >= 1200
              ) {
                lastBargeEmitRef.current = now;
                bargeLoudSinceRef.current = now;
                onBargeCandidateRef.current?.();
              }
            } else {
              bargeLoudSinceRef.current = null;
            }
            return;
          }

          // 武装延时期：丢弃音频防回采，不做打断
          if (now < captureArmAtRef.current) {
            return;
          }

          chunksRef.current.push(pcm);
          chunksBytesRef.current += pcm.byteLength;
          while (
            chunksRef.current.length > 1 &&
            chunksBytesRef.current > MAX_CHUNKS_BYTES
          ) {
            const dropped = chunksRef.current.shift();
            if (dropped) chunksBytesRef.current -= dropped.byteLength;
          }

          if (rms >= SILENCE_RMS_THRESHOLD) {
            speechChunksRef.current += 1;
            silenceStartRef.current = null;
            if (now - lastSpeechActivityRef.current >= SPEECH_ACTIVITY_THROTTLE_MS) {
              lastSpeechActivityRef.current = now;
              onSpeechActivityRef.current?.();
            }
          } else {
            bargeLoudSinceRef.current = null;
            if (!silenceStartRef.current) silenceStartRef.current = Date.now();
            else if (shouldCommitOnSilence()) {
              emitSilenceRef.current();
            }
          }
        };

        source.connect(processor);
        const silent = ctx.createGain();
        silent.gain.value = 0;
        processor.connect(silent);
        silent.connect(ctx.destination);

        const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (SR && session === sessionRef.current) {
          const startRec = () => {
            if (session !== sessionRef.current) return;
            if (!asrAllowedRef.current || !isCapturing()) return;
            // 已有实例在跑则不重复 start
            if (recognitionRef.current) return;
            const rec = new SR();
            rec.lang = asrLangRef.current;
            rec.continuous = true;
            rec.interimResults = true;
            rec.onresult = (event) => {
              if (!isCapturing()) return;
              let interim = "";
              let gotFinal = false;
              for (let i = event.resultIndex; i < event.results.length; i++) {
                const r = event.results[i];
                if (!r) continue;
                const piece = r[0]?.transcript ?? "";
                if (r.isFinal) {
                  finalsRef.current = `${finalsRef.current}${piece}`;
                  gotFinal = true;
                } else {
                  interim += piece;
                }
              }
              interimRef.current = interim;
              if (gotFinal) lastFinalAtRef.current = Date.now();
              if (interim) lastInterimUpdateRef.current = Date.now();
              const text = currentText();
              setPartialText(text);
              onPartialRef.current?.(text);

              const tail = text.slice(-48);
              if (tail.length >= 3) {
                const ratio = latinLetterRatio(tail);
                const nextLang: "zh-CN" | "en-US" =
                  ratio >= 0.55 ? "en-US" : "zh-CN";
                if (nextLang !== asrLangRef.current) {
                  asrLangRef.current = nextLang;
                  try {
                    rec.onend = null;
                    rec.stop();
                  } catch {
                    /* ignore */
                  }
                  recognitionRef.current = null;
                  window.setTimeout(() => {
                    if (session !== sessionRef.current) return;
                    try {
                      startRec();
                    } catch {
                      /* ignore */
                    }
                  }, 80);
                }
              }
            };
            rec.onerror = () => {
              /* no-speech / aborted 等由 onend 重启 */
            };
            rec.onend = () => {
              recognitionRef.current = null;
              if (session !== sessionRef.current) return;
              if (!asrAllowedRef.current || !isCapturing()) return;
              try {
                startRec();
              } catch {
                /* ignore */
              }
            };
            try {
              rec.start();
              recognitionRef.current = rec;
            } catch {
              /* already started */
            }
          };
          startAsrRef.current = startRec;
          // 仅在允许采集时启动浏览器 STT
          if (captureEnabledRef.current && isCapturing()) {
            asrAllowedRef.current = true;
            startRec();
          } else if (captureEnabledRef.current) {
            // 武装延时后再启
            window.setTimeout(() => {
              if (session !== sessionRef.current) return;
              if (!captureEnabledRef.current) return;
              asrAllowedRef.current = true;
              startRec();
            }, Math.max(0, captureArmAtRef.current - Date.now()));
          }
        }

        if (session === sessionRef.current) {
          setIsRecording(true);
        }
      } catch (e) {
        const msg = e instanceof Error ? e.message : "麦克风不可用";
        setMicError(msg);
        console.warn("麦克风不可用", e);
        if (streamRef.current) {
          streamRef.current.getTracks().forEach((t) => t.stop());
          streamRef.current = null;
        }
        safeCloseAudioContext(ctxRef.current);
        ctxRef.current = null;
      }
    })();

    return () => stop();
  }, [enabled, stop]);

  return {
    stop,
    flush,
    clearCaptureBuffers,
    seedCaptureFromRing,
    isRecording,
    partialText,
    micError,
  };
}

interface SpeechRecognition extends EventTarget {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  start(): void;
  stop(): void;
  onresult: ((event: SpeechRecognitionEvent) => void) | null;
  onerror: ((event: Event) => void) | null;
  onend: (() => void) | null;
}

interface SpeechRecognitionEvent {
  resultIndex: number;
  results: {
    length: number;
    [i: number]: { [j: number]: { transcript: string }; isFinal: boolean };
  };
}

declare global {
  interface Window {
    SpeechRecognition: new () => SpeechRecognition;
    webkitSpeechRecognition: new () => SpeechRecognition;
  }
}
