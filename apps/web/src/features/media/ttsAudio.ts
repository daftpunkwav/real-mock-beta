/**
 * TTS 播放的 AudioContext 小工具：创建/唤醒上下文、analyser 接线与静音探针。
 * 均为纯函数，错误统一交由调用方 try/catch 处理。
 */

/** 创建音频上下文；浏览器禁用/不支持时返回 null。 */
export function createAudioContext(): AudioContext | null {
  try {
    return new AudioContext();
  } catch {
    return null;
  }
}

/** 唤醒挂起的上下文；最终处于 running 才算成功。 */
export async function ensureContextRunning(ctx: AudioContext): Promise<boolean> {
  if (ctx.state === "suspended") {
    try {
      await ctx.resume();
    } catch {
      return false;
    }
  }
  return ctx.state === "running";
}

/** 创建 analyser 并接入输出，供音量电平采集（口型驱动）。 */
export function createAnalyserNode(ctx: AudioContext): AnalyserNode | null {
  try {
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 256;
    analyser.connect(ctx.destination);
    return analyser;
  } catch {
    return null;
  }
}

/** 将播放元素接入 analyser。analyser 缺失时不要创建 MediaElementSource（会劫持 element 输出导致无声）。 */
export function connectElementToAnalyser(
  ctx: AudioContext,
  audio: HTMLAudioElement,
  analyser: AnalyserNode | null,
): MediaElementAudioSourceNode | null {
  if (!analyser) return null;
  try {
    const src = ctx.createMediaElementSource(audio);
    src.connect(analyser);
    return src;
  } catch {
    return null;
  }
}

/** 用户手势内的静音探针：触发浏览器自动播放解锁。 */
export function fireSilentProbe(ctx: AudioContext): void {
  try {
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    gain.gain.value = 0;
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + 0.02);
  } catch {
    /* noop */
  }
}
