"use client";

import { useCallback, useEffect, useRef, useState } from "react";

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
  const levelRafRef = useRef<number | null>(null);
  /** 未解锁或播放失败时整段缓冲，供重试 */
  const heldQueueRef = useRef<string[]>([]);
  const onSpeakingChangeRef = useRef<(v: boolean) => void>(() => {});
  const onLevelRef = useRef<(level: number) => void>(() => {});
  const onBlockedRef = useRef<(blocked: boolean) => void>(() => {});
  const onPlaybackDoneRef = useRef<() => void>(() => {});
  const [queueDepth, setQueueDepth] = useState(0);
  const [audioUnlocked, setAudioUnlocked] = useState(false);

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

  const _stopLevelLoop = useCallback(() => {
    if (levelRafRef.current != null) {
      cancelAnimationFrame(levelRafRef.current);
      levelRafRef.current = null;
    }
    onLevelRef.current(0);
  }, []);

  const _startLevelLoop = useCallback(() => {
    const analyser = analyserRef.current;
    if (!analyser) return;
    const data = new Uint8Array(analyser.frequencyBinCount);
    const tick = () => {
      analyser.getByteTimeDomainData(data);
      let sum = 0;
      for (let i = 0; i < data.length; i++) {
        const v = ((data[i] ?? 128) - 128) / 128;
        sum += v * v;
      }
      const rms = Math.sqrt(sum / data.length);
      onLevelRef.current(Math.min(1, rms * 4));
      levelRafRef.current = requestAnimationFrame(tick);
    };
    _stopLevelLoop();
    levelRafRef.current = requestAnimationFrame(tick);
  }, [_stopLevelLoop]);

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
        audioCtxRef.current = new AudioContext();
      }
      const ctx = audioCtxRef.current;
      if (ctx.state === "suspended") {
        await ctx.resume();
      }
      if (ctx.state !== "running") {
        unlockedRef.current = false;
        setAudioUnlocked(false);
        onBlockedRef.current(true);
        return false;
      }
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      gain.gain.value = 0;
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start();
      osc.stop(ctx.currentTime + 0.02);
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
                _stopLevelLoop();
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
                _stopLevelLoop();
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
                  const ctx = audioCtxRef.current ?? new AudioContext();
                  audioCtxRef.current = ctx;
                  if (ctx.state === "suspended") {
                    await ctx.resume();
                  }
                  if (ctx.state !== "running") {
                    finishBlocked();
                    return;
                  }
                  if (!analyserRef.current) {
                    const analyser = ctx.createAnalyser();
                    analyser.fftSize = 256;
                    analyserRef.current = analyser;
                    analyser.connect(ctx.destination);
                  }
                  try {
                    const src = ctx.createMediaElementSource(audio);
                    sourceNodeRef.current = src;
                    src.connect(analyserRef.current);
                    _startLevelLoop();
                  } catch {
                    /* MediaElementSource 失败则 element 直出，无口型电平 */
                  }
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
    [_releaseCurrent, _startLevelLoop, _stopLevelLoop, _notifyIfIdle],
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
  const stop = useCallback((opts?: { silent?: boolean }) => {
    epochRef.current += 1;
    _releaseCurrent();
    speakingRef.current = false;
    pendingCountRef.current = 0;
    heldQueueRef.current = [];
    setQueueDepth(0);
    onSpeakingChangeRef.current(false);
    _stopLevelLoop();
    queueRef.current = Promise.resolve();
    if (!opts?.silent) {
      // 用户主动打断：允许服务端开麦
      onPlaybackDoneRef.current();
    }
  }, [_releaseCurrent, _stopLevelLoop]);

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
