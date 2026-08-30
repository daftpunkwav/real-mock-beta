"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { agentService as api } from "@/lib/api/agentService";
import { PREP_QUICK_PROMPTS } from "@/config/prepPrompts";
import type { PrepSearchGroup, PrepToolStep, ResumePickerItem } from "@/types";
import {
  AgentSteps,
  AskUserModal,
  SearchResultCards,
  ThinkAnswerMessage,
} from "@/features/prep";
import {
  Send,
  BookOpen,
  Sparkles,
  User,
  Bot,
  FileText,
  Lightbulb,
  MessageSquare,
  Zap,
  ArrowDown,
} from "lucide-react";

const QUICK_PROMPTS = PREP_QUICK_PROMPTS;
const RESTORE_KEY = "realmock_prep_session_id";
/** 距底多少像素内视为「贴着底部」,自动跟随滚动 */
const FOLLOW_THRESHOLD_PX = 96;

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  streaming?: boolean;
  searchGroups?: PrepSearchGroup[];
  steps?: PrepToolStep[];
  statusText?: string;
}

export default function PrepPage() {
  const [resumes, setResumes] = useState<ResumePickerItem[]>([]);
  const [resumeId, setResumeId] = useState<number | null>(null);
  const [prepSessionId, setPrepSessionId] = useState<number | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [restoring, setRestoring] = useState(false);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [starting, setStarting] = useState(false);
  const [prepError, setPrepError] = useState("");
  const [resumeLoadError, setResumeLoadError] = useState("");
  const [tokenUsage, setTokenUsage] = useState(0);
  const [askDialog, setAskDialog] = useState<{
    question: string;
    options: string[];
  } | null>(null);
  const [showJump, setShowJump] = useState(false);
  const chatScrollRef = useRef<HTMLDivElement>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const msgSeqRef = useRef(0);
  const followRef = useRef(true);
  const loadingRef = useRef(false);
  const pendingSendRef = useRef("");
  // 流式 token 先进缓冲,按帧批量上屏,避免逐 token 触发全列表重渲染
  const pendingTokenRef = useRef<{ id: string; text: string } | null>(null);
  const rafRef = useRef(0);

  function nextMsgId(prefix: string) {
    msgSeqRef.current += 1;
    return `${prefix}-${msgSeqRef.current}`;
  }

  useEffect(() => {
    api
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

  // 恢复上次辅导会话(刷新不丢上下文;消息不含检索卡片与执行步骤)
  useEffect(() => {
    const saved = Number(window.localStorage.getItem(RESTORE_KEY) || 0);
    if (!saved) return;
    setRestoring(true);
    api
      .prepMessages(saved)
      .then((list) => {
        const restored: ChatMessage[] = (Array.isArray(list) ? list : [])
          .filter((m) => (m.role === "user" || m.role === "assistant") && m.content)
          .map((m) => ({
            id: nextMsgId(m.role === "user" ? "u" : "a"),
            role: m.role === "user" ? "user" : "assistant",
            content: String(m.content),
          }));
        if (restored.length === 0) throw new Error("empty session");
        setPrepSessionId(saved);
        setMessages(restored);
      })
      .catch(() => window.localStorage.removeItem(RESTORE_KEY))
      .finally(() => setRestoring(false));
  }, []);

  const selectedResume = useMemo(
    () => resumes.find((r) => r.id === resumeId) ?? null,
    [resumes, resumeId],
  );

  /* ── 滚动:默认贴底跟随;用户上滑后以用户为准,提供回底按钮 ── */
  const handleScroll = useCallback(() => {
    const el = chatScrollRef.current;
    if (!el) return;
    const atBottom =
      el.scrollHeight - el.scrollTop - el.clientHeight < FOLLOW_THRESHOLD_PX;
    followRef.current = atBottom;
    setShowJump(!atBottom);
  }, []);

  useEffect(() => {
    if (!followRef.current) return;
    const el = chatScrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages]);

  const jumpToBottom = useCallback(() => {
    followRef.current = true;
    setShowJump(false);
    const el = chatScrollRef.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, []);

  /* ── token 批量上屏 ── */
  const flushPendingToken = useCallback(() => {
    rafRef.current = 0;
    const p = pendingTokenRef.current;
    if (!p) return;
    pendingTokenRef.current = null;
    setMessages((m) =>
      m.map((msg) =>
        msg.id === p.id ? { ...msg, content: msg.content + p.text } : msg,
      ),
    );
  }, []);

  const queueToken = useCallback(
    (id: string, text: string) => {
      const p = pendingTokenRef.current;
      if (p && p.id === id) {
        p.text += text;
      } else {
        if (p) flushPendingToken();
        pendingTokenRef.current = { id, text };
      }
      if (!rafRef.current) {
        rafRef.current = requestAnimationFrame(flushPendingToken);
      }
    },
    [flushPendingToken],
  );

  useEffect(
    () => () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    },
    [],
  );

  const patchMessage = useCallback((id: string, patch: Partial<ChatMessage>) => {
    setMessages((m) => m.map((msg) => (msg.id === id ? { ...msg, ...patch } : msg)));
  }, []);

  const startPrep = async () => {
    setStarting(true);
    setPrepError("");
    try {
      const { id } = await api.createPrepSession({ resume_id: resumeId ?? undefined });
      setPrepSessionId(id);
      window.localStorage.setItem(RESTORE_KEY, String(id));
      setMessages([
        {
          id: nextMsgId("a"),
          role: "assistant",
          content: "你好!我是你的面试准备教练。告诉我你的目标岗位,或让我帮你分析简历、出题练习。",
        },
      ]);
      return id;
    } catch (e) {
      setPrepError(e instanceof Error ? e.message : "创建辅导会话失败");
      return null;
    } finally {
      setStarting(false);
    }
  };

  const sendMessage = async (text: string, sessionId?: number) => {
    const sid = sessionId ?? prepSessionId;
    if (!text.trim() || !sid || loadingRef.current) return;

    const userMsg = text.trim();
    const assistantId = nextMsgId("a");
    setInput("");
    loadingRef.current = true;
    setLoading(true);
    followRef.current = true;
    setShowJump(false);
    setMessages((m) => [
      ...m,
      { id: nextMsgId("u"), role: "user", content: userMsg },
      { id: assistantId, role: "assistant", content: "", streaming: true },
    ]);

    try {
      const result = await api.prepMessageStream(sid, userMsg, {
        onToken: (token) => queueToken(assistantId, token),
        onSearchResults: (groups) => {
          setMessages((m) =>
            m.map((msg) =>
              msg.id === assistantId
                ? {
                    ...msg,
                    searchGroups: [...(msg.searchGroups ?? []), ...groups],
                  }
                : msg,
            ),
          );
        },
        onStatus: (text) => {
          if (text) patchMessage(assistantId, { statusText: text });
        },
        onToolStep: (step) => {
          setMessages((m) =>
            m.map((msg) =>
              msg.id === assistantId
                ? { ...msg, steps: [...(msg.steps ?? []), step] }
                : msg,
            ),
          );
        },
        onAskUser: (question, options) => {
          flushPendingToken();
          patchMessage(assistantId, { statusText: "" });
          setAskDialog({ question, options });
        },
      });
      flushPendingToken();
      setTokenUsage(result.token_usage);
      patchMessage(assistantId, { streaming: false, statusText: "" });
    } catch (e) {
      flushPendingToken();
      setMessages((m) =>
        m.map((msg) =>
          msg.id === assistantId
            ? {
                ...msg,
                streaming: false,
                statusText: "",
                content: msg.content || `错误:${e instanceof Error ? e.message : "失败"}`,
              }
            : msg,
        ),
      );
    } finally {
      loadingRef.current = false;
      setLoading(false);
      const pending = pendingSendRef.current;
      pendingSendRef.current = "";
      if (pending) {
        setTimeout(() => sendMessage(pending), 50);
      }
    }
  };

  const handleSend = () => sendMessage(input);

  const handleAskAnswer = (text: string) => {
    setAskDialog(null);
    if (loadingRef.current) {
      pendingSendRef.current = text;
      return;
    }
    sendMessage(text);
  };

  const handleQuickPrompt = async (prompt: string) => {
    if (restoring) return; // 会话恢复中,避免误创建新会话
    if (!prepSessionId) {
      const id = await startPrep();
      if (!id) return;
      await sendMessage(prompt, id);
      return;
    }
    sendMessage(prompt);
  };

  return (
    <div className="page-shell !max-w-6xl flex h-full min-h-0 flex-col overflow-hidden !pb-4 anim-rise">
      <div className="page-header !mb-4 shrink-0">
        <div className="flex items-start gap-3">
          <span className="icon-badge icon-badge-brand">
            <BookOpen size={18} strokeWidth={1.75} />
          </span>
          <div>
            <p className="page-eyebrow">Prep Coach</p>
            <h1 className="page-title">面试准备</h1>
            <p className="page-desc">ReAct 辅导 Agent — 简历分析、面经搜索、主动出题。</p>
          </div>
        </div>
      </div>

      <div className="grid min-h-0 flex-1 grid-cols-1 gap-5 overflow-hidden lg:grid-cols-[1fr_300px]">
        {/* 左侧:对话主区 */}
        <div className="flex min-h-0 flex-col overflow-hidden">
          {!prepSessionId ? (
            <div className="surface-card flex flex-1 flex-col justify-center overflow-hidden p-8">
              <div className="mx-auto w-full max-w-md space-y-5">
                <div className="text-center">
                  <span className="icon-badge icon-badge-brand mx-auto mb-4 !h-14 !w-14">
                    <Sparkles size={22} strokeWidth={1.75} />
                  </span>
                  <h2 className="text-[18px] font-semibold tracking-tight text-ink">
                    开始你的面试辅导
                  </h2>
                  <p className="mt-1.5 text-[13px] text-ink-muted">
                    关联简历后,AI 教练将基于你的背景进行针对性辅导。
                  </p>
                </div>

                {resumeLoadError ? (
                  <div className="alert alert-error !block text-center">{resumeLoadError}</div>
                ) : resumes.length > 0 ? (
                  <div>
                    <label className="field-label">关联简历</label>
                    <select
                      className="field-select"
                      value={resumeId ?? ""}
                      onChange={(e) => setResumeId(Number(e.target.value))}
                    >
                      {resumes.map((r) => (
                        <option key={r.id} value={r.id}>
                          {r.filename}
                          {r.is_active ? " (投递)" : ""}
                        </option>
                      ))}
                    </select>
                  </div>
                ) : (
                  <div className="alert alert-warning !block text-center">
                    暂无简历,可先去「简历管理」上传,也可直接开始通用辅导
                  </div>
                )}

                {prepError && (
                  <div className="alert alert-error !block text-center">{prepError}</div>
                )}

                <button
                  type="button"
                  onClick={startPrep}
                  disabled={starting}
                  className="btn-primary !h-10 w-full"
                >
                  {starting ? (
                    <span className="block h-3.5 w-3.5 anim-spin rounded-full border-2 border-current border-t-transparent" />
                  ) : (
                    <Sparkles size={14} />
                  )}
                  {starting ? "正在连接…" : "开始辅导"}
                </button>
              </div>
            </div>
          ) : (
            <>
              <div className="mb-2 flex shrink-0 items-center justify-between px-1 text-[11px] text-ink-subtle">
                <span className="chip chip-green !text-[10px]">
                  <span className="mr-1 inline-block h-1.5 w-1.5 rounded-full bg-[var(--success)]" />
                  辅导中 · {messages.length} 条
                </span>
                <span className="font-mono num-tabular">Token ≈ {tokenUsage || 0}</span>
              </div>
              <div className="relative min-h-0 flex-1">
                <div
                  ref={chatScrollRef}
                  onScroll={handleScroll}
                  className="surface-card h-full space-y-3.5 overflow-y-auto p-4"
                >
                  {messages.map((m) => (
                    <div
                      key={m.id}
                      className={`flex gap-2.5 ${m.role === "user" ? "flex-row-reverse" : ""}`}
                    >
                      <span
                        className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${
                          m.role === "user"
                            ? "bg-[var(--primary)] text-white"
                            : "bg-[var(--info-soft)] text-[var(--info-ink)]"
                        }`}
                      >
                        {m.role === "user" ? <User size={14} /> : <Bot size={14} />}
                      </span>
                      <div
                        className={`min-w-0 max-w-[88%] rounded-md px-3.5 py-2.5 text-[13px] leading-relaxed ${
                          m.role === "user"
                            ? "rounded-br-sm bg-[var(--primary)] text-white"
                            : "rounded-bl-sm border border-surface-border bg-surface-alt text-ink"
                        }`}
                      >
                        {m.role === "assistant" ? (
                          <div className="space-y-2">
                            {m.streaming && m.statusText ? (
                              <p className="flex items-center gap-1.5 text-[11px] text-ink-muted">
                                <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[var(--primary)]" />
                                {m.statusText}
                              </p>
                            ) : null}
                            {!m.streaming && m.steps && m.steps.length > 0 ? (
                              <AgentSteps steps={m.steps} />
                            ) : null}
                            {!m.streaming && m.searchGroups && m.searchGroups.length > 0 ? (
                              <SearchResultCards groups={m.searchGroups} />
                            ) : null}
                            <ThinkAnswerMessage
                              content={m.content}
                              streaming={!!m.streaming}
                            />
                          </div>
                        ) : (
                          m.content
                        )}
                      </div>
                    </div>
                  ))}
                  <div ref={endRef} />
                </div>
                {showJump && (
                  <button
                    type="button"
                    onClick={jumpToBottom}
                    className="btn-primary absolute bottom-3 right-3 !h-9 !w-9 rounded-full !p-0 shadow-lg"
                    aria-label="回到底部"
                  >
                    <ArrowDown size={15} />
                  </button>
                )}
              </div>
              <div className="mt-3 flex shrink-0 gap-2">
                <input
                  className="field-input flex-1"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleSend()}
                  placeholder="问我任何面试相关问题…"
                  disabled={loading}
                />
                <button
                  type="button"
                  onClick={handleSend}
                  disabled={loading}
                  className="btn-primary !h-9 !w-12 shrink-0 !px-0"
                  aria-label="发送"
                >
                  {loading ? (
                    <span className="block h-3.5 w-3.5 anim-spin rounded-full border-2 border-current border-t-transparent" />
                  ) : (
                    <Send size={14} />
                  )}
                </button>
              </div>
            </>
          )}
        </div>

        {/* 右侧:上下文与快捷操作 */}
        <div className="hidden min-h-0 flex-col gap-3 overflow-y-auto pr-0.5 lg:flex">
          <div className="surface-card p-4">
            <h2 className="mb-3 flex items-center gap-2 text-[13px] font-semibold tracking-tight text-ink">
              <FileText size={14} className="text-[var(--primary)]" />
              关联简历
            </h2>
            {selectedResume ? (
              <>
                <p className="truncate text-[13px] font-medium text-ink">
                  {selectedResume.filename}
                </p>
                <p className="mt-1 text-[11px] text-ink-subtle">
                  {selectedResume.is_active ? "当前投递" : "未设为投递"}
                  {selectedResume.score != null && ` · 评分 ${selectedResume.score}`}
                </p>
              </>
            ) : (
              <p className="text-[12px] text-ink-subtle">未关联简历,将进行通用辅导</p>
            )}
          </div>

          <div className="surface-card p-4">
            <h2 className="mb-3 flex items-center gap-2 text-[13px] font-semibold tracking-tight text-ink">
              <Zap size={14} className="text-[var(--warning)]" />
              快捷提问
            </h2>
            <div className="space-y-1.5">
              {QUICK_PROMPTS.map((prompt) => (
                <button
                  key={prompt}
                  type="button"
                  onClick={() => handleQuickPrompt(prompt)}
                  disabled={loading}
                  className="w-full rounded-md border border-surface-border px-3 py-2 text-left text-[12px] leading-relaxed text-ink-muted transition-colors hover:border-[var(--primary)] hover:bg-[var(--info-soft)] hover:text-ink disabled:opacity-50"
                >
                  {prompt}
                </button>
              ))}
            </div>
          </div>

          <div className="surface-card p-4">
            <h2 className="mb-3 flex items-center gap-2 text-[13px] font-semibold tracking-tight text-ink">
              <MessageSquare size={14} className="text-[var(--primary)]" />
              会话状态
            </h2>
            <div className="grid grid-cols-2 gap-2 text-center">
              <div className="kpi-card !p-3">
                <p className="kpi-value !text-xl">
                  {prepSessionId ? messages.length : 0}
                </p>
                <p className="kpi-label mt-1">消息数</p>
              </div>
              <div className="kpi-card !p-3">
                <p className="kpi-value !text-xl">{tokenUsage || "—"}</p>
                <p className="kpi-label mt-1">Token</p>
              </div>
            </div>
          </div>

          <div className="surface-card p-4">
            <h2 className="mb-2.5 flex items-center gap-2 text-[13px] font-semibold tracking-tight text-ink">
              <Lightbulb size={14} className="text-[var(--primary)]" />
              使用提示
            </h2>
            <ul className="space-y-2 text-[11px] leading-relaxed text-ink-subtle">
              <li>· 教练需要确认方向时会弹出选择框,点击选项即可回答</li>
              <li>· 检索来源与执行过程默认折叠,可展开查看</li>
              <li>· 描述目标公司与岗位,获得针对性模拟题</li>
              <li>· 输出时向上滑动可自由阅读,点右下角按钮回到底部</li>
            </ul>
          </div>
        </div>
      </div>

      {askDialog && (
        <AskUserModal
          question={askDialog.question}
          options={askDialog.options}
          onAnswer={handleAskAnswer}
          onClose={() => setAskDialog(null)}
        />
      )}
    </div>
  );
}
