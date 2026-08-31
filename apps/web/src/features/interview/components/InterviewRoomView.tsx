"use client";

import { AlertTriangle, WifiOff } from "lucide-react";
import { VideoPanel } from "./VideoPanel";
import { InterviewRoomGate } from "./InterviewRoomGate";
import { InterviewRoomChrome } from "./InterviewRoomChrome";
import { InterviewRoomChat } from "./InterviewRoomChat";
import { InterviewRoomOutline } from "./InterviewRoomOutline";
import type { InterviewRoomModel } from "../hooks/useInterviewRoom";

export function InterviewRoomView({ room }: { room: InterviewRoomModel }) {
  const {
    sessionIdValid,
    tokenMissing,
    goSetup,
    everConnected,
    connectionState,
    retryNow,
    videoRef,
    isRecording,
    voiceStatus,
    handleFaceAnalysis,
  } = room;

  if (!sessionIdValid) {
    return (
      <InterviewRoomGate
        icon={<AlertTriangle size={24} />}
        title="无效的会话 ID"
        desc="请从「面试配置」页重新开始一场面试。"
        tone="warning"
        onPrimary={goSetup}
        primaryLabel="返回配置页"
      />
    );
  }

  if (tokenMissing) {
    return (
      <InterviewRoomGate
        icon={<AlertTriangle size={24} />}
        title="会话无效或无权访问"
        desc="请从「面试配置」页重新开始一场面试。直接打开历史链接可能缺少能力令牌 Cookie。"
        tone="warning"
        onPrimary={goSetup}
        primaryLabel="返回配置页"
      />
    );
  }

  if (!everConnected && connectionState === "failed") {
    return (
      <InterviewRoomGate
        icon={<WifiOff size={24} />}
        title="无法连接到面试服务"
        desc="已尝试 5 次仍失败,请确认后端已启动(默认 :8081)或检查网络。"
        tone="danger"
        onPrimary={retryNow}
        primaryLabel="重新连接"
        onSecondary={goSetup}
        secondaryLabel="返回配置"
      />
    );
  }

  if (!everConnected && !room.connected) {
    return (
      <div className="h-screen flex flex-col items-center justify-center gap-3 bg-[var(--background)] text-ink-muted">
        <span className="block h-6 w-6 anim-spin rounded-full border-2 border-[var(--primary)] border-t-transparent" />
        <p className="text-[13px]">
          {connectionState === "reconnecting" ? "重新连接中…" : "连接面试服务…"}
        </p>
      </div>
    );
  }

  return (
    <div className="h-screen flex flex-col bg-[var(--background)] text-[var(--foreground)] relative">
      <InterviewRoomChrome room={room} />
      <div className="flex-1 grid grid-cols-1 lg:grid-cols-[minmax(280px,1fr)_minmax(0,1.8fr)] gap-2 p-2 min-h-0 overflow-hidden">
        <div className="grid grid-rows-[minmax(140px,0.9fr)_minmax(180px,1.1fr)] lg:grid-rows-[1.618fr_1fr] gap-2 min-h-0 order-2 lg:order-1">
          <VideoPanel
            ref={videoRef}
            enabled
            variant="dark"
            micActive={isRecording}
            voiceStatus={voiceStatus}
            onFaceAnalysis={handleFaceAnalysis}
          />
          <InterviewRoomChat room={room} />
        </div>
        <InterviewRoomOutline room={room} />
      </div>
    </div>
  );
}
