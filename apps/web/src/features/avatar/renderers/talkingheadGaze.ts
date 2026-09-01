"use client";

import { useEffect } from "react";
import type { RefObject } from "react";
import type { HeadInstance } from "./talkingheadTypes";

/** 说话时周期性看向镜头；沉默期间歇归位，避免长时间低头/瞟向别处。 */
export function useTalkingHeadGaze(headRef: RefObject<HeadInstance | null>, speaking: boolean) {
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
    // headRef 为稳定的 useRef 对象引用，加入依赖仅用于满足 exhaustive-deps
  }, [speaking, headRef]);
}
