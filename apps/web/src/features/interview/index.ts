/** 面试业务 feature 层。 */

export { ChatBubble } from "./components/ChatBubble";
export { VideoPanel, type VideoPanelHandle } from "./components/VideoPanel";
export { InterviewRoomView } from "./components/InterviewRoomView";
export { useInterviewWS } from "./hooks/useInterviewWS";
export { useInterviewRoomBootstrap } from "./hooks/useInterviewRoomBootstrap";
export { useInterviewRoom } from "./hooks/useInterviewRoom";
export { isLikelyEchoOfAssistant, normalizeEchoText } from "./echo";
export { toVisibleChatMessages } from "./messages";
