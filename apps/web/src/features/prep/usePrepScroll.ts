"use client";

/** prep 对话区滚动：默认贴底跟随，上滑后以用户为准。 */

import { useCallback, useEffect, useRef, useState } from "react";

/** 距底多少像素内视为「贴着底部」,自动跟随滚动 */
export const FOLLOW_THRESHOLD_PX = 96;

export function usePrepScroll(messagesLength: number) {
  const [showJump, setShowJump] = useState(false);
  const chatScrollRef = useRef<HTMLDivElement>(null);
  const followRef = useRef(true);

  const handleScroll = useCallback(() => {
    const el = chatScrollRef.current;
    if (!el) return;
    const atBottom =
      el.scrollHeight - el.scrollTop - el.clientHeight < FOLLOW_THRESHOLD_PX;
    followRef.current = atBottom;
    setShowJump(!atBottom);
  }, []);

  useEffect(() => {
    if (!followRef.current) return;
    const el = chatScrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messagesLength]);

  const jumpToBottom = useCallback(() => {
    followRef.current = true;
    setShowJump(false);
    const el = chatScrollRef.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, []);

  const stickToBottom = useCallback(() => {
    followRef.current = true;
    setShowJump(false);
  }, []);

  return {
    showJump,
    chatScrollRef,
    followRef,
    handleScroll,
    jumpToBottom,
    stickToBottom,
  };
}
