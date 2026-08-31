"use client";

/** 模型下拉与思考强度选择。 */

import { memo } from "react";
import { Brain } from "lucide-react";
import type { ModelProfile, ReasoningEffort } from "@/types";

export const EFFORT_OPTIONS: { value: ReasoningEffort; label: string }[] = [
  { value: "low", label: "低" },
  { value: "medium", label: "中" },
  { value: "high", label: "高" },
  { value: "max", label: "最高" },
];

/** 模型下拉(value=条目 id;null=跟随默认处理器绑定,该绑定条目作为普通项出现并选中) */
export const ModelSelect = memo(function ModelSelect({
  models,
  value,
  onChange,
  disabled,
  className,
  ariaLabel,
  defaultProfile,
}: {
  models: ModelProfile[];
  value: number | null;
  onChange: (id: number | null) => void;
  disabled?: boolean;
  className?: string;
  ariaLabel: string;
  defaultProfile?: ModelProfile | null;
}) {
  const effectiveValue =
    value ?? (defaultProfile && models.some((m) => m.id === defaultProfile.id) ? defaultProfile.id : "");
  return (
    <select
      className={`field-select !h-9 !w-auto max-w-[210px] !py-0 text-[12px] ${className ?? ""}`}
      value={effectiveValue}
      onChange={(e) => onChange(e.target.value ? Number(e.target.value) : null)}
      disabled={disabled}
      aria-label={ariaLabel}
    >
      {!defaultProfile && <option value="">未设置</option>}
      {models.map((m) => (
        <option key={m.id} value={m.id}>
          {m.label}
        </option>
      ))}
    </select>
  );
});

/** 思考强度选择;模型未声明 reasoning 能力且非 forceVisible 时不渲染。
 * forceVisible 用于「默认模型」场景:后端会自动忽略不支持的强度参数。 */
export const EffortSelect = memo(function EffortSelect({
  model,
  value,
  onChange,
  disabled,
  forceVisible = false,
}: {
  model: ModelProfile | null;
  value: ReasoningEffort;
  onChange: (e: ReasoningEffort) => void;
  disabled?: boolean;
  forceVisible?: boolean;
}) {
  if (!forceVisible && !model?.capabilities.reasoning) return null;
  return (
    <div className="flex items-center gap-1">
      <Brain size={14} className="shrink-0 text-ink-subtle" />
      <select
        className="field-select !h-9 !w-auto !py-0 text-[12px]"
        value={value}
        onChange={(e) => onChange(e.target.value as ReasoningEffort)}
        disabled={disabled}
        aria-label="思考强度"
      >
        {EFFORT_OPTIONS.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </div>
  );
});
