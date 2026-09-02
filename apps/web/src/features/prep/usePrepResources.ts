"use client";

/** prep 侧栏资源：简历列表、会话列表、场景模型选择器数据。 */

import { useCallback, useEffect, useState } from "react";
import { prepCoachHttp, profileHttp } from "@/lib/api/clients";
import type { PrepSessionSummary, ResumePickerItem } from "@/lib/api/contract";
import type { ModelProfile, ReasoningEffort } from "@/types";

export function usePrepResources() {
  const [resumes, setResumes] = useState<ResumePickerItem[]>([]);
  const [resumeId, setResumeId] = useState<number | null>(null);
  const [resumeLoadError, setResumeLoadError] = useState("");
  const [sessions, setSessions] = useState<PrepSessionSummary[]>([]);
  const [chatModels, setChatModels] = useState<ModelProfile[]>([]);
  const [selectedModelId, setSelectedModelId] = useState<number | null>(null);
  const [effort, setEffort] = useState<ReasoningEffort>("medium");
  const [defaultChatProfile, setDefaultChatProfile] = useState<ModelProfile | null>(null);

  useEffect(() => {
    prepCoachHttp
      .listResumes()
      .then((list) => {
        setResumeLoadError("");
        setResumes(list);
        const active = list.find((r) => r.is_active) || list[0];
        if (active) setResumeId(active.id);
      })
      .catch((e) => {
        setResumeLoadError(e instanceof Error ? e.message : "简历列表加载失败");
      });
  }, []);

  const refreshSessions = useCallback(() => {
    prepCoachHttp
      .listPrepSessions()
      .then((list) => setSessions(Array.isArray(list) ? list : []))
      .catch(() => {});
  }, []);

  useEffect(() => {
    refreshSessions();
  }, [refreshSessions]);

  useEffect(() => {
    profileHttp
      .listModelOptions()
      .then((res) => {
        const list = Array.isArray(res?.models) ? res.models : [];
        setChatModels(list.filter((m) => m.capabilities?.chat));
      })
      .catch(() => {
        /* 选择器数据加载失败不阻塞主流程 */
      });
    profileHttp
      .getBindings()
      .then((b) => {
        setDefaultChatProfile(b?.chat?.profile ?? null);
      })
      .catch(() => {});
  }, []);

  return {
    resumes,
    resumeId,
    setResumeId,
    resumeLoadError,
    sessions,
    chatModels,
    selectedModelId,
    setSelectedModelId,
    effort,
    setEffort,
    defaultChatProfile,
    refreshSessions,
  };
}
