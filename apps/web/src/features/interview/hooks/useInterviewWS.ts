"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { ClientEvent, ServerEvent, TurnState } from "@/types";
import { getEnv } from "@/lib/env";

type ServerHandler<K extends ServerEvent["type"]> = (
  msg: Extract<ServerEvent, { type: K }>,
) => void;

export type WSHandlers = {
  [K in ServerEvent["type"]]?: ServerHandler<K>;
};

export type WSConnectionState = "connecting" | "open" | "reconnecting" | "failed";

/**
 * 与后端 ``/api/v1/ws/interview/{id}`` 双向通信的强类型 Hook。
 *
 * - 回调参数基于 ``Extract<ServerEvent, { type: K }>`` 推导。
 * - handler 经 ref 同步，避免 handler 变化导致重连。
 * - 连接世代号 + 实例比对，防止 React Strict Mode / cleanup 竞态
 *   触发「旧 onclose 误重连 → 服务端踢旧 → 闪屏循环」。
 */
export function useInterviewWS(
  sessionId: number,
  handlers?: WSHandlers,
  options?: { maxRetries?: number },
) {
  const wsRef = useRef<WebSocket | null>(null);
  const handlersRef = useRef<Record<string, (msg: ServerEvent) => void>>({});
  const retryTimerRef = useRef<number | null>(null);
  const retryCountRef = useRef(0);
  /** effect 世代：cleanup 时递增，旧连接回调全部失效 */
  const generationRef = useRef(0);
  const [connected, setConnected] = useState(false);
  /** 是否曾成功连上过（用于页面层区分「首次连接」与「短暂断线」） */
  const [everConnected, setEverConnected] = useState(false);
  const [turnState, setTurnState] = useState<TurnState>("IDLE");
  const [reconnectAttempt, setReconnectAttempt] = useState(0);
  const [connectionState, setConnectionState] = useState<WSConnectionState>("connecting");
  const [reconnectKey, setReconnectKey] = useState(0);
  const maxRetries = options?.maxRetries ?? 5;

  useEffect(() => {
    if (handlers) {
      const next: Record<string, (msg: ServerEvent) => void> = {};
      for (const [type, handler] of Object.entries(handlers)) {
        if (handler) next[type] = handler as (msg: ServerEvent) => void;
      }
      handlersRef.current = next;
    }
  }, [handlers]);

  const on = useCallback(<K extends ServerEvent["type"]>(type: K, handler: ServerHandler<K>) => {
    handlersRef.current[type] = handler as (msg: ServerEvent) => void;
  }, []);

  const send = useCallback((payload: ClientEvent) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(payload));
      return true;
    }
    return false;
  }, []);

  const clearRetryTimer = useCallback(() => {
    if (retryTimerRef.current !== null) {
      window.clearTimeout(retryTimerRef.current);
      retryTimerRef.current = null;
    }
  }, []);

  const cancel = useCallback(() => {
    generationRef.current += 1;
    clearRetryTimer();
    const ws = wsRef.current;
    wsRef.current = null;
    if (ws) {
      try {
        ws.close(1000, "client_cancel");
      } catch {
        /* noop */
      }
    }
    setConnected(false);
    setConnectionState("connecting");
  }, [clearRetryTimer]);

  const retryNow = useCallback(() => {
    retryCountRef.current = 0;
    setReconnectAttempt(0);
    setConnectionState("connecting");
    setReconnectKey((k) => k + 1);
  }, []);

  useEffect(() => {
    // 本 effect 实例的世代；cleanup 后旧回调对比失败即退出
    const generation = ++generationRef.current;
    retryCountRef.current = 0;
    setEverConnected(false);
    setConnected(false);
    setTurnState("IDLE");
    setReconnectAttempt(0);
    setConnectionState("connecting");
    clearRetryTimer();

    const isCurrent = () => generationRef.current === generation;

    if (!Number.isFinite(sessionId) || sessionId <= 0) {
      return () => {
        generationRef.current += 1;
        clearRetryTimer();
      };
    }

    const connect = () => {
      if (!isCurrent()) return;

      // 关闭同 effect 内残留 socket，避免并行双连
      const prev = wsRef.current;
      if (prev) {
        try {
          prev.onclose = null;
          prev.onerror = null;
          prev.onmessage = null;
          prev.close(1000, "replace");
        } catch {
          /* noop */
        }
        if (wsRef.current === prev) wsRef.current = null;
      }

      const wsBase = getEnv().WS_BASE;
      // Cookie 由浏览器自动携带（与 REST 同 host）；不再经子协议传令牌
      const url = `${wsBase}/api/v1/ws/interview/${sessionId}`;
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        if (!isCurrent() || wsRef.current !== ws) {
          try {
            ws.close(1000, "stale");
          } catch {
            /* noop */
          }
          return;
        }
        retryCountRef.current = 0;
        setReconnectAttempt(0);
        setConnected(true);
        setEverConnected(true);
        setConnectionState("open");
      };

      ws.onclose = (ev) => {
        // 仅当前世代 + 当前 socket 才处理；防止 Strict Mode 旧连接误重连
        if (!isCurrent() || wsRef.current !== ws) return;
        wsRef.current = null;
        setConnected(false);

        // 主动关闭 / 被正常替换：不重连
        if (ev.code === 1000 && (ev.reason === "client_cancel" || ev.reason === "replace" || ev.reason === "stale")) {
          return;
        }

        retryCountRef.current += 1;
        if (retryCountRef.current > maxRetries) {
          // 快速重试耗尽：UI 标记 failed，但后台保持长间隔重连（20s）
          setConnectionState("failed");
          clearRetryTimer();
          retryTimerRef.current = window.setTimeout(() => {
            if (isCurrent()) connect();
          }, 20_000);
          return;
        }
        setReconnectAttempt(retryCountRef.current);
        setConnectionState("reconnecting");
        const delay = Math.min(1000 * 2 ** (retryCountRef.current - 1), 8000);
        clearRetryTimer();
        retryTimerRef.current = window.setTimeout(() => {
          if (isCurrent()) connect();
        }, delay);
      };

      ws.onerror = () => {
        // 交给 onclose 统一处理重连，避免双通道
        try {
          ws.close();
        } catch {
          /* noop */
        }
      };

      ws.onmessage = (ev) => {
        if (!isCurrent() || wsRef.current !== ws) return;
        try {
          const msg = JSON.parse(ev.data) as ServerEvent;
          if (msg.type === "turn_state") {
            setTurnState(msg.state);
          }
          if (msg.type === "server_ping") {
            if (ws.readyState === WebSocket.OPEN) {
              ws.send(JSON.stringify({ type: "pong", t: msg.t }));
            }
            return;
          }
          const handler = handlersRef.current[msg.type];
          if (handler) handler(msg);
        } catch {
          /* ignore malformed frame */
        }
      };
    };

    connect();

    return () => {
      // 使本 effect 内所有回调失效
      generationRef.current += 1;
      clearRetryTimer();
      const ws = wsRef.current;
      wsRef.current = null;
      if (ws) {
        try {
          ws.onclose = null;
          ws.onerror = null;
          ws.onmessage = null;
          ws.close(1000, "client_cancel");
        } catch {
          /* noop */
        }
      }
    };
  }, [sessionId, maxRetries, reconnectKey, clearRetryTimer]);

  return {
    connected,
    everConnected,
    turnState,
    reconnectAttempt,
    connectionState,
    send,
    on,
    cancel,
    retryNow,
  };
}
