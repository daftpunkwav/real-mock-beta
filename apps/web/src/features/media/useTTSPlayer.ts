"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  connectElementToAnalyser,
  createAnalyserNode,
  createAudioContext,
  ensureContextRunning,
  fireSilentProbe,
} from "./ttsAudio";
import { createTTSLevelLoop, type TTSLevelLoop } from "./ttsLevelLoop";

/**
 * 顺序播放 base64 MP3；必须先经用户手势 unlock，否则只缓冲不播、不假报 tts_playback_done。
 * 队列真实清空后才触发 onPlaybackDone。
 */
export function useTTSPlayer() {
  const queueRef = useRef<Promise<void>>(Promise.resolve());
  const currentAudioRef = useRef<HTMLAudioElement | null>(null);
  const sourceNodeRef = useRef<MediaElementAudioSourceNode | null>(null);
  const speakingRef = useRef(false);
  const pendingCountRef = useRef(0);
  const unlockedRef = useRef(false);
  const epochRef = useRef(0);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  /** 未解锁或播放失败时整段缓冲，供重试 */
  const heldQueueRef = useRef<string[]>([]);
  const onSpeakingChangeRef = useRef<(v: boolean) => void>(() => {});
  const onLevelRef = useRef<(level: number) => void>(() => {});
  const onBlockedRef = useRef<(blocked: boolean) => void>(() => {});
  const onPlaybackDoneRef = useRef<() => void>(() => {});
  const [queueDepth, setQueueDepth] = useState(0);
  const [audioUnlocked, setAudioUnlocked] = useState(false);

  const levelLoopRef = useRef<TTSLevelLoop | null>(null);
  if (levelLoopRef.current === null) {
    levelLoopRef.current = createTTSLevelLoop({
      getAnalyser: () => analyserRef.current,
      onLevel: (level) => onLevelRef.current(level),
    });
  }

  const setOnSpeakingChange = useCallback((fn: (v: boolean) => void) => {
    onSpeakingChangeRef.current = fn;
  }, []);

  const setOnAudioLevel = useCallback((fn: (level: number) => void) => {
    onLevelRef.current = fn;
  }, []);

  const setOnPlaybackBlocked = useCallback((fn: (blocked: boolean) => void) => {
    onBlockedRef.current = fn;
  }, []);

  const setOnPlaybackDone = useCallback((fn: () => void) => {
    onPlaybackDoneRef.current = fn;
  }, []);

  const _releaseCurrent = useCallback(() => {
    try {
      sourceNodeRef.current?.disconnect();
    } catch {
      /* noop */
    }
    sourceNodeRef.current = null;
    const a = currentAudioRef.current;
    if (!a) return;
    try {
      a.pause();
      a.src = "";
      a.onended = null;
      a.onerror = null;
    } catch {
      /* noop */
    }
    currentAudioRef.current = null;
  }, []);

  /**
   * 队列空闲时通知服务端可开麦。
   * - 未解锁且仅有 held：不回报（强制手势解锁，避免无声假 done）
   * - 已解锁但播失败入 held：仍回报，否则会永久卡住麦/文字输入
   */
  const _notifyIfIdle = useCallback(() => {
    if (pendingCountRef.current > 0 || speakingRef.current) return;
    if (!unlockedRef.current && heldQueueRef.current.length > 0) return;
    onPlaybackDoneRef.current();
  }, []);

  /** 用户手势中调用：解锁自动播放 */
  const unlockAudio = useCallback(async () => {
    try {
      if (!audioCtxRef.current) {
        audioCtxRef.current = createAudioContext();
      }
      const ctx = audioCtxRef.current;
      if (!ctx || !(await ensureContextRunning(ctx))) {
        unlockedRef.current = false;
        setAudioUnlocked(false);
        onBlockedRef.current(true);
        return false;
      }
      fireSilentProbe(ctx);
      unlockedRef.current = true;
      setAudioUnlocked(true);
      onBlockedRef.current(false);
      return true;
    } catch {
      unlockedRef.current = false;
      setAudioUnlocked(false);
      onBlockedRef.current(true);
      return false;
    }
  }, []);

  const playBase64Mp3 = useCallback(
    (b64: string) => {
      if (!b64) return;

      // 未解锁：只缓冲，不 play、不假报 done
      if (!unlockedRef.current) {
        heldQueueRef.current.push(b64);
        onBlockedRef.current(true);
        return;
      }

      const jobEpoch = epochRef.current;
      pendingCountRef.current += 1;
      setQueueDepth(pendingCountRef.current);
      const job = (prev: Promise<void>) =>
        prev.then(
          () =>
            new Promise<void>((resolve) => {
              const finishOk = () => {
                if (jobEpoch !== epochRef.current) {
                  resolve();
                  return;
                }
                pendingCountRef.current = Math.max(0, pendingCountRef.current - 1);
                setQueueDepth(pendingCountRef.current);
                currentAudioRef.current = null;
                speakingRef.current = false;
                onSpeakingChangeRef.current(false);
                levelLoopRef.current?.stop();
                _notifyIfIdle();
                resolve();
              };

              /** 播放失败：入重试队列；已解锁时仍回报 idle，避免卡死回合 */
              const finishBlocked = () => {
                if (jobEpoch !== epochRef.current) {
                  resolve();
                  return;
                }
                pendingCountRef.current = Math.max(0, pendingCountRef.current - 1);
                setQueueDepth(pendingCountRef.current);
                currentAudioRef.current = null;
                speakingRef.current = false;
                onSpeakingChangeRef.current(false);
                levelLoopRef.current?.stop();
                heldQueueRef.current.push(b64);
                onBlockedRef.current(true);
                _notifyIfIdle();
                resolve();
              };

              if (jobEpoch !== epochRef.current) {
                resolve();
                return;
              }

              _releaseCurrent();
              const audio = new Audio(`data:audio/mpeg;base64,${b64}`);
              currentAudioRef.current = audio;
              speakingRef.current = true;
              onSpeakingChangeRef.current(true);

              const runPlay = async () => {
                try {
                  const ctx = audioCtxRef.current ?? createAudioContext();
                  if (ctx) {
                    audioCtxRef.current = ctx;
                    if (!(await ensureContextRunning(ctx))) {
                      finishBlocked();
                      return;
                    }
                    if (!analyserRef.current) {
                      analyserRef.current = createAnalyserNode(ctx);
                    }
                    const src = connectElementToAnalyser(ctx, audio, analyserRef.current);
                    if (src) {
                      sourceNodeRef.current = src;
                      levelLoopRef.current?.start();
                    }
                    /* MediaElementSource / analyser 失败则 element 直出，无口型电平 */
                  }
                  /* AudioContext 创建失败：仍尝试 element.play */
                } catch {
                  /* 仍尝试 element.play */
                }

                audio.onended = () => {
                  finishOk();
                };
                audio.onerror = () => {
                  finishBlocked();
                };

                try {
                  await audio.play();
                  if (jobEpoch !== epochRef.current) {
                    try {
                      audio.pause();
                    } catch {
                      /* noop */
                    }
                    finishOk();
                    return;
                  }
                  onBlockedRef.current(false);
                } catch {
                  finishBlocked();
                }
              };

              void runPlay();
            }),
        );
      queueRef.current = job(queueRef.current);
    },
    [_releaseCurrent, _notifyIfIdle],
  );

  /** 重放整段缓冲（unlock 后或自动播放拦截后） */
  const flushHeldQueue = useCallback(() => {
    const held = heldQueueRef.current.splice(0, heldQueueRef.current.length);
    if (held.length === 0) return false;
    onBlockedRef.current(false);
    for (const b64 of held) {
      playBase64Mp3(b64);
    }
    return true;
  }, [playBase64Mp3]);

  const retryLastFailed = useCallback(() => {
    return flushHeldQueue();
  }, [flushHeldQueue]);

  /**
   * 停止播放并清空队列。
   * @param opts.silent 为 true 时不上报 playback_done（避免 barge 本地 stop 与 tts_interrupted 双重上报）
   */
  const stop = useCallback(
    (opts?: { silent?: boolean }) => {
      epochRef.current += 1;
      _releaseCurrent();
      speakingRef.current = false;
      pendingCountRef.current = 0;
      heldQueueRef.current = [];
      setQueueDepth(0);
      onSpeakingChangeRef.current(false);
      levelLoopRef.current?.stop();
      queueRef.current = Promise.resolve();
      if (!opts?.silent) {
        // 用户主动打断：允许服务端开麦
        onPlaybackDoneRef.current();
      }
    },
    [_releaseCurrent],
  );

  useEffect(() => {
    return () => {
      stop();
      void audioCtxRef.current?.close().catch(() => {});
      audioCtxRef.current = null;
      analyserRef.current = null;
    };
  }, [stop]);

  return {
    playBase64Mp3,
    setOnSpeakingChange,
    setOnAudioLevel,
    setOnPlaybackBlocked,
    setOnPlaybackDone,
    unlockAudio,
    retryLastFailed,
    flushHeldQueue,
    stop,
    isSpeaking: () => speakingRef.current,
    /** 是否正在播报（不含 held 重试队列——held 不应锁死麦/输入） */
    isActivelyPlaying: () => pendingCountRef.current > 0 || speakingRef.current,
    /** @deprecated 语义含 held；门控请用 isActivelyPlaying */
    isQueueBusy: () => pendingCountRef.current > 0 || speakingRef.current,
    queueDepth,
    audioUnlocked,
    heldCount: () => heldQueueRef.current.length,
  };
}
