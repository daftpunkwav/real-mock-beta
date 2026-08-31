"use client";

import {
  Award,
  Briefcase,
  Building2,
  GraduationCap,
  Link2,
  Mail,
  MapPin,
  Phone,
} from "lucide-react";
import type { UserProfile } from "@/types";
import { PreviewRow } from "./PreviewRow";

export function PreviewCard({
  profile,
  filledDomains,
}: {
  profile: UserProfile;
  filledDomains: string[];
}) {
  return (
    <div className="surface-card p-5">
      <div className="mb-5 flex items-center gap-3.5">
        <div
          className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full text-lg font-semibold tracking-tight text-white"
          style={{ background: "var(--primary)" }}
        >
          {(profile.name || "?").charAt(0)}
        </div>
        <div className="min-w-0">
          <h2 className="truncate text-[15px] font-semibold leading-snug tracking-tight text-ink">
            {profile.name || "未填写姓名"}
          </h2>
          <p className="mt-1 truncate text-[11px] text-ink-subtle">
            {[profile.identity, profile.school].filter(Boolean).join(" · ") ||
              "完善档案以生成预览"}
          </p>
        </div>
      </div>

      <dl className="space-y-3.5">
        {profile.major && (
          <PreviewRow
            icon={GraduationCap}
            label="专业"
            value={`${profile.major}${profile.graduation_year ? ` · ${profile.graduation_year}` : ""}`}
          />
        )}
        {profile.education_level && (
          <PreviewRow icon={Award} label="学历" value={profile.education_level} />
        )}
        {profile.target_role && (
          <PreviewRow icon={Briefcase} label="目标岗位" value={profile.target_role} />
        )}
        {profile.job_direction && (
          <PreviewRow icon={MapPin} label="求职方向" value={profile.job_direction} />
        )}
        {profile.current_company && (
          <PreviewRow icon={Building2} label="当前公司" value={profile.current_company} />
        )}
        {profile.expected_city && (
          <PreviewRow icon={MapPin} label="期望城市" value={profile.expected_city} />
        )}
        {profile.city && !profile.expected_city && (
          <PreviewRow icon={MapPin} label="城市" value={profile.city} />
        )}
        {profile.email && <PreviewRow icon={Mail} label="邮箱" value={profile.email} />}
        {profile.phone && <PreviewRow icon={Phone} label="电话/微信" value={profile.phone} />}
        {profile.github_username && (
          <PreviewRow icon={Link2} label="GitHub" value={profile.github_username} />
        )}
      </dl>

      {filledDomains.length > 0 && (
        <div className="mt-5 border-t border-surface-border pt-4">
          <p className="mb-2.5 text-[10px] font-semibold uppercase tracking-[0.1em] text-ink-subtle">
            技术栈
          </p>
          <div className="flex flex-wrap gap-1.5">
            {filledDomains.map((d) => (
              <span key={d} className="chip chip-blue">
                {d}
              </span>
            ))}
          </div>
        </div>
      )}

      {profile.self_intro && (
        <div className="mt-5 border-t border-surface-border pt-4">
          <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.1em] text-ink-subtle">
            自我介绍
          </p>
          <p className="line-clamp-6 text-[12.5px] leading-relaxed text-ink-muted text-balance">
            {profile.self_intro}
          </p>
        </div>
      )}
    </div>
  );
}
