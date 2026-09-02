# 面试 WebSocket 实时层

## 组装结构

`InterviewWSHandler`（`ws_handler.py`）是**薄组装壳**，通过 mixin 栈组合能力：

| 栈 | 模块 | 职责 |
| --- | --- | --- |
| ConnectionStack | `connection/auth`, `heartbeat`, `lifecycle` | 鉴权、心跳、连接生命周期 |
| TurnStack | `turn/coordinator` + `control` + `streaming` | 话轮锁、STT/TTS 流、打断/收尾 |
| MediaStack | `voice/pipeline`, `voice/tts_queue` | 语音管道与分句 TTS |
| MessageDispatcher | `core/message_dispatcher` | 客户端事件分发 |
| ReportScheduler | `report_scheduler` | 后台报告生成 |

**禁止**在 `ws_handler.py` 再叠加新 mixin；新能力应：

1. 扩展 `ConnectionContext` 字段（若需新状态）；
2. 在对应子包实现 mixin；
3. 经现有 stack 聚合，不增加 MRO 深度。

## 状态 SSOT

所有 mixin 通过 `self.ctx: ConnectionContext` 读写状态，**不得**在 mixin 上声明重复宿主字段。

字段清单见 `core/context.py`；新增字段须同步更新该 dataclass 与本文档。

## 测试 patch 约定

话轮 STT 等测试 patch 目标保持 `interview_service.realtime.turn.coordinator.*` 模块级符号，勿改为类方法 patch。

## 变更半径

修改话轮行为通常涉及 `turn/` 与 `control/`；修改连接行为涉及 `connection/`。跨栈改动前评估是否应下沉到 `ConnectionContext` 或共享服务层。
