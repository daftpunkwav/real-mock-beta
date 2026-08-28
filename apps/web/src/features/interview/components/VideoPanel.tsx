"use client";

import { useEffect, useState, useRef, forwardRef, useImperativeHandle, useCallback } from "react";
import { Video, VideoOff, Mic, MicOff } from "lucide-react";
import type { FaceAnalysis as BaseFaceAnalysis } from "@/types";
import { cn } from "@/lib/utils";

/** VideoPanel 内部使用的扩展版人脸分析字段，保持向后兼容。 */
export interface FaceAnalysis extends BaseFaceAnalysis {
  face_detected: boolean;
  looking_away: boolean;
  nervousness: number;
  face_count: number;
}

export interface VideoPanelHandle {
  /** 截取当前视频帧，返回 JPEG base64（不含 data URL 前缀） */
  captureFrame: () => string | null;
}

interface VideoPanelProps {
  onFaceAnalysis?: (analysis: FaceAnalysis) => void;
  enabled: boolean;
  micActive?: boolean;
  voiceStatus?: string;
  /** light 用于普通页面；dark 用于面试房间 */
  variant?: "light" | "dark";
  className?: string;
}

export const VideoPanel = forwardRef<VideoPanelHandle, VideoPanelProps>(
  function VideoPanel(
    {
      onFaceAnalysis,
      enabled,
      micActive = false,
      voiceStatus = "未开启",
      variant = "light",
      className,
    },
    ref,
  ) {
    const videoRef = useRef<HTMLVideoElement>(null);
    const canvasRef = useRef<HTMLCanvasElement>(null);
    const [cameraOn, setCameraOn] = useState(false);
    const streamRef = useRef<MediaStream | null>(null);
    const faceDetectorRef = useRef<BrowserFaceDetector | null>(null);
    const acquiringRef = useRef(false);
    const [faceStatus, setFaceStatus] = useState<string>("未检测");
    const jitterHistory = useRef<number[]>([]);
    // FaceDetector 不可用时：只上报一次 face_detected:false，避免每 3s 假数据刷新
    const detectorUnavailableReportedRef = useRef(false);
    const isDark = variant === "dark";

    useImperativeHandle(ref, () => ({
      captureFrame: () => {
        const video = videoRef.current;
        const canvas = canvasRef.current;
        if (!video || !canvas || !cameraOn || video.readyState < 2) return null;
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        const ctx = canvas.getContext("2d");
        if (!ctx) return null;
        ctx.drawImage(video, 0, 0);
        const dataUrl = canvas.toDataURL("image/jpeg", 0.7);
        return dataUrl.split(",")[1] || null;
      },
    }));

    const startCamera = async () => {
      if (acquiringRef.current) return;
      acquiringRef.current = true;
      try {
        // 先停旧流，避免并发 getUserMedia 泄漏
        streamRef.current?.getTracks().forEach((t) => t.stop());
        streamRef.current = null;
        const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
        if (!acquiringRef.current) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        streamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
        }
        // 重置「不可用已上报」标记，允许新会话重新检测
        detectorUnavailableReportedRef.current = false;
        setCameraOn(true);

        if ("FaceDetector" in window) {
          try {
            faceDetectorRef.current = new window.FaceDetector({ fastMode: true, maxDetectedFaces: 1 });
          } catch {
            faceDetectorRef.current = null;
          }
        }
      } catch {
        setFaceStatus("摄像头权限被拒绝");
      } finally {
        acquiringRef.current = false;
      }
    };

    const stopCamera = () => {
      acquiringRef.current = false;
      streamRef.current?.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
      if (videoRef.current) {
        videoRef.current.srcObject = null;
      }
      faceDetectorRef.current = null;
      setCameraOn(false);
      setFaceStatus("未检测");
    };

    const toggleCamera = () => {
      if (cameraOn) stopCamera();
      else void startCamera();
    };

    useEffect(() => {
      if (enabled) void startCamera();
      return () => stopCamera();
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [enabled]);

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
    }, [cameraOn, onFaceAnalysis]);

    useEffect(() => {
      if (!cameraOn || !enabled) return;
      const interval = setInterval(() => {
        analyzeFace();
      }, 3000);
      return () => clearInterval(interval);
    }, [cameraOn, enabled, analyzeFace]);

    useEffect(() => {
      return () => {
        stopCamera();
      };
    }, []);

    if (!enabled) return null;

    return (
      <div
        className={cn(
          "rounded-xl overflow-hidden flex flex-col h-full min-h-0",
          isDark
            ? "border border-white/10 bg-black/40"
            : "border border-[var(--border)] bg-black/5",
          className,
        )}
      >
        <div className="relative flex-1 min-h-0 bg-gray-950">
          <video
            ref={videoRef}
            autoPlay
            muted
            playsInline
            className={cn(
              "w-full h-full object-cover",
              cameraOn ? "" : "hidden",
            )}
            style={{ transform: "scaleX(-1)" }}
          />
          {!cameraOn && (
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 text-gray-500 text-sm">
              <VideoOff size={28} className="opacity-50" />
              <span>摄像头未开启</span>
            </div>
          )}
          {/* 悬浮状态条 */}
          <div className="absolute bottom-0 inset-x-0 p-2.5 bg-gradient-to-t from-black/70 via-black/30 to-transparent">
            <div className="flex items-center justify-between gap-2">
              <div className="min-w-0 flex-1">
                <p className="text-[11px] text-white/80 truncate">{faceStatus}</p>
                <p
                  className={cn(
                    "text-[11px] truncate flex items-center gap-1 mt-0.5",
                    micActive ? "text-emerald-300" : "text-white/50",
                  )}
                >
                  {micActive ? <Mic size={11} /> : <MicOff size={11} />}
                  {micActive ? voiceStatus : "等待你的回合…"}
                </p>
              </div>
              <button
                type="button"
                onClick={toggleCamera}
                className={cn(
                  "shrink-0 p-2 rounded-full transition-colors",
                  cameraOn
                    ? "bg-white/15 text-white hover:bg-white/25"
                    : "bg-white/10 text-gray-400 hover:bg-white/15",
                )}
                title={cameraOn ? "关闭摄像头" : "开启摄像头"}
              >
                {cameraOn ? <Video size={16} /> : <VideoOff size={16} />}
              </button>
            </div>
          </div>
          <canvas ref={canvasRef} className="hidden" />
        </div>
      </div>
    );
  },
);

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
