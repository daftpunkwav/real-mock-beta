"use client";

import { useEffect, useState } from "react";

/** 拟真面试官 2D 人像的实时表现参数（口型 / 眨眼）。 */
export interface InterviewerAvatarMotion {
  mouthOpen: number;
  blink: number;
}

/**
 * 2D 人像口型与眨眼：
 * - 口型优先跟随 TTS 音频电平（阈值 0.03、shaped 曲线与 3D 通道一致），
 *   低电平强制闭嘴，不再随机张嘴；
 * - 眨眼为 2.8–6s 随机间隔的独立循环。
 */
export function useInterviewerAvatarMotion(
  speaking: boolean,
  audioLevel: number,
): InterviewerAvatarMotion {
  const [mouthOpen, setMouthOpen] = useState(0);
  const [blink, setBlink] = useState(1);

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

  return { mouthOpen, blink };
}
