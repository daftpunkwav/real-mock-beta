"use client";

import { useEffect, useMemo, useState } from "react";
import { apiService as api } from "@/lib/api/apiService";
import type { UserProfile } from "@/types";
import {
  Save,
  User,
  Plus,
  GraduationCap,
  Briefcase,
  Sparkles,
  MapPin,
  Building2,
  Link2,
  X,
  Mail,
  Phone,
  Award,
  CheckCircle2,
} from "lucide-react";
import { LoadError } from "@/components/LoadError";
import { CollapsibleSection } from "@/components/CollapsibleSection";

/** 必填字段:保存时校验,并计入完整度核心项 */
const REQUIRED_KEYS = [
  "name",
  "identity",
  "job_direction",
  "target_role",
  "self_intro",
  "tech_domains",
] as const;

type RequiredKey = (typeof REQUIRED_KEYS)[number];

const REQUIRED_LABELS: Record<RequiredKey, string> = {
  name: "姓名",
  identity: "身份",
  job_direction: "求职方向",
  target_role: "目标岗位",
  self_intro: "自我介绍",
  tech_domains: "技术领域",
};

/** 选填字段:计入完整度但不拦截保存 */
const OPTIONAL_COMPLETION_KEYS = [
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

export default function ProfilePage() {
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState("");
  const [missingRequired, setMissingRequired] = useState<RequiredKey[]>([]);

  const loadProfile = () => {
    setLoading(true);
    setLoadError("");
    api
      .getProfile()
      .then(setProfile)
      .catch((e) => setLoadError(e instanceof Error ? e.message : "加载失败"))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadProfile();
  }, []);

  const filledDomains = profile?.tech_domains.filter((d) => d.trim()) ?? [];

  const isFieldFilled = (key: string): boolean => {
    if (!profile) return false;
    if (key === "tech_domains") return filledDomains.length > 0;
    const value = profile[key as keyof UserProfile];
    return typeof value === "string" ? value.trim().length > 0 : Boolean(value);
  };

  const requiredMissing = useMemo(() => {
    if (!profile) return [] as RequiredKey[];
    return REQUIRED_KEYS.filter((key) => !isFieldFilled(key));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [profile, filledDomains.length]);

  const requiredDone = REQUIRED_KEYS.length - requiredMissing.length;
  const optionalDone = OPTIONAL_COMPLETION_KEYS.filter((key) => isFieldFilled(key)).length;
  const totalTracked = REQUIRED_KEYS.length + OPTIONAL_COMPLETION_KEYS.length;
  const completion = requiredDone + optionalDone;
  const completionPct = Math.round((completion / totalTracked) * 100);

  const handleSave = async () => {
    if (!profile) return;
    const missing = REQUIRED_KEYS.filter((key) => {
      if (key === "tech_domains") return filledDomains.length === 0;
      const value = profile[key as keyof UserProfile];
      return typeof value === "string" ? !value.trim() : !value;
    });
    setMissingRequired(missing);
    if (missing.length > 0) {
      setMsg(`请先填写必填项:${missing.map((k) => REQUIRED_LABELS[k]).join("、")}`);
      return;
    }
    setSaving(true);
    try {
      const payload = {
        ...profile,
        tech_domains: profile.tech_domains.map((d) => d.trim()).filter(Boolean),
      };
      const updated = await api.updateProfile(payload);
      setProfile(updated);
      setMsg("已保存");
      setTimeout(() => setMsg(""), 2000);
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "保存失败");
    } finally {
      setSaving(false);
    }
  };

  const addDomain = () => {
    if (!profile) return;
    setProfile({ ...profile, tech_domains: [...profile.tech_domains, ""] });
  };

  const removeDomain = (i: number) => {
    if (!profile) return;
    const domains = profile.tech_domains.filter((_, idx) => idx !== i);
    setProfile({ ...profile, tech_domains: domains.length ? domains : [""] });
  };

  const patch = <K extends keyof UserProfile>(key: K, value: UserProfile[K]) => {
    if (!profile) return;
    setProfile({ ...profile, [key]: value });
    if (REQUIRED_KEYS.includes(key as RequiredKey)) {
      setMissingRequired((prev) => prev.filter((k) => k !== key));
    }
  };

  if (loading) {
    return (
      <div className="page-shell">
        <PageHead />
        <div className="flex items-center justify-center gap-2 py-16 text-[13px] text-ink-muted">
          <span className="block h-4 w-4 anim-spin rounded-full border-2 border-current border-t-transparent" />
          加载档案…
        </div>
      </div>
    );
  }

  if (loadError) {
    return (
      <div className="page-shell">
        <PageHead />
        <LoadError message={loadError} onRetry={loadProfile} />
      </div>
    );
  }

  if (!profile) return null;

  const requiredError = (key: RequiredKey) => missingRequired.includes(key);

  return (
    <div className="page-shell anim-rise">
      <div className="page-header">
        <PageHead />
        <div className="flex shrink-0 items-center gap-3">
          {msg && (
            <span
              className={`max-w-xs text-right text-[12px] font-medium ${
                msg.includes("失败") || msg.includes("必填")
                  ? "text-[var(--danger-ink)]"
                  : "text-[var(--success-ink)]"
              }`}
            >
              {msg}
            </span>
          )}
          <button type="button" onClick={handleSave} disabled={saving} className="btn-primary">
            {saving ? (
              <span className="block h-3.5 w-3.5 anim-spin rounded-full border-2 border-current border-t-transparent" />
            ) : (
              <Save size={13} />
            )}
            保存档案
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 items-start gap-5 xl:grid-cols-[minmax(0,1fr)_300px]">
        <div className="space-y-4">
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

          <CollapsibleSection
            title="技能与介绍"
            icon={Sparkles}
            tone="brand"
            actions={
              <button
                type="button"
                onClick={addDomain}
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
                        onClick={() => removeDomain(i)}
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
        </div>

        <aside className="space-y-4 xl:sticky xl:top-6">
          {/* 完整度卡片 */}
          <div className="surface-card p-5">
            <div className="mb-2.5 flex items-center justify-between">
              <span className="text-[13px] font-semibold tracking-tight text-ink">
                档案完整度
              </span>
              <span className="font-mono text-[14px] font-semibold text-[var(--primary)] num-tabular">
                {completionPct}%
              </span>
            </div>
            <div className="progress">
              <div
                className="progress-bar anim-progress-fill"
                style={{ width: `${completionPct}%` }}
              />
            </div>
            <div className="mt-3 grid grid-cols-2 gap-2 text-center">
              <div className="kpi-card !p-2.5">
                <p className="font-mono text-[15px] font-semibold text-ink num-tabular">
                  {requiredDone}/{REQUIRED_KEYS.length}
                </p>
                <p className="kpi-label mt-0.5">必填</p>
              </div>
              <div className="kpi-card !p-2.5">
                <p className="font-mono text-[15px] font-semibold text-ink num-tabular">
                  {optionalDone}/{OPTIONAL_COMPLETION_KEYS.length}
                </p>
                <p className="kpi-label mt-0.5">选填</p>
              </div>
            </div>
            {requiredMissing.length > 0 ? (
              <div className="mt-3 rounded-md border border-[var(--danger)]/30 bg-[var(--danger-soft)] px-3 py-2">
                <p className="text-[11px] leading-relaxed text-[var(--danger-ink)]">
                  待补必填:{requiredMissing.map((k) => REQUIRED_LABELS[k]).join("、")}
                </p>
              </div>
            ) : (
              <div className="mt-3 flex items-center gap-2 rounded-md border border-[var(--success)]/30 bg-[var(--success-soft)] px-3 py-2">
                <CheckCircle2 size={13} className="text-[var(--success)]" />
                <span className="text-[11px] font-medium text-[var(--success-ink)]">
                  所有必填项已就绪
                </span>
              </div>
            )}
          </div>

          {/* 档案预览 */}
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
        </aside>
      </div>
    </div>
  );
}

function PageHead() {
  return (
    <div className="flex items-start gap-3">
      <span className="icon-badge">
        <User size={18} strokeWidth={1.75} />
      </span>
      <div>
        <p className="page-eyebrow">Profile</p>
        <h1 className="page-title">个人档案</h1>
        <p className="page-desc">本地存储,无需注册。必填信息用于生成更精准的面试问题。</p>
      </div>
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  placeholder,
  className = "",
  required = false,
  error = false,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  className?: string;
  required?: boolean;
  error?: boolean;
}) {
  return (
    <div className={className}>
      <label className="field-label !mb-1.5 !text-xs">
        {label}
        {required ? <span className="text-[var(--danger)]"> *</span> : null}
      </label>
      <input
        type="text"
        className={`field-input !text-[13px] ${error ? "field-invalid" : ""}`}
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        aria-invalid={error || undefined}
        aria-required={required || undefined}
      />
      {error && <p className="field-error">请填写{label}</p>}
    </div>
  );
}

function PreviewRow({
  icon: Icon,
  label,
  value,
}: {
  icon: React.ComponentType<{ size?: number; className?: string; strokeWidth?: number }>;
  label: string;
  value: string;
}) {
  return (
    <div className="flex items-start gap-3">
      <Icon size={14} className="mt-1 shrink-0 text-ink-subtle" strokeWidth={1.75} />
      <div className="min-w-0 flex-1">
        <dt className="text-[10px] uppercase leading-none tracking-[0.1em] text-ink-subtle">
          {label}
        </dt>
        <dd className="mt-1.5 break-words text-[13px] font-medium leading-snug text-ink">
          {value}
        </dd>
      </div>
    </div>
  );
}
