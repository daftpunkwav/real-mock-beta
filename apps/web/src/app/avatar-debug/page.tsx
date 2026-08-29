"use client";

import { notFound } from "next/navigation";
import { AvatarStage } from "@/features/avatar/AvatarStage";

const CASES = [
  { id: "professional_male", label: "专业男" },
  { id: "strict_expert", label: "严厉专家" },
  { id: "gentle_female", label: "温和女" },
] as const;

/** 用真实 AvatarStage 组件并排验证三人像（含 Strict Mode 竞态） */
export default function AvatarDebugPage() {
  if (process.env.NODE_ENV === "production") {
    notFound();
  }

  return (
    <div className="p-6 space-y-4">
      <h1 className="text-lg font-bold">Avatar 组件实机调试</h1>
      <p className="text-sm text-white/60">
        应看到 3D 人像；若出现「3D 人像加载失败」黄条则仍异常。Ctrl+Shift+R 强刷后再看。
      </p>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {CASES.map((c) => (
          <div key={c.id} className="space-y-2">
            <div className="text-sm font-medium">{c.label}</div>
            <div className="h-[320px] rounded-xl overflow-hidden border border-white/10">
              <AvatarStage avatarId={c.id} sceneId="meeting_room" emotion="neutral" />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
