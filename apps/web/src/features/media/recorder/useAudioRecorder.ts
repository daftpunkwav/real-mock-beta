"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  SILENCE_RMS_THRESHOLD,
  BARGE_RMS_THRESHOLD,
  BARGE_SUSTAIN_MS,
  MIN_SPEECH_CHUNKS,
  MIN_TEXT_CHARS,
  SPEECH_ACTIVITY_THROTTLE_MS,
  TARGET_SAMPLE_RATE,
  RING_BUFFER_MAX_BYTES,
  CAPTURE_ARM_DELAY_MS,
  CAPTURE_ARM_AFTER_BARGE_MS,
} from "./audioRecorderConstants";
import {
  safeCloseAudioContext,
  floatTo16BitPCM,
  encodeBase64,
  appendChunkWithCap,
  shouldCommitOnSilence,
  trimRing,
} from "./audioRecorderPcm";
import { createSpeechRecognitionSession } from "./audioRecorderAsr";
import type { SpeechRecognition } from "./audioRecorderTypes";

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
    onPartialRef.current = onPartial;
    onSpeechActivityRef.current = onSpeechActivity;
    onBargeCandidateRef.current = onBargeCandidate;
  }, [onSilence, onPartial, onSpeechActivity, onBargeCandidate]);

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

  /** 主采集缓冲与 VAD 状态复位（不触碰 ring / 打断状态）。 */
  const resetCaptureState = useCallback(() => {
    chunksRef.current = [];
    chunksBytesRef.current = 0;
    speechChunksRef.current = 0;
    silenceStartRef.current = null;
    finalsRef.current = "";
    interimRef.current = "";
    lastInterimUpdateRef.current = 0;
    lastFinalAtRef.current = 0;
  }, []);

  const clearCaptureBuffers = useCallback(() => {
    resetCaptureState();
    bargeLoudSinceRef.current = null;
    setPartialText("");
  }, [resetCaptureState]);

  /** 打断瞬间：把 AI 期环缓拷贝为下一轮采集种子。 */
  const seedCaptureFromRing = useCallback(() => {
    const seed = ringChunksRef.current.map((c) => c.slice());
    pendingSeedRef.current = seed.length ? seed : null;
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
      startAsrRef.current();
    }, armMs);
    return () => clearTimeout(t);
  }, [captureEnabled, clearCaptureBuffers, stopAsr]);

  // 保持 emitSilence 闭包引用最新
  const emitSilenceRef = useRef(() => {});
  emitSilenceRef.current = () => {
    if (!isCapturing()) {
      clearCaptureBuffers();
      return;
    }
    const text = `${finalsRef.current}${interimRef.current}`.trim();
    const hasSpeech =
      speechChunksRef.current >= MIN_SPEECH_CHUNKS || text.length >= MIN_TEXT_CHARS;
    const nativeRate = ctxRef.current?.sampleRate || TARGET_SAMPLE_RATE;
    const b64 = hasSpeech ? encodeBase64(chunksRef.current, nativeRate) : "";
    resetCaptureState();
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

    stopAsr();
    resetCaptureState();
    bargeLoudSinceRef.current = null;
    ringChunksRef.current = [];
    ringBytesRef.current = 0;
    pendingSeedRef.current = null;
    asrLangRef.current = "zh-CN";
  }, [stopAsr, resetCaptureState]);

  const flush = useCallback(() => {
    if (!streamRef.current) return;
    emitSilenceRef.current();
  }, []);

  // 仅在 enabled 变化时启停录音，避免回调引用变化导致反复重启
  useEffect(() => {
    if (!enabled) {
      stop();
      setPartialText("");
      return;
    }

    stop();
    const session = sessionRef.current;
    setMicError("");
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

          appendChunkWithCap(chunksRef.current, chunksBytesRef, pcm);

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
            else if (
              shouldCommitOnSilence({
                silenceStartMs: silenceStartRef.current,
                chunkCount: chunksRef.current.length,
                speechChunks: speechChunksRef.current,
                finals: finalsRef.current,
                interim: interimRef.current,
                lastInterimUpdate: lastInterimUpdateRef.current,
                lastFinalAt: lastFinalAtRef.current,
              })
            ) {
              emitSilenceRef.current();
            }
          }
        };

        source.connect(processor);
        const silent = ctx.createGain();
        silent.gain.value = 0;
        processor.connect(silent);
        silent.connect(ctx.destination);

        const asr = createSpeechRecognitionSession({
          getSession: () => sessionRef.current,
          isCapturing,
          captureEnabledNow: () => captureEnabledRef.current,
          asrAllowedRef,
          recognitionRef,
          asrLangRef,
          finalsRef,
          interimRef,
          lastFinalAtRef,
          lastInterimUpdateRef,
          setPartialText,
          onPartialRef,
        });
        startAsrRef.current = asr.enableAndStart;
        // 仅在允许采集时启动浏览器 STT
        if (captureEnabledRef.current && isCapturing()) {
          asr.enableAndStart();
        } else if (captureEnabledRef.current) {
          // 武装延时后再启
          asr.startAfterArm(captureArmAtRef.current - Date.now());
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
