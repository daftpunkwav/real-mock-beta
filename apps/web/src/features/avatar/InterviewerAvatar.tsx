"use client";

import { useEffect, useState } from "react";
import { AVATAR_PROFILES } from "./avatarProfiles";
import { SCENE_FALLBACK, SCENES } from "./avatarScenes";

interface InterviewerAvatarProps {
  avatarId: string;
  sceneId: string;
  emotion?: string;
  speaking?: boolean;
  /** 0–1 实时音量，优先于随机口型 */
  audioLevel?: number;
  onAudioLevel?: (level: number) => void;
}

/**
 * 拟真面试官人像：场景背景 + 精细半身像 + 口型/眨眼/情绪联动。
 * 口型优先跟随 TTS 音量电平；WebGL 数字人可后续替换且保持同一 props。
 */
export function InterviewerAvatar({
  avatarId,
  sceneId,
  emotion = "neutral",
  speaking = false,
  audioLevel = 0,
}: InterviewerAvatarProps) {
  const [mouthOpen, setMouthOpen] = useState(0);
  const [blink, setBlink] = useState(1);
  const profile = AVATAR_PROFILES[avatarId] || AVATAR_PROFILES.professional_male!;

  useEffect(() => {
    if (!speaking) {
      setMouthOpen(0);
      return;
    }
    // 低电平强制闭嘴，不再随机张嘴
    if (audioLevel < 0.03) {
      setMouthOpen(0);
      return;
    }
    const shaped = Math.pow(Math.min(1, (audioLevel - 0.03) / 0.75), 0.85);
    setMouthOpen(Math.min(0.95, 0.12 + shaped * 0.88));
  }, [speaking, audioLevel]);

  // 自然眨眼
  useEffect(() => {
    let timeout: ReturnType<typeof setTimeout>;
    const schedule = () => {
      timeout = setTimeout(() => {
        setBlink(0.08);
        setTimeout(() => {
          setBlink(1);
          schedule();
        }, 120);
      }, 2800 + Math.random() * 3200);
    };
    schedule();
    return () => clearTimeout(timeout);
  }, []);

  const sceneBg = SCENE_FALLBACK[sceneId] || SCENE_FALLBACK.meeting_room;
  const sceneImg = SCENES[sceneId] || SCENES.meeting_room;

  const browY =
    emotion === "serious" || emotion === "angry"
      ? 3
      : emotion === "curious"
        ? -2
        : emotion === "smile" || emotion === "happy" || emotion === "encouraging"
          ? -1
          : emotion === "concerned" || emotion === "sad"
            ? 1.5
            : 0;
  const eyeSquint =
    emotion === "smile" || emotion === "happy" || emotion === "encouraging" ? 0.85 : 1;
  const mouthBase =
    emotion === "smile" || emotion === "happy"
      ? 0.35
      : emotion === "serious" || emotion === "angry"
        ? 0.04
        : emotion === "encouraging"
          ? 0.25
          : 0.12;
  const mouthH = speaking ? 6 + mouthOpen * 14 : 4 + mouthBase * 8;
  const mouthW = speaking ? 22 + mouthOpen * 6 : 20;
  const cheekOpacity =
    emotion === "smile" || emotion === "happy" || emotion === "encouraging" ? 0.35 : 0.12;

  return (
    <div className="relative w-full h-full overflow-hidden rounded-xl" style={{ background: sceneBg }}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={sceneImg} alt="" className="absolute inset-0 w-full h-full object-cover opacity-90" />
      <div className="absolute inset-0 opacity-15 bg-[url('/scenes/pattern.svg')] bg-cover" />
      {/* 柔光 */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          background:
            "radial-gradient(ellipse 60% 50% at 50% 70%, rgba(255,255,255,0.12) 0%, transparent 70%)",
        }}
      />

      {/* 半身像区域 */}
      <div className="absolute bottom-0 left-1/2 -translate-x-1/2 w-[min(100%,340px)] h-[88%] flex flex-col items-center justify-end">
        <svg
          viewBox="0 0 200 260"
          className="w-full h-full drop-shadow-2xl"
          style={{
            filter: emotion === "serious" ? "saturate(0.85) contrast(1.05)" : undefined,
          }}
          aria-label={profile.label}
        >
          {/* 肩膀/西装 */}
          <ellipse cx="100" cy="250" rx="88" ry="48" fill={profile.suit} />
          <path
            d="M40 220 Q100 200 160 220 L170 260 L30 260 Z"
            fill={profile.suit}
          />
          {/* 衬衫领 */}
          <path d="M78 210 L100 235 L122 210 L115 248 L85 248 Z" fill={profile.shirt} />
          <rect x="96" y="220" width="8" height="30" rx="1" fill={profile.accent} opacity={0.85} />

          {/* 脖子 */}
          <rect x="88" y="145" width="24" height="32" rx="6" fill={profile.skin} />

          {/* 头部阴影与立体感 */}
          <ellipse cx="100" cy="100" rx="52" ry="58" fill={profile.skin} />
          <ellipse cx="100" cy="108" rx="40" ry="48" fill="#000" opacity={0.06} />

          {/* 头发 — 分层更细 */}
          {profile.gender === "female" ? (
            <>
              <ellipse cx="100" cy="72" rx="54" ry="42" fill={profile.hair} />
              <path d="M48 90 Q40 140 55 180 Q70 150 72 100 Z" fill={profile.hair} />
              <path d="M152 90 Q160 140 145 180 Q130 150 128 100 Z" fill={profile.hair} />
              <path d="M55 55 Q100 28 145 55 Q140 85 100 76 Q60 85 55 55 Z" fill={profile.hair} />
              <path d="M70 48 Q100 38 130 48" stroke="#000" strokeWidth="3" opacity={0.12} fill="none" />
            </>
          ) : (
            <>
              <path
                d="M46 98 Q48 42 100 36 Q152 42 154 98 Q148 68 100 64 Q52 68 46 98 Z"
                fill={profile.hair}
              />
              <ellipse cx="100" cy="58" rx="48" ry="26" fill={profile.hair} />
              <path d="M55 70 Q100 52 145 70" stroke="#000" strokeWidth="2" opacity={0.15} fill="none" />
            </>
          )}

          {/* 眉毛 */}
          <path
            d={`M68 ${78 + browY} Q80 ${72 + browY} 90 ${78 + browY}`}
            stroke={profile.hair}
            strokeWidth="2.8"
            fill="none"
            strokeLinecap="round"
          />
          <path
            d={`M110 ${78 + browY} Q120 ${72 + browY} 132 ${78 + browY}`}
            stroke={profile.hair}
            strokeWidth="2.8"
            fill="none"
            strokeLinecap="round"
          />

          {/* 眼睛 — 更立体 */}
          <ellipse cx="80" cy="95" rx="10" ry={7.5 * blink * eyeSquint} fill="#fff" />
          <ellipse cx="120" cy="95" rx="10" ry={7.5 * blink * eyeSquint} fill="#fff" />
          <ellipse cx="80" cy="95" rx="5" ry={5 * blink * eyeSquint} fill="#1e293b" />
          <ellipse cx="120" cy="95" rx="5" ry={5 * blink * eyeSquint} fill="#1e293b" />
          <circle cx="82" cy={93} r={1.8 * blink} fill="#fff" opacity={0.95} />
          <circle cx="122" cy={93} r={1.8 * blink} fill="#fff" opacity={0.95} />
          <path
            d={`M70 ${88 - (1 - blink) * 4} Q80 ${86 - (1 - blink) * 4} 90 ${88 - (1 - blink) * 4}`}
            stroke={profile.hair}
            strokeWidth="1.2"
            fill="none"
            opacity={0.35}
          />
          <path
            d={`M110 ${88 - (1 - blink) * 4} Q120 ${86 - (1 - blink) * 4} 130 ${88 - (1 - blink) * 4}`}
            stroke={profile.hair}
            strokeWidth="1.2"
            fill="none"
            opacity={0.35}
          />

          {/* 鼻子 */}
          <path
            d="M100 102 L97 118 Q100 123 103 118 Z"
            fill={profile.skin}
            stroke="#c9956c"
            strokeWidth="0.9"
            opacity={0.75}
          />

          {/* 脸颊 */}
          <ellipse cx="62" cy="115" rx="11" ry="7" fill="#e07a5f" opacity={cheekOpacity} />
          <ellipse cx="138" cy="115" rx="11" ry="7" fill="#e07a5f" opacity={cheekOpacity} />

          {/* 嘴 — 音量驱动 */}
          {emotion === "smile" && !speaking ? (
            <path
              d="M84 132 Q100 148 116 132"
              stroke="#b85c48"
              strokeWidth="2.8"
              fill="none"
              strokeLinecap="round"
            />
          ) : (
            <ellipse
              cx="100"
              cy="134"
              rx={mouthW / 2}
              ry={mouthH / 2}
              fill={speaking ? "#4a1f1f" : "#c47868"}
            />
          )}
          {speaking && mouthOpen > 0.35 && (
            <ellipse cx="100" cy="136" rx={mouthW / 3.2} ry={mouthH / 3.5} fill="#d48a8a" opacity={0.55} />
          )}
        </svg>
      </div>

      {/* 说话波纹 */}
      {speaking && (
        <div className="absolute bottom-6 left-1/2 -translate-x-1/2 flex gap-1 items-end h-6">
          {[0, 1, 2, 3, 4].map((i) => (
            <div
              key={i}
              className="w-1 rounded-full bg-white/70 animate-pulse"
              style={{
                height: `${8 + ((i + mouthOpen * 5) % 5) * 4}px`,
                animationDelay: `${i * 80}ms`,
              }}
            />
          ))}
        </div>
      )}

      <div className="absolute top-4 left-4 flex items-center gap-2">
        <span
          className="w-2 h-2 rounded-full"
          style={{ background: speaking ? "#22c55e" : profile.accent }}
        />
        <span className="text-white/90 text-sm font-medium drop-shadow">
          {profile.label}
        </span>
      </div>
      {emotion !== "neutral" && (
        <div className="absolute top-4 right-4 text-xs text-white/70 bg-black/30 px-2 py-0.5 rounded-full">
          {emotion === "smile" ? "友好" : emotion === "serious" ? "严肃" : emotion}
        </div>
      )}
    </div>
  );
}
