"use client";

/** 面试配置页右侧预览：配置摘要 + 公司面经 + 提示。 */

import { Briefcase, Building2, Lightbulb, ListChecks, Mic, UserCircle } from "lucide-react";
import type { InterviewConfig, Options, ResumePickerItem } from "@/lib/api/contract";
import { strictnessLabel } from "./form";

export function PreviewRow({
  icon: Icon,
  label,
  value,
}: {
  icon: React.ComponentType<{ size?: number; className?: string; strokeWidth?: number }>;
  label: string;
  value: string;
}) {
  return (
    <div className="flex items-start gap-1.5">
      <Icon size={12} className="mt-0.5 shrink-0 text-ink-subtle" strokeWidth={1.75} />
      <div className="min-w-0">
        <span className="text-[10px] uppercase tracking-[0.08em] text-ink-subtle">{label}</span>
        <p className="break-words text-[12px] font-medium leading-snug text-ink">{value}</p>
      </div>
    </div>
  );
}

export function InterviewPreview({
  options,
  config,
  resumes,
}: {
  options: Options;
  config: InterviewConfig;
  resumes: ResumePickerItem[];
}) {
  const selectedCompany = options.companies.find((c) => c.id === config.company);
  const selectedPersonality = options.personalities.find((p) => p.id === config.personality);
  const selectedWorkflow = options.workflow_types.find((w) => w.id === config.workflow_type);
  const selectedStyle = options.interview_styles.find((s) => s.id === config.interview_style);
  const selectedAvatar = options.avatars?.find((a) => a.id === config.avatar_id);
  const selectedScene = options.scenes?.find((s) => s.id === config.scene_id);
  const selectedResume = resumes.find((r) => r.id === config.resume_id);

  return (
    <div className="flex h-full flex-col gap-2.5 overflow-hidden">
      <div className="surface-card p-3.5">
        <h2 className="mb-2.5 flex items-center gap-1.5 text-xs font-semibold text-ink">
          <ListChecks size={14} className="text-[var(--primary)]" />
          配置预览
        </h2>
        <div className="space-y-2 text-xs">
          <PreviewRow icon={Briefcase} label="岗位" value={`${config.role} · ${config.level}`} />
          <PreviewRow icon={Building2} label="公司" value={selectedCompany?.name ?? config.company} />
          <PreviewRow
            icon={Mic}
            label="类型"
            value={`${selectedWorkflow?.name ?? ""} · ${selectedStyle?.name ?? ""}`}
          />
          <PreviewRow
            icon={UserCircle}
            label="面试官"
            value={`${selectedPersonality?.name ?? ""} · ${strictnessLabel(config.strictness)}`}
          />
          {(selectedAvatar || selectedScene) && (
            <PreviewRow
              icon={UserCircle}
              label="形象"
              value={[
                selectedAvatar?.name,
                selectedAvatar?.voice
                  ? `音色 ${
                      options.tts_voices?.find((v) => v.id === selectedAvatar.voice)?.name ||
                      selectedAvatar.voice
                    }`
                  : null,
                selectedScene?.name,
              ]
                .filter(Boolean)
                .join(" · ")}
            />
          )}
          {selectedResume && (
            <PreviewRow icon={Briefcase} label="简历" value={selectedResume.filename} />
          )}
        </div>
      </div>

      {selectedCompany && (
        <div className="surface-card min-h-0 flex-1 overflow-y-auto p-3.5">
          <h2 className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold text-ink">
            <Building2 size={14} className="text-[var(--primary)]" />
            {selectedCompany.name} 面经
          </h2>
          <p className="mb-2 line-clamp-3 text-[11px] leading-snug text-ink-muted">
            {selectedCompany.style}
          </p>
          {selectedCompany.focus_areas.length > 0 && (
            <div className="mb-2 flex flex-wrap gap-1">
              {selectedCompany.focus_areas.slice(0, 6).map((area) => (
                <span key={area} className="chip chip-blue !text-[10px]">
                  {area}
                </span>
              ))}
            </div>
          )}
          {selectedWorkflow && selectedWorkflow.phases.length > 0 && (
            <div className="mb-2">
              <p className="mb-1 text-[10px] uppercase tracking-[0.08em] text-ink-subtle">流程</p>
              <p className="font-mono text-[11px] leading-snug text-ink-muted">
                {selectedWorkflow.phases.join(" → ")}
              </p>
            </div>
          )}
          {selectedCompany.sample_questions.length > 0 && (
            <p className="line-clamp-3 text-[11px] leading-snug text-ink-muted">
              <span className="text-ink-subtle">参考:</span>
              {selectedCompany.sample_questions[0]}
            </p>
          )}
        </div>
      )}

      <div className="surface-card shrink-0 px-3.5 py-2.5">
        <p className="flex items-start gap-1.5 text-[11px] leading-snug text-ink-muted">
          <Lightbulb size={13} className="mt-0.5 shrink-0 text-[var(--primary)]" />
          关联简历后问题更贴合项目;建议先完成 BYOK 配置。
        </p>
      </div>
    </div>
  );
}
