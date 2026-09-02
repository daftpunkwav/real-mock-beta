import type { UserProfileResponse as UserProfile } from "@/lib/api/contract";

/** 必填字段:保存时校验,并计入完整度核心项 */
export const REQUIRED_KEYS = [
  "name",
  "identity",
  "job_direction",
  "target_role",
  "self_intro",
  "tech_domains",
] as const;

export type RequiredKey = (typeof REQUIRED_KEYS)[number];

export const REQUIRED_LABELS: Record<RequiredKey, string> = {
  name: "姓名",
  identity: "身份",
  job_direction: "求职方向",
  target_role: "目标岗位",
  self_intro: "自我介绍",
  tech_domains: "技术领域",
};

/** 选填字段:计入完整度但不拦截保存 */
export const OPTIONAL_COMPLETION_KEYS = [
  "gender",
  "school",
  "major",
  "education_level",
  "graduation_year",
  "experience_years",
  "current_company",
  "expected_salary",
  "city",
  "expected_city",
  "email",
  "phone",
  "github_username",
  "english_level",
  "certificates",
  "signature_projects",
  "career_highlights",
  "strengths",
  "weaknesses",
] as const;

export interface ProfileCompletionStats {
  filledDomains: string[];
  requiredMissing: RequiredKey[];
  requiredDone: number;
  optionalDone: number;
  completionPct: number;
}

export function filledDomainsOf(profile: UserProfile): string[] {
  return profile.tech_domains.filter((d) => d.trim());
}

export function isFieldFilled(
  profile: UserProfile | null,
  key: string,
  filledDomains: string[],
): boolean {
  if (!profile) return false;
  if (key === "tech_domains") return filledDomains.length > 0;
  const value = profile[key as keyof UserProfile];
  return typeof value === "string" ? value.trim().length > 0 : Boolean(value);
}

export function requiredMissingOf(
  profile: UserProfile | null,
  filledDomains: string[],
): RequiredKey[] {
  if (!profile) return [];
  return REQUIRED_KEYS.filter((key) => !isFieldFilled(profile, key, filledDomains));
}

export function completionStatsOf(profile: UserProfile | null): ProfileCompletionStats {
  const filledDomains = profile ? filledDomainsOf(profile) : [];
  const requiredMissing = requiredMissingOf(profile, filledDomains);
  const requiredDone = REQUIRED_KEYS.length - requiredMissing.length;
  const optionalDone = OPTIONAL_COMPLETION_KEYS.filter((key) =>
    isFieldFilled(profile, key, filledDomains),
  ).length;
  const totalTracked = REQUIRED_KEYS.length + OPTIONAL_COMPLETION_KEYS.length;
  const completion = requiredDone + optionalDone;
  return {
    filledDomains,
    requiredMissing,
    requiredDone,
    optionalDone,
    completionPct: Math.round((completion / totalTracked) * 100),
  };
}
