"use client";

import type { ComponentType } from "react";

type IconType = ComponentType<{ size?: number; className?: string; strokeWidth?: number }>;

/** 成长侧栏统计行：icon + label + value（档案页 PreviewRow 职责不同，独立维护）。 */
export function PreviewRow({
  icon: Icon,
  label,
  value,
}: {
  icon: IconType;
  label: string;
  value: string;
}) {
  return (
    <div className="flex items-start gap-2.5">
      <Icon size={13} className="mt-0.5 shrink-0 text-ink-subtle" strokeWidth={1.75} />
      <div className="min-w-0">
        <p className="text-[10px] uppercase leading-none tracking-[0.08em] text-ink-subtle">
          {label}
        </p>
        <p className="mt-1 text-[13px] font-medium text-ink">{value}</p>
      </div>
    </div>
  );
}
