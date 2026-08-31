"use client";

import { User } from "lucide-react";
import { CollapsibleSection } from "@/components/CollapsibleSection";
import { Field } from "./Field";
import type { ProfileSectionProps } from "../types";

export function BasicInfoSection({ profile, patch, requiredError }: ProfileSectionProps) {
  return (
    <CollapsibleSection
      title="基本信息"
      icon={User}
      hint="带 * 为必填,影响面试问题生成"
      tone="brand"
    >
      <div className="grid grid-cols-1 gap-x-4 gap-y-4 sm:grid-cols-2 lg:grid-cols-3">
        <Field
          label="姓名"
          required
          error={requiredError("name")}
          value={profile.name}
          onChange={(v) => patch("name", v)}
          placeholder="你的姓名"
        />
        <Field
          label="性别"
          value={profile.gender || ""}
          onChange={(v) => patch("gender", v)}
          placeholder="男 / 女"
        />
        <Field
          label="身份"
          required
          error={requiredError("identity")}
          value={profile.identity || ""}
          onChange={(v) => patch("identity", v)}
          placeholder="学生 / 在职 / 待业"
        />
        <Field
          label="邮箱"
          value={profile.email || ""}
          onChange={(v) => patch("email", v)}
          placeholder="you@example.com"
        />
        <Field
          label="电话 / 微信"
          value={profile.phone || ""}
          onChange={(v) => patch("phone", v)}
          placeholder="手机号或微信号"
        />
      </div>
    </CollapsibleSection>
  );
}
