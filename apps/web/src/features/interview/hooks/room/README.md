# 面试房间运行时 Hooks

## 组装入口

`useInterviewRoom(sessionId)` 是唯一页面消费入口；返回类型 `InterviewRoomModel` 为 UI 契约 SSOT。

## 子 Hook 职责（按装配顺序）

| Hook | 职责 |
| --- | --- |
| `useInterviewRoomBootstrap` | 会话元数据、历史消息、phase 恢复 |
| `useInterviewWS` | WebSocket 连接与 `TurnState`（父目录） |
| `useInterviewRoomState` | UI 状态 + ref 容器 |
| `useInterviewRoomTtsBinding` | TTS 播放与世代对齐 |
| `useInterviewRoomSilenceTimer` | 静默超时 / nudge |
| `useInterviewRoomEvents` | WS 服务端事件处理 |
| `useInterviewRoomActions` | 用户操作（发送、收尾、barge-in） |
| `useInterviewRoomRecorderBridge` | 麦克风/录音桥接 |

## 跨 Hook 数据流

- **状态**：`useInterviewRoomState` 的 `state` + `set` + `refs`
- **WS**：`send` / `on` 来自 `useInterviewWS`；经 `sendRef` 注入子 hook 避免 stale closure
- **录音**：`recorderRef` 由 actions 与 recorder bridge 共享

新增 UI 行为时优先：

1. 判定归属子 hook（勿在 `useInterviewRoom` 堆逻辑）；
2. 若需新 ref，加入 `useInterviewRoomState`；
3. 仅当字段需暴露给页面时加入 `InterviewRoomModel` return。

## 变更半径目标

单一场景改动（如 TTS、静默计时）应限制在 1–2 个 hook 文件内。
