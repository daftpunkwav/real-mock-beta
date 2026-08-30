"use client";

import { useEffect, useRef, useState } from "react";
import { HelpCircle, Send } from "lucide-react";

interface AskUserModalProps {
  question: string;
  options: string[];
  disabled?: boolean;
  onAnswer: (text: string) => void;
  onClose: () => void;
}

/**
 * Agent 弹窗提问:展示问题与候选选项,点击选项直接回答;
 * 底部输入框支持自定义回答。代替"在对话框里追问"的旧交互。
 */
export function AskUserModal({
  question,
  options,
  disabled = false,
  onAnswer,
  onClose,
}: AskUserModalProps) {
  const [custom, setCustom] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !custom) onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [custom, onClose]);

  const answer = (text: string) => {
    const t = text.trim();
    if (!t || disabled) return;
    onAnswer(t);
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 anim-fade-in"
      role="dialog"
      aria-modal="true"
      aria-label={question}
    >
      <div className="surface-card w-full max-w-md !p-5 anim-rise">
        <div className="flex items-start gap-3">
          <span className="icon-badge icon-badge-brand shrink-0">
            <HelpCircle size={16} />
          </span>
          <div className="min-w-0">
            <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--primary)]">
              教练想确认
            </p>
            <p className="mt-1 text-[14px] font-medium leading-relaxed text-ink">
              {question}
            </p>
          </div>
        </div>

        <div className="mt-4 space-y-2">
          {options.map((opt) => (
            <button
              key={opt}
              type="button"
              disabled={disabled}
              onClick={() => answer(opt)}
              className="w-full rounded-md border border-surface-border bg-surface-alt px-3.5 py-2.5 text-left text-[13px] leading-relaxed text-ink transition-colors hover:border-[var(--primary)] hover:bg-[var(--info-soft)] disabled:cursor-not-allowed disabled:opacity-50"
            >
              {opt}
            </button>
          ))}
        </div>

        <div className="mt-4 flex gap-2">
          <input
            ref={inputRef}
            className="field-input flex-1"
            value={custom}
            onChange={(e) => setCustom(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && answer(custom)}
            placeholder="或输入自定义回答…"
            disabled={disabled}
          />
          <button
            type="button"
            onClick={() => answer(custom)}
            disabled={disabled || !custom.trim()}
            className="btn-primary !h-9 !w-11 shrink-0 !px-0"
            aria-label="发送回答"
          >
            <Send size={14} />
          </button>
        </div>

        <button
          type="button"
          onClick={onClose}
          className="mt-3 w-full text-center text-[11px] text-ink-subtle transition-colors hover:text-ink-muted"
        >
          暂不回答,稍后在输入框回复
        </button>
      </div>
    </div>
  );
}
