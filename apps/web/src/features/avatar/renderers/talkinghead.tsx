"use client";

import type { AvatarExpression, AvatarRendererDef, AvatarRendererProps } from "../contract";
import { AVATAR_ASSETS } from "./talkingheadAssets";
import { useTalkingHeadBoot } from "./talkingheadBoot";
import { useTalkingHeadEmotion } from "./talkingheadEmotion";
import { useTalkingHeadGaze } from "./talkingheadGaze";
import { useTalkingHeadMouth } from "./talkingheadMouth";
import { webglSupported } from "./talkingheadSupport";

/**
 * 3D 头像渲染通道：@met4citizen/talkinghead 适配器（组装层）。
 *
 * boot/teardown、视线锁定、表情 morph、口型 rAF 分别拆到同目录
 * talkingheadBoot / talkingheadGaze / talkingheadEmotion / talkingheadMouth；
 * 本文件只做 hook 组装 + 挂载 div + renderer 元数据，是唯一允许
 * import 该库的边界（动态 import 仍在 talkingheadBoot 内）。
 */

function TalkingHeadRenderer({
  avatarId,
  emotion,
  speaking,
  audioLevel,
  onProgress,
  onReady,
  onFailed,
}: AvatarRendererProps) {
  const { mountRef, headRef } = useTalkingHeadBoot(avatarId, { onProgress, onReady, onFailed });
  useTalkingHeadGaze(headRef, speaking);
  useTalkingHeadEmotion(headRef, emotion);
  useTalkingHeadMouth(headRef, audioLevel, speaking);

  return <div ref={mountRef} className="absolute inset-0" />;
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
