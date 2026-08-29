"use client";

import { useEffect } from "react";
import { InterviewerAvatar } from "../InterviewerAvatar";
import type { AvatarRendererDef, AvatarRendererProps } from "../contract";

/**
 * 平面形象渲染通道：CSS/SVG 矢量人像（无外部资源与 WebGL 依赖）。
 * 与 3D 通道同契约、同优先级参与通道选择，也作为 3D 加载失败的回退。
 */
function CssPortraitRenderer({
  avatarId,
  sceneId,
  emotion,
  speaking,
  audioLevel,
  onReady,
}: AvatarRendererProps) {
  useEffect(() => {
    onReady?.();
  }, [onReady]);

  return (
    <InterviewerAvatar
      avatarId={avatarId}
      sceneId={sceneId}
      emotion={emotion}
      speaking={speaking}
      audioLevel={audioLevel}
    />
  );
}

export const cssPortraitRenderer: AvatarRendererDef = {
  id: "css-portrait",
  isSupported: () => true,
  Component: CssPortraitRenderer,
};
