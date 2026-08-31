"use client";

import { useEffect, useRef, useState } from "react";
import { interviewService as api } from "@/lib/api/interviewService";
import { ApiError } from "@/lib/api/base";
import type { GetReportResponse, InterviewReport } from "@/types";

function isReportPending(error: unknown): boolean {
  if (error instanceof ApiError) {
    return error.code === "A2004" || error.retryable || error.status === 404;
  }
  const msg = error instanceof Error ? error.message : String(error);
  return /尚未|A2004/.test(msg);
}

function sleep(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const timer = window.setTimeout(resolve, ms);
    const onAbort = () => {
      window.clearTimeout(timer);
      reject(new DOMException("aborted", "AbortError"));
    };
    if (signal.aborted) {
      onAbort();
      return;
    }
    signal.addEventListener("abort", onAbort, { once: true });
  });
}

function isValidSessionId(id: number): boolean {
  return Number.isFinite(id) && id > 0;
}

/** 报告页加载域:无效 ID 判定、20 次轮询、abort 清理、手动重新生成。 */
export function useReportLoad(sessionId: number) {
  const [report, setReport] = useState<InterviewReport | null>(null);
  const [duration, setDuration] = useState<number | undefined>();
  const [messagesCount, setMessagesCount] = useState<number | undefined>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const sessionIdRef = useRef(sessionId);
  sessionIdRef.current = sessionId;
  const seqRef = useRef(0);

  const applyPayload = (data: GetReportResponse) => {
    setReport(data.report);
    setDuration(data.duration_minutes);
    setMessagesCount(data.messages_count);
  };

  /** 单次拉取(不轮询),供「生成 / 重新加载」在 finish 后调用。 */
  const loadReport = (id: number) => {
    if (!isValidSessionId(id) || id !== sessionIdRef.current) return;
    const seq = ++seqRef.current;
    setLoading(true);
    setError("");
    api
      .getReport(id)
      .then((data) => {
        if (seq !== seqRef.current || id !== sessionIdRef.current) return;
        applyPayload(data);
      })
      .catch((e) => {
        if (seq !== seqRef.current || id !== sessionIdRef.current) return;
        setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (seq !== seqRef.current || id !== sessionIdRef.current) return;
        setLoading(false);
      });
  };

  /** 触发报告生成后再拉取一次。 */
  const retryGenerate = () => {
    const id = sessionIdRef.current;
    if (!isValidSessionId(id)) return;
    setLoading(true);
    api
      .finishInterview(id)
      .catch(() => undefined)
      .finally(() => loadReport(id));
  };

  useEffect(() => {
    const seq = ++seqRef.current;
    if (!isValidSessionId(sessionId)) {
      setReport(null);
      setError("无效的会话 ID");
      setLoading(false);
      return;
    }
    const ac = new AbortController();
    setLoading(true);
    setError("");
    setReport(null);

    const poll = async () => {
      const maxAttempts = 20;
      for (let attempt = 0; attempt < maxAttempts; attempt++) {
        if (ac.signal.aborted || seq !== seqRef.current) return;
        try {
          const data = await api.getReport(sessionId);
          if (ac.signal.aborted || seq !== seqRef.current) return;
          applyPayload(data);
          setError("");
          setLoading(false);
          return;
        } catch (e) {
          if (ac.signal.aborted || seq !== seqRef.current) return;
          if (isReportPending(e)) {
            try {
              await sleep(Math.min(1000 * (attempt + 1), 4000), ac.signal);
            } catch {
              return;
            }
            continue;
          }
          setError(e instanceof Error ? e.message : String(e));
          setLoading(false);
          return;
        }
      }
      if (!ac.signal.aborted && seq === seqRef.current) {
        setError("报告尚未生成。可点击下方按钮生成或重新加载。");
        setLoading(false);
      }
    };

    void poll();
    return () => {
      ac.abort();
    };
  }, [sessionId]);

  return { report, duration, messagesCount, loading, error, retryGenerate };
}
