"use client";

/** 面试状态分析卡。 */
export function FaceAnalysisCard({ summary }: { summary: string }) {
  return (
    <div className="surface-card mt-5 p-4">
      <h3 className="mb-2 text-[13px] font-semibold tracking-tight text-ink">
        面试状态分析
      </h3>
      <p className="text-[12.5px] leading-relaxed text-ink-muted">
        {summary}
      </p>
    </div>
  );
}
