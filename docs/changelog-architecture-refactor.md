# 架构改进修改日志

**日期：** 2026-08-28  
**依据：** `docs/architecture-review-2026-08-28.md` 审查报告  
**验证：** 351 pytest + 33 npm test + build 全部通过

---

## 第一阶段：shared 包精简

### 1.1 拆分 `shared/capabilities/ai/llm/client.py` → `client/` 包

**原因：** 原文件 654 行，混合了重试逻辑、文本提取、环境检查、LLM 客户端、统一客户端、工具参数解析。

**改动：**

| 操作 | 文件 |
|------|------|
| 新建 | `services/shared/capabilities/ai/llm/client/__init__.py` |
| 新建 | `services/shared/capabilities/ai/llm/client/base.py` — `_retry_request`, `_extract_message_text`, `_is_local_allowed`, `_require_https` |
| 移动 | `client.py` → `client/llm_client.py` — `LLMClient` 类 |
| 移动 | `unified_client.py` → `client/unified_client.py` — `UnifiedLLMClient` 类 |
| 移动 | `tool_args.py` → `client/tool_args.py` — `parse_tool_arguments` |
| 新建 | `services/shared/capabilities/ai/llm/unified_client.py` — thin wrapper re-export |
| 新建 | `services/shared/capabilities/ai/llm/tool_args.py` — thin wrapper re-export |
| 删除 | 原 `client.py`、`unified_client.py`、`tool_args.py` |

**兼容性：** 所有现有 import 路径通过 `__init__.py` re-export 和 thin wrapper 保持不变。

**测试修复：**
- `services/tests/test_llm_client_retry.py` — monkeypatch 路径更新为 `client.llm_client.*` 和 `client.base.*`
- `services/tests/test_rag_backends.py` — `import ... as llm_mod` 更新为 `client.llm_client`

---

### 1.2 拆分 `shared/core/security.py` → `security/` 包

**原因：** 原文件 519 行，混合了文件安全、URL/SSRF 过滤、DNS pin、API Key 脱敏。

**改动：**

| 操作 | 文件 |
|------|------|
| 新建 | `services/shared/core/security/__init__.py` — re-export 全部公共符号 |
| 新建 | `services/shared/core/security/file.py` — `sanitize_filename`, `assert_within_dir` |
| 新建 | `services/shared/core/security/url.py` — `UnsafeURLError`, `is_safe_http_url`, `PinnedHostTransport`, `make_pinned_async_client` 等 |
| 新建 | `services/shared/core/security/redact.py` — `redact_api_key` |
| 删除 | 原 `security.py` |

**兼容性：** `from shared.core.security import ...` 路径不变。

**测试修复：**
- `services/tests/conftest.py` — `from shared.core.security import url as security_url`
- `services/tests/test_security.py` — monkeypatch 路径更新
- `services/tests/test_security_extra.py` — monkeypatch 路径更新
- `services/tests/sessions/test_session_ssrf_pin.py` — monkeypatch 路径更新

---

### 1.3 提取 `LLMSettings`/`StageConfig` 到 `shared/core/config_models.py`

**原因：** 这两个 ORM 模型是基础设施配置，不属于业务域，与 `Resume`/`UserProfile` 混在 `shared/models` 中。

**改动：**

| 操作 | 文件 |
|------|------|
| 新建 | `services/shared/core/config_models.py` — `StageConfig`, `LLMSettings` |
| 修改 | `services/shared/models/__init__.py` — 从 `config_models` re-export，保留 `Resume`, `UserProfile` |

**兼容性：** `from shared.models import LLMSettings, StageConfig` 路径不变。

---

## 第二阶段：interview_service 实时层重构

### 2.1 新建 `ConnectionContext` dataclass

**原因：** 7 个 mixin 通过 `TYPE_CHECKING` 声明宿主字段契约，运行时靠隐式 `self.xxx` 访问，新增字段需在多处同步。

**改动：**

| 操作 | 文件 |
|------|------|
| 新建 | `services/interview_service/realtime/context.py` — `ConnectionContext` dataclass，集中 34 个可变字段 |

### 2.2 重构 7 个 mixin 使用 `self.ctx`

**改动文件：**

| 文件 | 改动要点 |
|------|----------|
| `realtime/connection_lifecycle.py` | 删除 TYPE_CHECKING 块，`self.xxx` → `self.ctx.xxx`，`send`/`set_turn` 等方法保留 |
| `realtime/turn_coordinator.py` | 同上 |
| `realtime/turn_control.py` | 同上 |
| `realtime/turn_streaming.py` | 同上 |
| `realtime/voice_pipeline.py` | 同上 |
| `realtime/hint_service.py` | 同上 |
| `realtime/report_scheduler.py` | 同上 |
| `realtime/ws_handler.py` | `__init__` 改为构造 `ConnectionContext`；添加 `session_id`/`ws`/`_superseded` 委托属性以满足 `SessionConnection` 协议 |

**测试修复：**
- `services/tests/test_ws_handler.py` — `handler.xxx` → `handler.ctx.xxx`，monkeypatch 路径更新
- `services/tests/test_ws_hardening.py` — 同上
- `services/tests/test_cloud_stt.py` — 同上
- `services/tests/sessions/test_session_auth_and_audio_buffer.py` — 同上
- `services/tests/sessions/test_session_ws_mutex.py` — 同上

---

## 第三阶段：前端重组

### 3.1 创建 `features/interview/` 业务层

**改动：**

| 操作 | 文件 |
|------|------|
| 新建 | `apps/web/src/features/interview/components/ChatBubble.tsx` |
| 新建 | `apps/web/src/features/interview/index.ts` |
| 修改 | `apps/web/src/app/interview/[id]/page.tsx` — 删除内联 `ChatBubble`，改为从 `@/features/interview` 导入 |

### 3.3 类型按域拆分

**原因：** `types/index.ts` 506 行，包含全部前端类型，合并冲突风险高。

**改动：**

| 操作 | 文件 |
|------|------|
| 新建 | `apps/web/src/types/api.ts` — LLM/Stage 配置、语音目录、错误 envelope |
| 新建 | `apps/web/src/types/interview.ts` — 面试/报告/成长/SSE/WebSocket 事件 |
| 新建 | `apps/web/src/types/profile.ts` — 用户档案/简历/企业信息/选项 |
| 修改 | `apps/web/src/types/index.ts` — 改为 barrel `export * from "./api" \| "./interview" \| "./profile"` |

**兼容性：** `from "@/types"` 路径不变。

---

## 第四阶段：清理

### 4.1 删除空 `__init__.py`

从 29 个减少到 9 个。删除了 20 个无 re-export 的空包标识文件（`agents/prep/__init__.py`、`routes/__init__.py`、`services/__init__.py` 等）。保留了服务根、shared 根、tests 根等必要的。

### 4.2 兼容代码 DEPRECATED 标记

| 文件 | 位置 |
|------|------|
| `shared/schemas/__init__.py:76` | `LLMSettingsUpdate` — DEPRECATED: 将在 v2.0 移除 |
| `api_service/routes/settings.py:96` | `get_llm_settings` — DEPRECATED: 将在 v2.0 移除 |
| `api_service/routes/settings.py:139` | `update_llm_settings` — DEPRECATED: 将在 v2.0 移除 |
| `api_service/routes/settings.py:247` | `test_llm_connection` — DEPRECATED: 将在 v2.0 移除 |
| `shared/capabilities/voice/stt/__init__.py:42` | `transcribe_utterance` — DEPRECATED: 请使用 `transcribe_utterance_result` |

---

## 未完成项（可后续推进）

| 项 | 优先级 | 说明 |
|----|--------|------|
| 3.2 拆分 resume/profile/settings 大页面 | 高 | 页面 600-800 行，需抽取子组件 |
| 3.4 Server Component 优化 | 中 | 需检查父组件依赖链，部分组件可删除 `use client` |
| 5 前端 hook 测试覆盖 | 中 | `useInterviewWS`、`useAudioRecorder`、`useTTSPlayer` 无测试 |
| 6 文件上传统一封装 | 低 | `apiService.uploadResume` 未走统一 `request()` |

---

## 影响范围

- **后端生产文件改动：** 20+ 个 Python 文件
- **后端测试文件改动：** 8 个测试文件
- **前端文件改动：** 5 个（页面 + 类型 + 新组件）
- **新建文件：** 15 个（包 `__init__.py`、拆分后的模块、新组件）
- **删除文件：** 5 个（旧的单文件模块）
- **向后兼容：** 所有公共 import 路径保持不变
