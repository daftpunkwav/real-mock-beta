"use client";

import { useEffect, useRef } from "react";
import { AVATAR_ASSETS } from "./talkingheadAssets";
import { safeMood } from "./talkingheadMood";
import type { HeadInstance } from "./talkingheadTypes";

/** boot 阶段回调，与 AvatarRendererProps 的 onProgress/onReady/onFailed 同名契约。 */
export interface TalkingHeadBootCallbacks {
  onProgress?: (pct: number) => void;
  onReady?: () => void;
  onFailed?: (err: unknown) => void;
}

/**
 * 3D 头像 boot/teardown：动态 import + Strict Mode 双挂载保护 + 进度上报
 * + 进房后视线锁定。返回挂载节点与实例句柄，供 gaze/emotion/mouth 复用。
 * 本文件仍是唯一允许 import @met4citizen/talkinghead 的边界。
 */
export function useTalkingHeadBoot(
  avatarId: string,
  { onProgress, onReady, onFailed }: TalkingHeadBootCallbacks,
) {
  const mountRef = useRef<HTMLDivElement>(null);
  const headRef = useRef<HeadInstance | null>(null);
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

  return { mountRef, headRef };
}
