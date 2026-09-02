/** 面试准备（prep）域的聊天视图类型。 */

import type { PrepSearchGroup, PrepToolStep } from "@/lib/api/contract";
import type { PrepUsageStats } from "@/types";

export interface PrepChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  streaming?: boolean;
  searchGroups?: PrepSearchGroup[];
  steps?: PrepToolStep[];
  /** 模型思考过程(reasoning 事件累计/历史还原),默认折叠展示 */
  thinking?: string;
  statusText?: string;
}

/** 一轮 LLM 流式选项 */
export interface PrepStreamOptions {
  modelProfileId?: number | null;
  reasoningEffort?: string | null;
}

/** 流式回调集合 */
export interface PrepStreamHandlers {
  onToken: (text: string) => void;
  onThinking: (text: string) => void;
  onSearchResults: (groups: PrepSearchGroup[]) => void;
  onStatus: (text: string) => void;
  onToolStep: (step: PrepToolStep) => void;
  onAskUser: (question: string, options: string[]) => void;
  onUsage: (usage: PrepUsageStats) => void;
}
