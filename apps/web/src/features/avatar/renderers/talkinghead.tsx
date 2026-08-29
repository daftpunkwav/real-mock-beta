"use client";

import { useEffect, useRef } from "react";
import type { AvatarExpression, AvatarRendererDef, AvatarRendererProps } from "../contract";

/**
 * 3D 头像渲染通道：@met4citizen/talkinghead 适配器。
 *
 * 本文件是唯一允许 import 该库的边界；表情（expression）→ 库内 mood +
 * morph 的映射、音色光照等资产定制全部收拢在此。替换渲染通道时只替换
 * renderers/ 下的适配器，调用方零改动。
 */

/** 同源 GLB 资产与该通道的渲染定制（基线姿态/光照/默认心境）。 */
const AVATAR_ASSETS: Record<
  string,
  {
    url: string;
    body: "M" | "F";
    mood: TalkingMood;
    baseline?: Record<string, number>;
    light?: { ambient: number; direct: number; directColor: number };
  }
> = {
  professional_male: {
    url: "/avatars/professional_male.glb",
    body: "M",
    mood: "neutral",
    baseline: {
      headRotateX: 0.12,
      eyesLookDown: 0,
      eyesLookUp: 0.08,
      eyeBlinkLeft: 0.02,
      eyeBlinkRight: 0.02,
    },
    light: { ambient: 1.25, direct: 8, directColor: 0xffe6cc },
  },
  senior_male: {
    url: "/avatars/senior_male.glb",
    body: "M",
    mood: "neutral",
    baseline: {
      headRotateX: 0.1,
      eyesLookDown: 0,
      eyesLookUp: 0.06,
      eyeBlinkLeft: 0.02,
      eyeBlinkRight: 0.02,
    },
    light: { ambient: 1.05, direct: 9, directColor: 0xffd8b0 },
  },
  strict_expert: {
    url: "/avatars/senior_male.glb",
    body: "M",
    mood: "angry",
    baseline: {
      headRotateX: 0.1,
      eyesLookDown: 0,
      eyesLookUp: 0.05,
      browInnerUp: 0.15,
      eyeBlinkLeft: 0.02,
      eyeBlinkRight: 0.02,
    },
    light: { ambient: 0.9, direct: 11, directColor: 0xffd0b0 },
  },
  gentle_female: {
    url: "/avatars/gentle_female.glb",
    body: "F",
    mood: "happy",
    baseline: {
      headRotateX: 0.1,
      eyesLookDown: 0,
      eyesLookUp: 0.08,
      mouthSmile: 0.15,
    },
    light: { ambient: 1.3, direct: 7.5, directColor: 0xffeef0 },
  },
  hr_female: {
    url: "/avatars/hr_female.glb",
    body: "F",
    mood: "neutral",
    baseline: {
      headRotateX: 0.1,
      eyesLookDown: 0,
      eyesLookUp: 0.07,
    },
    light: { ambient: 1.2, direct: 8, directColor: 0xffe8d8 },
  },
  young_female: {
    url: "/avatars/young_female.glb",
    body: "F",
    mood: "happy",
    baseline: {
      headRotateX: 0.11,
      eyesLookDown: 0,
      eyesLookUp: 0.09,
      mouthSmile: 0.2,
    },
    light: { ambient: 1.35, direct: 7, directColor: 0xfff0e8 },
  },
};

/** 库内置心境名（无 serious；未列出值一律回落 neutral）。 */
type TalkingMood =
  | "neutral"
  | "happy"
  | "angry"
  | "sad"
  | "fear"
  | "disgust"
  | "love"
  | "sleep";

const VALID_MOODS: ReadonlySet<TalkingMood> = new Set([
  "neutral",
  "happy",
  "angry",
  "sad",
  "fear",
  "disgust",
  "love",
  "sleep",
]);

function safeMood(mood: string | undefined, fallback: TalkingMood = "neutral"): TalkingMood {
  if (mood && VALID_MOODS.has(mood as TalkingMood)) return mood as TalkingMood;
  return fallback;
}

/** 表情 → 库内心境（mood 粒度不够时由辅助 morph 补一层）。 */
const EXPRESSION_TO_MOOD: Record<string, TalkingMood> = {
  neutral: "neutral",
  smile: "happy",
  happy: "happy",
  serious: "neutral",
  curious: "neutral",
  encouraging: "happy",
  skeptical: "fear",
  concerned: "sad",
  angry: "angry",
  sad: "sad",
};

/** 表情 → 辅助 morph（眉/眼/嘴角）。 */
const EXPRESSION_MORPH: Record<
  string,
  { browInnerUp?: number; eyeSquint?: number; mouthSmile?: number; eyesClosed?: number }
> = {
  neutral: {},
  smile: { mouthSmile: 0.45, eyeSquint: 0.15 },
  happy: { mouthSmile: 0.55, eyeSquint: 0.2 },
  serious: { browInnerUp: 0.35, mouthSmile: 0 },
  curious: { browInnerUp: 0.4, mouthSmile: 0.1 },
  encouraging: { mouthSmile: 0.4, eyeSquint: 0.12 },
  skeptical: { browInnerUp: 0.25, mouthSmile: 0 },
  concerned: { browInnerUp: 0.45, mouthSmile: 0, eyesClosed: 0.08 },
  angry: { browInnerUp: 0.55, mouthSmile: 0 },
  sad: { browInnerUp: 0.3, mouthSmile: 0, eyesClosed: 0.12 },
};

type HeadInstance = {
  showAvatar: (avatar: Record<string, unknown>, onprogress?: (ev: unknown) => void) => Promise<void>;
  setMood: (mood: string) => void;
  setValue: (mt: string, val: number, ms?: number | null) => void;
  setBaselineValue?: (mt: string, val: number | null) => void;
  setFixedValue?: (mt: string, val: number | null, ms?: number | null) => void;
  getMoodNames?: () => string[];
  lookAt?: (x: number, y: number, t: number) => void;
  lookAtCamera?: (t: number) => void;
  makeEyeContact?: (t: number) => void;
  stop?: () => void;
};

/** 音量 → 口型：低电平闭嘴、带攻击/衰减的平滑曲线 */
function mapAudioToMouth(level: number, speaking: boolean): number {
  if (!speaking) return 0;
  if (level < 0.03) return 0;
  const shaped = Math.pow(Math.min(1, (level - 0.03) / 0.75), 0.85);
  return Math.min(0.95, 0.12 + shaped * 0.88);
}

function TalkingHeadRenderer({
  avatarId,
  emotion,
  speaking,
  audioLevel,
  onProgress,
  onReady,
  onFailed,
}: AvatarRendererProps) {
  const mountRef = useRef<HTMLDivElement>(null);
  const headRef = useRef<HeadInstance | null>(null);
  const mouthSmoothRef = useRef(0);
  const rafRef = useRef<number>(0);
  const bootGenRef = useRef(0);

  // 就绪状态上抛由 boot 流程驱动；失败上抛后由舞台切通道
  useEffect(() => {
    const gen = ++bootGenRef.current;
    let cancelled = false;
    let head: HeadInstance | null = null;
    /** 每次 boot 独立挂载点，避免 Strict Mode 双挂载时 stop() 清掉下一次的 DOM */
    let mount: HTMLDivElement | null = null;

    const boot = async () => {
      const node = mountRef.current;
      if (!node) return;
      try {
        const mod = await import("@met4citizen/talkinghead");
        const TalkingHead = (mod as { TalkingHead: new (n: HTMLElement, o?: object) => HeadInstance })
          .TalkingHead;
        if (cancelled || bootGenRef.current !== gen) return;

        const profile = AVATAR_ASSETS[avatarId] || AVATAR_ASSETS.professional_male!;
        const mood = safeMood(profile.mood);
        mount = document.createElement("div");
        mount.style.cssText = "position:absolute;inset:0;width:100%;height:100%;";
        node.replaceChildren(mount);

        const light = profile.light;
        head = new TalkingHead(mount, {
          ttsEndpoint: "",
          lipsyncModules: [],
          cameraView: "head",
          avatarMood: mood,
          avatarIdleEyeContact: 1,
          avatarSpeakingEyeContact: 1,
          avatarIdleHeadMove: 0.08,
          avatarSpeakingHeadMove: 0.1,
          lightAmbientColor: 0x8899aa,
          lightAmbientIntensity: light?.ambient ?? 1.2,
          lightDirectColor: light?.directColor ?? 0xffe6cc,
          lightDirectIntensity: light?.direct ?? 8,
          modelFPS: 30,
        });
        headRef.current = head;

        const avatarOpts: Record<string, unknown> = {
          url: profile.url,
          body: profile.body,
          avatarMood: mood,
          avatarIdleEyeContact: 1,
          avatarSpeakingEyeContact: 1,
          avatarIdleHeadMove: 0.08,
        };
        if (profile.baseline) avatarOpts.baseline = profile.baseline;

        await head.showAvatar(avatarOpts, (ev: unknown) => {
          const e = ev as { lengthComputable?: boolean; loaded?: number; total?: number };
          if (e?.lengthComputable && e.total && e.total > 0) {
            const raw = Math.round((100 * (e.loaded || 0)) / e.total);
            if (bootGenRef.current === gen) onProgress?.(Math.min(100, Math.max(0, raw)));
          }
        });
        if (cancelled || bootGenRef.current !== gen) {
          try {
            head.stop?.();
          } catch {
            /* noop */
          }
          mount?.remove();
          return;
        }
        // 进房后锁定视线看向镜头，避免长时间低头/瞟向别处
        try {
          head.setBaselineValue?.("eyesLookDown", 0);
          head.setFixedValue?.("eyesLookDown", 0, 200);
          head.setValue("eyesLookDown", 0, 200);
          head.setValue("eyesLookUp", 0.08, 200);
          head.setValue("headRotateX", 0.1, 300);
          head.lookAtCamera?.(1500);
          head.makeEyeContact?.(3000);
        } catch {
          /* ignore */
        }
        if (bootGenRef.current === gen) onReady?.();
      } catch (err) {
        console.warn("3D 头像通道加载失败", avatarId, err);
        if (!cancelled && bootGenRef.current === gen) onFailed?.(err);
      }
    };

    void boot();
    return () => {
      cancelled = true;
      try {
        head?.stop?.();
      } catch {
        /* noop */
      }
      if (headRef.current === head) headRef.current = null;
      try {
        mount?.remove();
      } catch {
        /* noop */
      }
    };
    // avatarId 变化即重建；回调经引用稳定约定由舞台保证
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [avatarId]);

  // 说话时周期性看向镜头
  useEffect(() => {
    const head = headRef.current;
    if (!head) return;
    const lockGaze = () => {
      try {
        head.setBaselineValue?.("eyesLookDown", 0);
        head.setFixedValue?.("eyesLookDown", 0, 180);
        head.setValue("eyesLookDown", 0, 180);
        head.setValue("eyesLookUp", 0.08, 180);
        head.setValue("headRotateX", 0.1, 250);
        head.lookAtCamera?.(speaking ? 700 : 1200);
        head.makeEyeContact?.(speaking ? 900 : 2000);
      } catch {
        /* ignore */
      }
    };
    lockGaze();
    const id = window.setInterval(lockGaze, 2800);
    return () => window.clearInterval(id);
  }, [speaking]);

  // 表情 → 心境 + 辅助 morph
  useEffect(() => {
    const head = headRef.current;
    if (!head) return;
    const mood = EXPRESSION_TO_MOOD[emotion] ?? "neutral";
    try {
      const names = head.getMoodNames?.() || [];
      if (names.length === 0 || names.includes(mood)) {
        head.setMood(mood);
      } else {
        head.setMood("neutral");
      }
    } catch {
      try {
        head.setMood("neutral");
      } catch {
        /* ignore */
      }
    }

    const morph = EXPRESSION_MORPH[emotion] ?? {};
    const trySet = (name: string, val: number) => {
      try {
        head.setValue(name, val, 180);
      } catch {
        /* morph 可能不存在 */
      }
    };
    trySet("browInnerUp", morph.browInnerUp ?? 0);
    trySet("eyeSquintLeft", morph.eyeSquint ?? 0);
    trySet("eyeSquintRight", morph.eyeSquint ?? 0);
    trySet("mouthSmile", morph.mouthSmile ?? 0);
    trySet("eyesClosed", morph.eyesClosed ?? 0);
  }, [emotion]);

  // 音量 → 平滑口型（攻击快、衰减慢）
  useEffect(() => {
    const head = headRef.current;
    if (!head) return;

    const target = mapAudioToMouth(audioLevel, speaking);
    const tick = () => {
      const cur = mouthSmoothRef.current;
      const attack = 0.45;
      const release = 0.18;
      const k = target > cur ? attack : release;
      const next = cur + (target - cur) * k;
      mouthSmoothRef.current = Math.abs(next - target) < 0.008 ? target : next;
      try {
        const open = mouthSmoothRef.current;
        head.setValue("mouthOpen", open, 30);
        head.setValue("jawOpen", open * 0.55, 30);
        if (speaking && open > 0.2) {
          head.setValue("mouthSmile", Math.min(0.25, open * 0.2), 40);
        }
      } catch {
        /* morph 可能尚未就绪 */
      }
      if (speaking || mouthSmoothRef.current > 0.01) {
        rafRef.current = requestAnimationFrame(tick);
      }
    };
    cancelAnimationFrame(rafRef.current);
    rafRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafRef.current);
  }, [audioLevel, speaking]);

  return <div ref={mountRef} className="absolute inset-0" />;
}

function webglSupported(): boolean {
  if (typeof window === "undefined") return false;
  try {
    const canvas = document.createElement("canvas");
    return Boolean(
      canvas.getContext("webgl") || canvas.getContext("experimental-webgl"),
    );
  } catch {
    return false;
  }
}

export const talkingheadRenderer: AvatarRendererDef = {
  id: "3d-head",
  isSupported: webglSupported,
  Component: TalkingHeadRenderer,
  prefetch(avatarId: string): void {
    if (typeof window === "undefined") return;
    const profile = AVATAR_ASSETS[avatarId] || AVATAR_ASSETS.professional_male;
    if (!profile) return;
    const link = document.createElement("link");
    link.rel = "prefetch";
    link.as = "fetch";
    link.href = profile.url;
    link.crossOrigin = "anonymous";
    document.head.appendChild(link);
  },
};

export type { AvatarExpression };
