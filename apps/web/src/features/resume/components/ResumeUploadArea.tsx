"use client";

import type { ChangeEvent, RefObject } from "react";
import { Upload } from "lucide-react";

interface ResumeUploadAreaProps {
  uploading: boolean;
  error: string;
  inputRef: RefObject<HTMLInputElement | null>;
  onUpload: (e: ChangeEvent<HTMLInputElement>) => void;
}

/** 上传区：点击或拖拽上传简历。 */
export function ResumeUploadArea({ uploading, error, inputRef, onUpload }: ResumeUploadAreaProps) {
  return (
    <>
      {/* 上传区 */}
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        disabled={uploading}
        className="group surface-card flex w-full cursor-pointer flex-col items-center justify-center border-dashed !border-2 p-6 text-center hover:border-[var(--primary)] hover:bg-[var(--info-soft)] sm:p-8 disabled:opacity-60"
      >
        {uploading ? (
          <span className="block h-7 w-7 anim-spin rounded-full border-2 border-[var(--primary)] border-t-transparent" />
        ) : (
          <span className="icon-badge icon-badge-brand transition-transform group-hover:scale-105">
            <Upload size={16} strokeWidth={1.75} />
          </span>
        )}
        <p className="mt-3 text-[13px] font-medium text-ink">
          {uploading ? "正在解析简历…" : "点击或拖拽上传简历"}
        </p>
        <p className="mt-1 text-[11px] text-ink-subtle">PDF · DOCX · MD · TXT · 最大 10MB</p>
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,.docx,.doc,.md,.txt"
          className="hidden"
          onChange={onUpload}
        />
      </button>

      {error && <div className="alert alert-error">{error}</div>}
    </>
  );
}
