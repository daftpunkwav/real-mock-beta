"use client";

import { useCallback, useRef, useState } from "react";
import type { Dispatch, RefObject, SetStateAction } from "react";

/**
 * 摄像头采集 hook：负责 getUserMedia 生命周期（start/stop/toggle、防并发、先停旧轨）。
 * 不接触画面分析 / 录音 —— 那是 useFaceAnalysisLoop / useAudioRecorder 的职责。
 * @param videoRef 主组件持有的 <video> ref，stream 挂到其上。
 * @param setFaceStatus 摄像头相关的状态文案（权限被拒绝 / 未检测），由主组件持有。
 */
export function useCameraStream(
  videoRef: RefObject<HTMLVideoElement | null>,
  setFaceStatus: Dispatch<SetStateAction<string>>,
) {
  const [cameraOn, setCameraOn] = useState(false);
  const streamRef = useRef<MediaStream | null>(null);
  const acquiringRef = useRef(false);

  const startCamera = useCallback(async () => {
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
      setCameraOn(true);
    } catch {
      setFaceStatus("摄像头权限被拒绝");
    } finally {
      acquiringRef.current = false;
    }
  }, [videoRef, setFaceStatus]);

  const stopCamera = useCallback(() => {
    acquiringRef.current = false;
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
    setCameraOn(false);
    setFaceStatus("未检测");
  }, [videoRef, setFaceStatus]);

  const toggleCamera = useCallback(() => {
    if (cameraOn) stopCamera();
    else void startCamera();
  }, [cameraOn, startCamera, stopCamera]);

  return { cameraOn, startCamera, stopCamera, toggleCamera };
}
