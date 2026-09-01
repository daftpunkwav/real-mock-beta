"use client";

import { useEffect } from "react";
import type { RefObject } from "react";
import type { AvatarExpression } from "../contract";
import { EXPRESSION_MORPH, EXPRESSION_TO_MOOD } from "./talkingheadMood";
import type { HeadInstance } from "./talkingheadTypes";

/** 表情 → 库内心境 + 辅助 morph（眉/眼/嘴角）；未知值回落 neutral。 */
export function useTalkingHeadEmotion(
  headRef: RefObject<HeadInstance | null>,
  emotion: AvatarExpression,
) {
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
    // headRef 为稳定的 useRef 对象引用，加入依赖仅用于满足 exhaustive-deps
  }, [emotion, headRef]);
}
