/** 面试准备域 feature 层。 */

export { AgentSteps } from "./components/AgentSteps";
export { AskUserModal } from "./components/AskUserModal";
export { PrepComposer } from "./components/PrepComposer";
export { PrepEmptyState } from "./components/PrepEmptyState";
export { PrepSessionList } from "./components/PrepSessionList";
export { PrepSidePanel } from "./components/PrepSidePanel";
export { SearchResultCards } from "./components/SearchResultCards";
export { ThinkAnswerMessage } from "./components/ThinkAnswerMessage";
export { AssistantBubble, UserBubble } from "./components/ChatBubbles";
export { usePrepChat } from "./usePrepChat";
export type { PrepChatMessage, PrepStreamHandlers, PrepStreamOptions } from "./types";
export {
  mapHistoryMessages,
  normalizeSearchGroups,
  normalizeSteps,
  normalizeThinking,
} from "./history";
