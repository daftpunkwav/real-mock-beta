"use client";

import { GraduationCap } from "lucide-react";
import { CollapsibleSection } from "@/components/CollapsibleSection";
import { Field } from "./Field";
import type { ProfileSectionProps } from "../types";

export function EducationSection({ profile, patch }: ProfileSectionProps) {
  return (
    <CollapsibleSection title="教育背景" icon={GraduationCap} tone="brand">
      <div className="grid grid-cols-1 gap-x-4 gap-y-4 sm:grid-cols-2 lg:grid-cols-3">
        <Field
          label="学校"
          value={profile.school || ""}
          onChange={(v) => patch("school", v)}
          placeholder="学校全称"
        />
        <Field
          label="专业"
          value={profile.major || ""}
          onChange={(v) => patch("major", v)}
          placeholder="专业名称"
        />
        <Field
          label="学历层次"
          value={profile.education_level || ""}
          onChange={(v) => patch("education_level", v)}
          placeholder="本科 / 硕士 / 博士"
        />
        <Field
          label="毕业年份"
          value={profile.graduation_year || ""}
          onChange={(v) => patch("graduation_year", v)}
          placeholder="如 2027"
        />
        <Field
          label="英语水平"
          value={profile.english_level || ""}
          onChange={(v) => patch("english_level", v)}
          placeholder="CET-6 / 雅思 7 / 工作语言"
        />
      </div>
    </CollapsibleSection>
  );
}
