"use client";

import type { ComponentType } from "react";

/**
 * 人像渲染通道契约（纯类型，零实现依赖）。
 *
 * 页面与房间组件只依赖本契约与 <AvatarStage>；具体渲染实现（3D 头像 /
 * 平面形象 / 未来视频流）全部在 renderers/ 下以适配器接入，替换渲染通道
 * 不触碰任何调用方。
 */

/** 回合协议 emotion 字段的中性枚举（与后端 turn 协议一致）。 */
export const AVATAR_EXPRESSIONS = [
  "neutral",
  "smile",
  "serious",
  "curious",
  "encouraging",
  "skeptical",
  "concerned",
  "angry",
  "sad",
  "happy",
] as const;

export type AvatarExpression = (typeof AVATAR_EXPRESSIONS)[number];

/** 未知值安全回落 neutral（协议字段缺失/漂移时表情通道不中断）。 */
export function toAvatarExpression(value: string | undefined): AvatarExpression {
  return (AVATAR_EXPRESSIONS as readonly string[]).includes(value ?? "")
    ? (value as AvatarExpression)
    : "neutral";
}

export interface AvatarRendererProps {
  avatarId: string;
  /** 场景上下文（背景/环境由通道自行取舍；舞台只画加载遮罩） */
  sceneId: string;
  emotion: AvatarExpression;
  /** 是否正在播报（驱动口型与姿态） */
  speaking: boolean;
  /** 0–1 实时语音电平（口型驱动） */
  audioLevel: number;
  /** 资源加载进度 0–100（无加载过程的通道可不触发） */
  onProgress?(pct: number): void;
  /** 通道就绪、可以隐藏加载遮罩 */
  onReady?(): void;
  /** 通道加载失败，舞台将回退到下一优先级通道 */
  onFailed?(err: unknown): void;
}

export type AvatarRendererComponent = ComponentType<AvatarRendererProps>;

export interface AvatarRendererDef {
  /** 渲染通道标识（按能力命名，不含实现品牌） */
  id: string;
  /** 当前运行环境是否支持（WebGL 探测等；SSR 环境返回 false） */
  isSupported(): boolean;
  Component: AvatarRendererComponent;
  /** 可选：进房前预热人像资源 */
  prefetch?(avatarId: string): void;
}
