"use client";

import { Briefcase } from "lucide-react";
import { CollapsibleSection } from "@/components/CollapsibleSection";
import { Field } from "./Field";
import type { ProfileSectionProps } from "../types";

export function JobIntentSection({ profile, patch, requiredError }: ProfileSectionProps) {
  return (
    <CollapsibleSection title="求职意向" icon={Briefcase} tone="brand">
      <div className="grid grid-cols-1 gap-x-4 gap-y-4 sm:grid-cols-2">
        <Field
          label="求职方向"
          required
          error={requiredError("job_direction")}
          value={profile.job_direction}
          onChange={(v) => patch("job_direction", v)}
          placeholder="如 人工智能 / 后端"
        />
        <Field
          label="目标岗位"
          required
          error={requiredError("target_role")}
          value={profile.target_role}
          onChange={(v) => patch("target_role", v)}
          placeholder="如 AI 工程师"
        />
        <Field
          label="工作年限"
          value={profile.experience_years}
          onChange={(v) => patch("experience_years", v)}
          placeholder="0-1 年"
        />
        <Field
          label="年限说明"
          value={profile.work_years_detail || ""}
          onChange={(v) => patch("work_years_detail", v)}
          placeholder="含实习 / 仅正式工作"
        />
        <Field
          label="当前公司"
          value={profile.current_company || ""}
          onChange={(v) => patch("current_company", v)}
          placeholder="无则留空"
        />
        <Field
          label="期望薪资"
          value={profile.expected_salary || ""}
          onChange={(v) => patch("expected_salary", v)}
          placeholder="如 15-20K"
        />
        <Field
          label="所在城市"
          value={profile.city || ""}
          onChange={(v) => patch("city", v)}
          placeholder="如 上海"
        />
        <Field
          label="期望城市"
          value={profile.expected_city || ""}
          onChange={(v) => patch("expected_city", v)}
          placeholder="如 北京 / 远程"
        />
        <Field
          label="到岗时间"
          value={profile.notice_period || ""}
          onChange={(v) => patch("notice_period", v)}
          placeholder="两周 / 一个月"
        />
        <Field
          label="远程意愿"
          value={profile.open_to_remote || ""}
          onChange={(v) => patch("open_to_remote", v)}
          placeholder="yes / no / hybrid"
        />
      </div>
    </CollapsibleSection>
  );
}
