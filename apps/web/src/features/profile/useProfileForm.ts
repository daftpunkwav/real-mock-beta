"use client";

import { useEffect, useMemo, useState } from "react";
import { profileHttp as api } from "@/lib/api/clients";
import type { UserProfileResponse } from "@/lib/api/contract";
import {
  REQUIRED_KEYS,
  REQUIRED_LABELS,
  completionStatsOf,
  type ProfileCompletionStats,
  type RequiredKey,
} from "./profileRules";

export function useProfileForm() {
  const [profile, setProfile] = useState<UserProfileResponse | null>(null);
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

  const stats: ProfileCompletionStats = useMemo(() => completionStatsOf(profile), [profile]);

  const patch = <K extends keyof UserProfileResponse>(key: K, value: UserProfileResponse[K]) => {
    if (!profile) return;
    setProfile({ ...profile, [key]: value });
    if (REQUIRED_KEYS.includes(key as RequiredKey)) {
      setMissingRequired((prev) => prev.filter((k) => k !== key));
    }
  };

  const handleSave = async () => {
    if (!profile) return;
    const missing = stats.requiredMissing;
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

  const requiredError = (key: RequiredKey) => missingRequired.includes(key);

  return {
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
  };
}
