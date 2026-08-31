"use client";

import { Plus, Sparkles, X } from "lucide-react";
import { CollapsibleSection } from "@/components/CollapsibleSection";
import type { ProfileSectionProps } from "../types";

export function SkillsSection({
  profile,
  patch,
  requiredError,
  onAddDomain,
  onRemoveDomain,
}: ProfileSectionProps & {
  onAddDomain: () => void;
  onRemoveDomain: (i: number) => void;
}) {
  return (
    <CollapsibleSection
      title="技能与介绍"
      icon={Sparkles}
      tone="brand"
      actions={
        <button
          type="button"
          onClick={onAddDomain}
          className="btn-tertiary !h-8 !px-2 !text-xs text-[var(--primary)]"
        >
          <Plus size={13} /> 添加技术领域
        </button>
      }
    >
      <div className="space-y-4">
        <div>
          <label className="field-label">
            自我介绍 <span className="text-[var(--danger)]">*</span>
          </label>
          <textarea
            className={`field-textarea !leading-[1.7] ${requiredError("self_intro") ? "field-invalid" : ""}`}
            rows={4}
            value={profile.self_intro || ""}
            onChange={(e) => patch("self_intro", e.target.value)}
            placeholder="简要介绍背景、优势与求职动机…"
          />
          {requiredError("self_intro") && <p className="field-error">请填写自我介绍</p>}
        </div>
        <div>
          <label className="field-label">职业亮点</label>
          <textarea
            className="field-textarea !min-h-[80px] !leading-[1.7]"
            rows={3}
            value={profile.career_highlights || ""}
            onChange={(e) => patch("career_highlights", e.target.value)}
            placeholder="2–4 条可量化的成就…"
          />
        </div>
        <div>
          <label className="field-label">代表项目</label>
          <textarea
            className="field-textarea !min-h-[80px] !leading-[1.7]"
            rows={3}
            value={profile.signature_projects || ""}
            onChange={(e) => patch("signature_projects", e.target.value)}
            placeholder="1–3 个代表性项目:名称、职责、技术栈、结果…"
          />
        </div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <label className="field-label">优势</label>
            <textarea
              className="field-textarea !min-h-[80px] !leading-[1.7]"
              rows={3}
              value={profile.strengths || ""}
              onChange={(e) => patch("strengths", e.target.value)}
              placeholder="如系统思维、落地能力…"
            />
          </div>
          <div>
            <label className="field-label">待提升</label>
            <textarea
              className="field-textarea !min-h-[80px] !leading-[1.7]"
              rows={3}
              value={profile.weaknesses || ""}
              onChange={(e) => patch("weaknesses", e.target.value)}
              placeholder="坦诚且可改进的短板…"
            />
          </div>
        </div>
        <div>
          <label className="field-label">证书</label>
          <textarea
            className="field-textarea !min-h-[72px] !leading-[1.7]"
            rows={2}
            value={profile.certificates || ""}
            onChange={(e) => patch("certificates", e.target.value)}
            placeholder="如 AWS SAA、软考、专利等"
          />
        </div>
        <div>
          <div className="mb-2 flex items-center justify-between">
            <label className="field-label !mb-0">
              技术领域 <span className="text-[var(--danger)]">*</span>
            </label>
          </div>
          <div className="flex flex-wrap gap-2">
            {profile.tech_domains.map((d, i) => (
              <div
                key={i}
                className={`inline-flex h-9 items-center gap-1 rounded-md border bg-surface-card pl-3 pr-1 transition-colors focus-within:border-[var(--primary)] focus-within:shadow-focus ${
                  requiredError("tech_domains") ? "border-[var(--danger)]" : "border-surface-border"
                }`}
              >
                <input
                  className="w-28 bg-transparent text-[13px] outline-none placeholder:text-ink-subtle sm:w-32"
                  value={d}
                  placeholder="如 Python"
                  onChange={(e) => {
                    const domains = [...profile.tech_domains];
                    domains[i] = e.target.value;
                    patch("tech_domains", domains);
                  }}
                />
                <button
                  type="button"
                  onClick={() => onRemoveDomain(i)}
                  className="flex h-7 w-7 items-center justify-center rounded-full text-ink-muted transition-colors hover:bg-surface-muted hover:text-ink"
                  aria-label="移除"
                >
                  <X size={12} />
                </button>
              </div>
            ))}
          </div>
          {requiredError("tech_domains") && (
            <p className="field-error">请至少填写一项技术领域</p>
          )}
        </div>
      </div>
    </CollapsibleSection>
  );
}
