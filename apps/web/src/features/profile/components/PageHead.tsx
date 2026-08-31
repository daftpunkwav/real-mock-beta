"use client";

import { User } from "lucide-react";

export function PageHead() {
  return (
    <div className="flex items-start gap-3">
      <span className="icon-badge">
        <User size={18} strokeWidth={1.75} />
      </span>
      <div>
        <p className="page-eyebrow">Profile</p>
        <h1 className="page-title">个人档案</h1>
        <p className="page-desc">本地存储,无需注册。必填信息用于生成更精准的面试问题。</p>
      </div>
    </div>
  );
}
