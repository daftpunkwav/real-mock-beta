"use client";

import { FileText } from "lucide-react";

/** 简历管理页头。 */
export function ResumePageHead() {
  return (
    <div className="page-header">
      <div className="flex items-start gap-3">
        <span className="icon-badge icon-badge-success">
          <FileText size={18} strokeWidth={1.75} />
        </span>
        <div>
          <p className="page-eyebrow">Resume</p>
          <h1 className="page-title">简历管理</h1>
          <p className="page-desc">
            PDF · Word · Markdown · TXT。AI 解析为职业知识档案并给出深度评价。
          </p>
        </div>
      </div>
    </div>
  );
}
