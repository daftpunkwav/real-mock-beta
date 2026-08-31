"use client";

import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";
import { Mic, MicOff, Video, VideoOff } from "lucide-react";
import { cn } from "@/lib/utils";
import { useCameraStream } from "../hooks/useCameraStream";
import { useFaceAnalysisLoop } from "../hooks/useFaceAnalysisLoop";
import type { FaceAnalysis } from "../hooks/useFaceAnalysisLoop";

export type { FaceAnalysis };

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
    const [faceStatus, setFaceStatus] = useState<string>("未检测");
    const isDark = variant === "dark";

    const { cameraOn, startCamera, stopCamera, toggleCamera } = useCameraStream(
      videoRef,
      setFaceStatus,
    );
    useFaceAnalysisLoop({ videoRef, cameraOn, enabled, onFaceAnalysis, setFaceStatus });

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

    useEffect(() => {
      if (enabled) void startCamera();
      return () => stopCamera();
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [enabled]);

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
