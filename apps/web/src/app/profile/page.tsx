"use client";

import { Save } from "lucide-react";
import { LoadError } from "@/components/LoadError";
import {
  BasicInfoSection,
  CompletionCard,
  EducationSection,
  JobIntentSection,
  OnlineIdentitySection,
  PageHead,
  PreviewCard,
  SkillsSection,
  useProfileForm,
} from "@/features/profile";

export default function ProfilePage() {
  const {
    profile,
    loading,
    loadError,
    saving,
    msg,
    stats,
    loadProfile,
    patch,
    handleSave,
    addDomain,
    removeDomain,
    requiredError,
  } = useProfileForm();

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
          <BasicInfoSection profile={profile} patch={patch} requiredError={requiredError} />
          <EducationSection profile={profile} patch={patch} requiredError={requiredError} />
          <JobIntentSection profile={profile} patch={patch} requiredError={requiredError} />
          <OnlineIdentitySection profile={profile} patch={patch} requiredError={requiredError} />
          <SkillsSection
            profile={profile}
            patch={patch}
            requiredError={requiredError}
            onAddDomain={addDomain}
            onRemoveDomain={removeDomain}
          />
        </div>

        <aside className="space-y-4 xl:sticky xl:top-6">
          <CompletionCard stats={stats} />
          <PreviewCard profile={profile} filledDomains={stats.filledDomains} />
        </aside>
      </div>
    </div>
  );
}
