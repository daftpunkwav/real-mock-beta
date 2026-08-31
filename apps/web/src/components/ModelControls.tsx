"use client";

import { memo, useState } from "react";
import { Brain } from "lucide-react";
import type { ModelProfile, ReasoningEffort } from "@/types";

/** tokens → 中文万单位显示(如 123456 → 12.3万) */
export function formatTokens(n: number): string {
  if (!Number.isFinite(n) || n <= 0) return "0";
  if (n >= 10000) return `${(n / 10000).toFixed(n >= 1000000 ? 0 : 1)}万`;
  return String(Math.round(n));
}

/** 上下文使用环:完整圆环(低调底轨 + 彩色进度弧,真实占比,round 端点保证小占比可见) */
export const ContextRing = memo(function ContextRing({
  ratio,
  title,
}: {
  ratio: number;
  title?: string;
}) {
  const pct = Math.max(0, Math.min(1, Number.isFinite(ratio) ? ratio : 0));
  const r = 6;
  const c = 2 * Math.PI * r;
  const color =
    pct >= 0.9
      ? "var(--danger)"
      : pct >= 0.7
        ? "var(--warning)"
        : "var(--primary)";
  const label = `${Math.round(pct * 100)}%`;
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 14 14"
      className="shrink-0"
      role="img"
      aria-label={title ?? `上下文使用 ${label}`}
    >
      <title>{title ?? `上下文使用 ${label}`}</title>
      <circle cx="7" cy="7" r={r} fill="none" stroke="var(--border)" strokeWidth="2" />
      {pct > 0 && (
        <circle
          cx="7"
          cy="7"
          r={r}
          fill="none"
          stroke={color}
          strokeWidth="2"
          strokeDasharray={`${c * pct} ${c}`}
          strokeLinecap="round"
          transform="rotate(-90 7 7)"
        />
      )}
    </svg>
  );
});

export interface ContextBucket {
  label: string;
  /** 估算 token 数(用于占比计算) */
  value: number;
  color: string;
}

/** 真实 token 用量(供应商回传时展示);缓存命中率 = cached / prompt */
export interface UsageSummary {
  prompt_tokens: number;
  completion_tokens: number;
  cached_tokens: number;
}

/** 上下文用量表:点击圆环弹出容量面板(总量 + 分项占比 + 真实用量),参考终端类产品交互。 */
export const ContextGauge = memo(function ContextGauge({
  used,
  window: win,
  breakdown,
  usage,
}: {
  used: number;
  /** 上下文窗口;0/缺省表示未知(面板提示选择模型) */
  window: number;
  /** 分项:label + 估算值 + 颜色 */
  breakdown: ContextBucket[];
  /** 供应商回传的真实 token 用量(可选) */
  usage?: UsageSummary | null;
}) {
  const [open, setOpen] = useState(false);
  const pct = win ? Math.max(0, Math.min(1, used / win)) : 0;
  const color =
    pct >= 0.9 ? "var(--danger)" : pct >= 0.7 ? "var(--warning)" : "var(--primary)";
  const total = breakdown.reduce((s, b) => s + b.value, 0) || 1;
  const hasUsage = !!usage && (usage.prompt_tokens > 0 || usage.completion_tokens > 0);
  const cacheRate =
    hasUsage && usage!.prompt_tokens > 0
      ? Math.min(1, usage!.cached_tokens / usage!.prompt_tokens)
      : null;

  return (
    <div className="relative shrink-0">
      <button
        type="button"
        className="flex items-center rounded-full p-0.5 transition-colors hover:bg-surface-muted"
        onClick={() => setOpen((v) => !v)}
        aria-label="上下文使用情况"
        aria-expanded={open}
      >
        <ContextRing ratio={pct} title={`上下文使用 ${Math.round(pct * 100)}%`} />
      </button>

      {open && (
        <>
          {/* 点击面板外关闭 */}
          <div className="fixed inset-0 z-30" onClick={() => setOpen(false)} aria-hidden />
          <div className="surface-card absolute bottom-full right-0 z-40 mb-2 w-64 !p-3 shadow-lg">
            <div className="flex items-baseline justify-between">
              <p className="text-[12px] font-semibold text-ink">上下文容量</p>
              <p className="num-tabular text-[11px] text-ink-muted">
                {win
                  ? `${formatTokens(used)}/${formatTokens(win)}（${Math.round(pct * 100)}%）`
                  : `${formatTokens(used)}（未选模型）`}
              </p>
            </div>
            <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-surface-muted">
              <div
                className="h-full rounded-full transition-all"
                style={{ width: `${pct * 100}%`, backgroundColor: color }}
              />
            </div>
            <div className="mt-2.5 space-y-1.5">
              {breakdown.map((b) => (
                <div key={b.label} className="flex items-center gap-2 text-[11px]">
                  <span
                    className="h-1.5 w-1.5 shrink-0 rounded-full"
                    style={{ backgroundColor: b.color }}
                  />
                  <span className="min-w-0 flex-1 text-ink-muted">{b.label}</span>
                  <span className="num-tabular text-ink-subtle">
                    {Math.round((b.value / total) * 100)}%
                  </span>
                </div>
              ))}
              {breakdown.length === 0 && (
                <p className="text-[11px] text-ink-subtle">暂无消息</p>
              )}
            </div>
            {hasUsage && (
              <>
                <div className="my-2.5 border-t border-surface-border" />
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between text-[11px]">
                    <span className="text-ink-muted">输入 token</span>
                    <span className="num-tabular text-ink-subtle">
                      {formatTokens(usage!.prompt_tokens)}
                    </span>
                  </div>
                  <div className="flex items-center justify-between text-[11px]">
                    <span className="text-ink-muted">输出 token</span>
                    <span className="num-tabular text-ink-subtle">
                      {formatTokens(usage!.completion_tokens)}
                    </span>
                  </div>
                  <div className="flex items-center justify-between text-[11px]">
                    <span className="text-ink-muted">缓存命中率</span>
                    <span className="num-tabular text-ink-subtle">
                      {cacheRate != null
                        ? `${Math.round(cacheRate * 100)}%（${formatTokens(usage!.cached_tokens)}）`
                        : "—"}
                    </span>
                  </div>
                </div>
              </>
            )}
          </div>
        </>
      )}
    </div>
  );
});

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
