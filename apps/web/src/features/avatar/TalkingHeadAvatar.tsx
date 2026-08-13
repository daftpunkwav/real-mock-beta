"use client";

import { useEffect, useRef, useState } from "react";
import { InterviewerAvatar } from "@/features/avatar/InterviewerAvatar";
import { Loader2 } from "lucide-react";

/** TalkingHead 内置 mood；传入其它值（如 serious）会在 showAvatar 内抛 Unknown mood */
const VALID_MOODS = new Set([
  "neutral",
  "happy",
  "angry",
  "sad",
  "fear",
  "disgust",
  "love",
  "sleep",
] as const);

type TalkingMood = "neutral" | "happy" | "angry" | "sad" | "fear" | "disgust" | "love" | "sleep";

function safeMood(mood: string | undefined, fallback: TalkingMood = "neutral"): TalkingMood {
  if (mood && VALID_MOODS.has(mood as TalkingMood)) return mood as TalkingMood;
  return fallback;
}

/**
 * 同源 GLB（见 public/avatars/）。
 * 男模：TalkingHead 示例 avatarsdk.glb（body M）；女模：brunette.glb。
 * mood 必须是 TalkingHead 内置名（无 serious），否则 showAvatar 会抛 Unknown mood。
 */
const AVATAR_URLS: Record<
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

/** 预取当前人像 GLB，缩短进房等待 */
export function prefetchAvatarGlb(avatarId: string): void {
  if (typeof window === "undefined") return;
  const profile = AVATAR_URLS[avatarId] || AVATAR_URLS.professional_male;
  if (!profile) return;
  const link = document.createElement("link");
  link.rel = "prefetch";
  link.as = "fetch";
  link.href = profile.url;
  link.crossOrigin = "anonymous";
  document.head.appendChild(link);
}

const SCENE_IMG: Record<string, string> = {
  meeting_room: "/scenes/meeting_room.svg",
  glass_office: "/scenes/glass_office.svg",
  online_interview: "/scenes/online_interview.svg",
  boardroom: "/scenes/boardroom.svg",
  startup_loft: "/scenes/startup_loft.svg",
  library_corner: "/scenes/library_corner.svg",
};

const SCENE_FALLBACK: Record<string, string> = {
  meeting_room: "linear-gradient(160deg, #0f172a 0%, #1e3a5f 55%, #0b1220 100%)",
  glass_office: "linear-gradient(160deg, #111827 0%, #1f2937 50%, #0f172a 100%)",
  online_interview: "linear-gradient(160deg, #020617 0%, #1e293b 60%, #0f172a 100%)",
  boardroom: "linear-gradient(160deg, #1c1917 0%, #44403c 50%, #0c0a09 100%)",
  startup_loft: "linear-gradient(160deg, #292524 0%, #57534e 45%, #1c1917 100%)",
  library_corner: "linear-gradient(160deg, #1e1b4b 0%, #312e81 50%, #0f172a 100%)",
};

/** 情绪 → TalkingHead mood（仅使用库内存在的键；serious 映射为 neutral） */
const EMOTION_TO_MOOD: Record<string, TalkingMood> = {
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

/** 情绪 → 辅助 morph（眉/眼/嘴角），mood 不够细时补一层 */
const EMOTION_MORPH: Record<
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

interface TalkingHeadAvatarProps {
  avatarId: string;
  sceneId: string;
  emotion?: string;
  speaking?: boolean;
  audioLevel?: number;
}

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

/**
 * TalkingHead 3D 面试官：Edge TTS 音量驱动口型；WebGL 失败时回退 CSS 矢量人像。
 */
export function TalkingHeadAvatar({
  avatarId,
  sceneId,
  emotion = "neutral",
  speaking = false,
  audioLevel = 0,
}: TalkingHeadAvatarProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const headRef = useRef<HeadInstance | null>(null);
  const mouthSmoothRef = useRef(0);
  const rafRef = useRef<number>(0);
  const bootGenRef = useRef(0);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [loadPct, setLoadPct] = useState(0);

  useEffect(() => {
    const gen = ++bootGenRef.current;
    let cancelled = false;
    let head: HeadInstance | null = null;
    /** 每次 boot 独立挂载点，避免 Strict Mode 双挂载时 stop() 清掉下一次的 DOM */
    let mount: HTMLDivElement | null = null;

    setLoading(true);
    setFailed(false);
    setLoadPct(0);

    const boot = async () => {
      const node = containerRef.current;
      if (!node) return;
      try {
        const canvas = document.createElement("canvas");
        const gl = canvas.getContext("webgl") || canvas.getContext("experimental-webgl");
        if (!gl) throw new Error("no webgl");
      } catch {
        if (!cancelled && bootGenRef.current === gen) setFailed(true);
        return;
      }

      try {
        const mod = await import("@met4citizen/talkinghead");
        const TalkingHead = (mod as { TalkingHead: new (n: HTMLElement, o?: object) => HeadInstance }).TalkingHead;
        if (cancelled || !containerRef.current || bootGenRef.current !== gen) return;

        const profile = AVATAR_URLS[avatarId] || AVATAR_URLS.professional_male!;
        const mood = safeMood(profile.mood);
        mount = document.createElement("div");
        mount.style.cssText = "position:absolute;inset:0;width:100%;height:100%;";
        containerRef.current.replaceChildren(mount);

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
            if (bootGenRef.current === gen) {
              setLoadPct(Math.min(100, Math.max(0, raw)));
            }
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
        const lockGaze = () => {
          try {
            head?.setBaselineValue?.("eyesLookDown", 0);
            head?.setFixedValue?.("eyesLookDown", 0, 200);
            head?.setValue("eyesLookDown", 0, 200);
            head?.setValue("eyesLookUp", 0.08, 200);
            head?.setValue("headRotateX", 0.1, 300);
            head?.lookAtCamera?.(1500);
            head?.makeEyeContact?.(3000);
          } catch {
            /* ignore */
          }
        };
        lockGaze();
        setLoading(false);
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        console.warn("TalkingHead 加载失败，回退 CSS 人像", avatarId, msg, err);
        if (!cancelled && bootGenRef.current === gen) {
          setFailed(true);
          setLoading(false);
        }
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
  }, [avatarId]);

  // 说话时周期性看向镜头，避免长时间低头/瞟向别处
  useEffect(() => {
    const head = headRef.current;
    if (!head || failed || loading) return;
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
  }, [speaking, failed, loading, emotion]);

  // 情绪 → mood + 辅助 morph
  useEffect(() => {
    const head = headRef.current;
    if (!head || failed) return;
    const mood = safeMood(EMOTION_TO_MOOD[emotion], "neutral");
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

    const morph = EMOTION_MORPH[emotion] || {};
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
  }, [emotion, failed]);

  // 音量 → 平滑口型（攻击快、衰减慢）
  useEffect(() => {
    const head = headRef.current;
    if (!head || failed || loading) return;

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
  }, [audioLevel, speaking, failed, loading]);

  if (failed) {
    return (
      <div className="relative w-full h-full min-h-[180px]">
        <InterviewerAvatar
          avatarId={avatarId}
          sceneId={sceneId}
          emotion={emotion}
          speaking={speaking}
          audioLevel={audioLevel}
        />
        <div className="absolute bottom-2 left-2 right-2 z-10 rounded-md bg-black/65 px-2 py-1.5 text-[11px] text-amber-200/95 text-center">
          3D 人像加载失败，已回退平面形象
        </div>
      </div>
    );
  }

  const bg = SCENE_FALLBACK[sceneId] || SCENE_FALLBACK.meeting_room;
  const sceneImg = SCENE_IMG[sceneId] || SCENE_IMG.meeting_room;

  return (
    <div
      className="relative w-full h-full min-h-[180px] rounded-xl overflow-hidden border border-white/10"
      style={{ background: bg }}
    >
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={sceneImg}
        alt=""
        className="absolute inset-0 w-full h-full object-cover opacity-85 pointer-events-none"
      />
      <div ref={containerRef} className="absolute inset-0" />
      {loading && (
        <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-2 bg-black/50 text-white/80 text-xs">
          <Loader2 className="animate-spin text-brand-400" size={22} />
          <span>加载 3D 面试官…{loadPct > 0 ? ` ${loadPct}%` : ""}</span>
          <span className="text-white/40">不阻塞进房与麦克风</span>
        </div>
      )}
    </div>
  );
}
