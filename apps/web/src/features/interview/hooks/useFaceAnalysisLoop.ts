"use client";

import { useCallback, useEffect, useRef } from "react";
import type { Dispatch, RefObject, SetStateAction } from "react";
import type { FaceAnalysis as BaseFaceAnalysis } from "@/types";

/** VideoPanel 内部使用的扩展版人脸分析字段，保持向后兼容。 */
export interface FaceAnalysis extends BaseFaceAnalysis {
  face_detected: boolean;
  looking_away: boolean;
  nervousness: number;
  face_count: number;
}

interface DetectedFace {
  boundingBox: { x: number; y: number; width: number; height: number };
}

interface BrowserFaceDetector {
  detect(source: HTMLVideoElement): Promise<DetectedFace[]>;
}

interface FaceDetectorOptions {
  fastMode?: boolean;
  maxDetectedFaces?: number;
}

declare global {
  interface Window {
    FaceDetector: new (options?: FaceDetectorOptions) => BrowserFaceDetector;
  }
}

interface UseFaceAnalysisLoopOptions {
  videoRef: RefObject<HTMLVideoElement | null>;
  cameraOn: boolean;
  enabled: boolean;
  onFaceAnalysis?: (analysis: FaceAnalysis) => void;
  setFaceStatus: Dispatch<SetStateAction<string>>;
}

/**
 * 人脸分析循环 hook：定时调用浏览器 FaceDetector，产出 looking_away / nervousness（jitter）
 * 并回调 onFaceAnalysis。FaceDetector 不可用时只上报一次 face_detected:false。
 * 摄像头开/关时同步检测器生命周期（开启重建、关闭清空）。
 */
export function useFaceAnalysisLoop({
  videoRef,
  cameraOn,
  enabled,
  onFaceAnalysis,
  setFaceStatus,
}: UseFaceAnalysisLoopOptions) {
  const faceDetectorRef = useRef<BrowserFaceDetector | null>(null);
  const jitterHistory = useRef<number[]>([]);
  // FaceDetector 不可用时：只上报一次 face_detected:false，避免每 3s 假数据刷新
  const detectorUnavailableReportedRef = useRef(false);

  // 摄像头开/关时重建检测器，并重置「不可用已上报」标记，允许新会话重新检测
  useEffect(() => {
    if (!cameraOn) {
      faceDetectorRef.current = null;
      return;
    }
    detectorUnavailableReportedRef.current = false;
    if ("FaceDetector" in window) {
      try {
        faceDetectorRef.current = new window.FaceDetector({ fastMode: true, maxDetectedFaces: 1 });
      } catch {
        faceDetectorRef.current = null;
      }
    }
    return () => {
      faceDetectorRef.current = null;
    };
  }, [cameraOn]);

  const analyzeFace = useCallback(async () => {
    const video = videoRef.current;
    if (!video || !cameraOn || video.readyState < 2) return;

    const analysis: FaceAnalysis = {
      face_detected: false,
      looking_away: true,
      nervousness: 0,
      face_count: 0,
    };

    if (faceDetectorRef.current) {
      try {
        const faces = await faceDetectorRef.current.detect(video);
        analysis.face_count = faces.length;
        analysis.face_detected = faces.length > 0;

        if (faces.length > 0) {
          const face = faces[0]?.boundingBox;
          if (face) {
            const cx = face.x + face.width / 2;
            const cy = face.y + face.height / 2;
            const vcx = video.videoWidth / 2;
            const vcy = video.videoHeight / 2;
            const offset = Math.hypot(cx - vcx, cy - vcy) / Math.hypot(vcx, vcy);
            analysis.looking_away = offset > 0.35;
            jitterHistory.current.push(offset);
            if (jitterHistory.current.length > 8) jitterHistory.current.shift();
            if (jitterHistory.current.length >= 3) {
              const avg =
                jitterHistory.current.reduce((a, b) => a + b, 0) /
                jitterHistory.current.length;
              const variance =
                jitterHistory.current.reduce((s, v) => s + (v - avg) ** 2, 0) /
                jitterHistory.current.length;
              analysis.nervousness = Math.min(1, variance * 20);
            }
          } else {
            jitterHistory.current.push(0);
            if (jitterHistory.current.length > 8) jitterHistory.current.shift();
          }
          setFaceStatus(
            analysis.looking_away
              ? "已检测人脸 · 未看镜头"
              : analysis.nervousness > 0.5
                ? "已检测人脸 · 略显紧张"
                : "已检测人脸 · 状态正常",
          );
        } else {
          setFaceStatus("未检测到人脸");
        }
      } catch {
        setFaceStatus("面部分析暂时不可用");
      }
      onFaceAnalysis?.(analysis);
    } else {
      // FaceDetector 不可用：仅上报一次 face_detected:false，后续静默，不假装检测到人脸
      if (!detectorUnavailableReportedRef.current) {
        detectorUnavailableReportedRef.current = true;
        setFaceStatus("摄像头已开启（浏览器不支持人脸检测 API）");
        onFaceAnalysis?.(analysis); // face_detected: false
      }
    }
  }, [cameraOn, onFaceAnalysis, videoRef, setFaceStatus]);

  useEffect(() => {
    if (!cameraOn || !enabled) return;
    const interval = setInterval(() => {
      analyzeFace();
    }, 3000);
    return () => clearInterval(interval);
  }, [cameraOn, enabled, analyzeFace]);

  return {};
}
