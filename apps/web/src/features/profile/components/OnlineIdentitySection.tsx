"use client";

import { Link2 } from "lucide-react";
import { CollapsibleSection } from "@/components/CollapsibleSection";
import { Field } from "./Field";
import type { ProfileSectionProps } from "../types";

export function OnlineIdentitySection({ profile, patch }: ProfileSectionProps) {
  return (
    <CollapsibleSection title="在线身份" icon={Link2} tone="brand">
      <div className="grid grid-cols-1 gap-x-4 gap-y-4 sm:grid-cols-2">
        <Field
          label="GitHub"
          value={profile.github_username || ""}
          onChange={(v) => patch("github_username", v)}
          placeholder="用户名"
        />
        <Field
          label="偏好语言"
          value={profile.preferred_languages || ""}
          onChange={(v) => patch("preferred_languages", v)}
          placeholder="中文, English"
        />
        <Field
          label="作品集 / 博客"
          value={profile.portfolio_url || ""}
          onChange={(v) => patch("portfolio_url", v)}
          placeholder="https://..."
          className="sm:col-span-2"
        />
        <Field
          label="LinkedIn"
          value={profile.linkedin_url || ""}
          onChange={(v) => patch("linkedin_url", v)}
          placeholder="https://linkedin.com/in/..."
          className="sm:col-span-2"
        />
      </div>
    </CollapsibleSection>
  );
}
