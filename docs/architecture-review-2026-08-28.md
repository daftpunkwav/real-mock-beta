# RealMock 项目架构审查报告

**审查日期：** 2026-08-28  
**审查依据：** 以代码为唯一真相，不依赖 README 或文档。  
**审查范围：**

- 后端：`services/` 下全部 Python 代码（含 `api_service`、`agent_service`、`interview_service`、`shared` 及聚合入口 `services/main.py`）。
- 前端：`apps/web/src/` 下全部 TypeScript / TSX 代码。
- 不涉及：构建配置、CI、非代码文档、静态资源。

---

## 1. 执行摘要

### 1.1 总体评分

| 维度 | 评分 | 说明 |
|------|------|------|
| 后端架构健康度 | 6 / 10 | 模块化单体方向正确，三服务边界基本清晰；但 `interview_service` 内部严重膨胀，`shared` 职责过重，命名空间与兼容代码侵蚀主线。 |
| 前端架构健康度 | 5 / 10 | Next.js App Router 目录结构可用，`@/` alias 一致；但页面组件过大、`use client` 泛滥、`features` 层未承担业务封装、测试覆盖薄弱。 |
| 可维护性 | 5 / 10 | 面试核心逻辑耦合在 WebSocket 生命周期与 mixin 中，新人理解成本高；前后端类型契约靠手工同步，易漂移。 |
| 安全性 | 7 / 10 | CORS、请求 ID、URL 安全、文件上传校验、访问令牌等已有集中处理；但大文件/长 LLM 任务仍存在 DoS 敞口。 |

### 1.2 最关键的发现

1. **`interview_service` 已成为事实上的“巨石服务”**：其内部 import 占总服务间 import 的绝大部分，且核心实时面试代码集中在少数超大文件中。
2. **`shared` 包正在变成“通用垃圾堆”**：LLM 客户端、安全配置、Pipeline 配置、密钥管理等功能膨胀，缺乏进一步拆分。
3. **前端页面组件过大**：`app/interview/[id]/page.tsx` 接近 1000 行，84 个函数/箭头函数、65 个 hook 调用，接近“上帝页面”。
4. **空 `__init__.py` 与兼容代码大量存在**：30 个空包 + 20 余处“兼容旧”分支，反映重构过程中未彻底清理历史包袱。
5. **类型契约前后端重复**：后端 Pydantic 模型与前端 `types/index.ts` 手工同步，未来拆分为微服务或调整字段时风险高。

---

## 2. 后端架构审查

### 2.1 顶层结构

项目采用“模块化单体”模式：

```
services/
├── main.py                  # 聚合入口：api_service + agent_service + interview_service
├── api_service/             # 基础 API：profile / resume / settings
├── agent_service/           # 智能体：面试准备教练 prep
├── interview_service/       # 模拟面试引擎、实时 WebSocket、报告、成长
└── shared/                  # 平台能力：DB、配置、LLM、语音、搜索、安全等
```

**验证结果：**

- 三服务之间没有业务循环依赖，仅通过 `shared` 共享基础设施与模型。
- `services/main.py` 聚合三个 `service_router`，并注入 `/api/v1` 前缀，同时保留 `/api` 兼容别名。
- 各服务可独立启动（`api_service/main.py`、`agent_service/main.py`、`interview_service/main.py`），共享 `shared/app_factory.py`。

**结论：** 顶层服务拆分合理，符合“先单体、后可拆”的演进策略。

### 2.2 服务间依赖关系

通过 AST 统计生产文件中的 `from X import`：

| 被 import 的顶层包 | 次数 | 占比 |
|------------------|------|------|
| `shared` | 278 | ~70% |
| `interview_service` | 100 | ~25% |
| `api_service` | 11 | ~3% |
| `agent_service` | 7 | ~2% |

**分析：**

- `shared` 被高频依赖是正常的，但其中大量 import 指向 `shared.capabilities.ai.llm.client`、`shared.core.security`、`shared.services.pipeline_config` 等超重模块。
- `interview_service` 内部自引用 100 次，说明该服务内部模块高度耦合。
- `api_service` / `agent_service` 之间几乎无交互，符合边界设计。

**未发现跨服务业务 import：** 没有 `api_service` 直接 import `interview_service` 的业务模块，反之亦然。

### 2.3 目录与命名空间问题

#### 2.3.1 `interview_service` 内部目录重复且语义不清

| 路径 | 问题 |
|------|------|
| `interview_service/services/interview/` | 双重复 `interview`，无额外语义。 |
| `interview_service/agents/orchestrator.py` | 名为“统筹 Agent”，实际只处理 silence nudge 与随机追问。 |
| `interview_service/agents/vision/agent.py` | 名为 Agent，更像视觉分析器/预处理器。 |
| `interview_service/agents/snapshot.py` | `SessionSnapshot` 被 `events.py` re-export 并标注“旧调用方仍可用”。 |
| `interview_service/capabilities/rag/` | 企业知识库 RAG 放在 `interview_service` 是对的，但与 `shared/capabilities/knowledge/company/` 并存，职责边界模糊。 |

**建议：**

- `interview_service/services/interview/` → 拆分为 `engine/`（runner、agent、prompts、tools）和 `domain/`（workflows、report、followup）。
- `interview_service/agents/orchestrator.py` → 改名为 `nudge.py` 或 `context_builder.py`。
- `interview_service/agents/vision/agent.py` → 改名为 `vision_analyzer.py` 或移到 `realtime/vision/`。

#### 2.3.2 `agent_service` 目录单薄但命名同样混乱

| 路径 | 问题 |
|------|------|
| `agent_service/agents/prep/agent.py` | 真正的 LLM Agent。 |
| `interview_service/services/interview/agent.py` | 实际是“会话状态机/数据层”。 |

两者都叫 `Agent`，但职责完全不同，阅读代码时容易混淆。

### 2.4 `shared` 包职责过重

#### 2.4.1 超重模块

| 文件 | 行数 | 问题 |
|------|------|------|
| `shared/capabilities/ai/llm/client.py` | 653 | 统一 LLM 客户端 + StageConfig/LLMSettings 读取 + 环境变量回退 + retry 逻辑。 |
| `shared/core/security.py` | 518 | URL 安全、文件名安全、文件路径校验、pinned async client 等。 |
| `shared/services/pipeline_config.py` | 334 | 三阶段配置解析，与 `api_service/routes/settings.py`、`client.py` 形成三角依赖。 |
| `shared/core/session_auth.py` | 261 | Cookie、WS 子协议令牌、CSRF、访问令牌生成。 |
| `shared/core/migrate.py` | 205 | 列迁移逻辑。 |
| `shared/schemas/__init__.py` | 217 | 包含错误 envelope、LLM 设置、StageConfig、CompanyInfo、CandidateProfile 等多种契约。 |

#### 2.4.2 能力下沉不彻底

- `shared/capabilities/knowledge/company/knowledge.py`：存放企业知识数据，被 `agent_service` 和 `interview_service` 共用。
- `interview_service/capabilities/rag/`：存放 RAG 后端实现。

两者同时存在，导致“企业知识”这一概念被拆到两个服务、两个能力层。

**建议：**

- 把 `shared/capabilities/ai/llm/client.py` 拆为 `client/base.py`、`client/providers.py`、`client/auth.py`、`client/stage_resolver.py`。
- 把 `shared/core/security.py` 拆为 `security/url.py` 和 `security/file.py`。
- 明确 `shared/capabilities/knowledge/` 与 `interview_service/capabilities/rag/` 的分工：前者只放跨服务共享的“公司元数据”，后者只放面试域 RAG 实现。

### 2.5 空 `__init__.py` 统计

生产环境中发现 **30 个空 `__init__.py`**，包括：

- `services/agent_service/agents/__init__.py`
- `services/agent_service/routes/__init__.py`
- `services/api_service/routes/__init__.py`
- `services/api_service/services/__init__.py`
- `services/interview_service/agents/__init__.py`
- `services/interview_service/routes/__init__.py`
- `services/interview_service/services/__init__.py`
- `services/interview_service/services/interview/__init__.py`
- `services/shared/capabilities/ai/__init__.py`
- `services/shared/capabilities/integrations/__init__.py`
- `services/shared/capabilities/knowledge/__init__.py`
- `services/shared/capabilities/voice/__init__.py`
- `services/shared/core/__init__.py`
- `services/shared/services/__init__.py`

**影响：**

- 增加了目录层级，却无聚合导出价值。
- 使得 `from interview_service.services.interview import runner` 这类路径看起来有包，实际只是文件路径。

**建议：** 对于没有 re-export 或文档说明的包，删除空 `__init__.py`（Python 3.3+ 支持 namespace package），或填充有意义的聚合导出。

### 2.6 兼容代码与历史包袱

搜索到 **20+ 处**“兼容旧”标记，典型位置：

| 位置 | 内容 |
|------|------|
| `shared/models/__init__.py:66` | 兼容旧字段：识别模型 / Edge 音色 |
| `shared/schemas/__init__.py:77` | 兼容旧版三阶段统一保存；内部会拆到 stage_configs |
| `api_service/routes/settings.py:96` | 兼容旧版设置读取 |
| `api_service/routes/settings.py:139` | 兼容旧版统一保存：拆分到 stage_configs |
| `api_service/routes/resume.py:50` | `ALLOWED_EXTENSIONS = RESUME_ALLOWED_EXTENSIONS # 兼容旧引用` |
| `api_service/schemas/__init__.py:113` | 兼容旧字段 strengths/weaknesses/… |
| `interview_service/realtime/events.py:35` | 旧调用方 `from interview_service.realtime.events import SessionSnapshot` 仍可用 |
| `interview_service/realtime/voice_pipeline.py:109` | 兼容旧调用：仅更新音色 |
| `interview_service/realtime/ws_handler.py:61` | 兼容测试 / 外部 import |
| `interview_service/realtime/ws_handler.py:162` | 兼容旧接口 |
| `shared/capabilities/ai/llm/client.py:161` | 优先从 stage_configs 读取；否则兼容旧 LLMSettings 与环境变量 |
| `shared/capabilities/voice/stt/__init__.py:42` | 转写一整段用户发言，返回纯文本（兼容旧调用） |
| `shared/capabilities/voice/stt/__init__.py:77` | 兼容旧调用：仅当显式传入 api_key/api_base 时走 openai_compat |
| `shared/capabilities/voice/config/credentials.py:24` | 明文兼容旧数据：非加密前缀直接返回 |
| `shared/services/pipeline_config.py:85` | 兼容早期已创建但没有动态默认值的空记录 |

**影响：** 主线代码被大量分支路径污染，增加了测试覆盖难度和阅读成本。

**建议：**

- 制定明确的废弃（deprecation）周期。
- 对“兼容旧”代码加 `@deprecated` 注解，并在日志中输出迁移提示。
- 在下一个 minor 版本中删除无活跃调用方的兼容分支。

### 2.7 数据库模型归属

当前模型分布：

| 位置 | 模型 |
|------|------|
| `shared/models/__init__.py` | `StageConfig`、`LLMSettings`、`Resume`、`UserProfile` |
| `api_service/models/__init__.py` | re-export `Resume`、`UserProfile` |
| `agent_service/models/__init__.py` | `PrepSession` |
| `interview_service/models/__init__.py` | `InterviewSession`、`GrowthRecord`，并 re-export `LLMSettings`、`StageConfig` |

**问题：**

- `Resume` / `UserProfile` 归属 `shared` 是合理的，因为被 api/agent/interview 三服务共享。
- `LLMSettings` / `StageConfig` 本质上是“基础设施/处理器配置”，放在 `shared/models` 与业务模型混在一起，不如单独放在 `shared/core/config_models.py` 或 `shared/infrastructure/models.py`。
- `api_service/models/__init__.py` 的 re-export 价值有限，反而制造了“Resume 属于 api_service”的错觉。

### 2.8 实时面试核心代码分析

#### 2.8.1 文件规模

| 文件 | 行数 | 职责 |
|------|------|------|
| `interview_service/realtime/connection_lifecycle.py` | 460 | WS 握手、鉴权、心跳、主循环、RAG/语音凭证初始化 |
| `interview_service/realtime/ws_handler.py` | >460 | facade + mixin 组合 + 兼容导出 |
| `interview_service/realtime/turn_coordinator.py` | 314 | 候选人回合、话轮锁、打断处理 |
| `interview_service/realtime/voice_pipeline.py` | 305 | STT 选择、TTS 队列、音频缓冲 |
| `interview_service/realtime/turn_streaming.py` | 未精确统计 | 流式事件消费与 TTS 分发 |
| `interview_service/services/interview/runner.py` | 316 | 面试回合执行器：开场、常规回合、收尾 |
| `interview_service/services/interview/agent.py` | 375 | 会话状态机、消息历史、阶段推进 |

#### 2.8.2 Mixin 耦合方式

`InterviewWSHandler` 通过多重继承组合：

```python
class InterviewWSHandler(
    ConnectionLifecycleMixin,
    TurnCoordinatorMixin,
    VoicePipelineMixin,
    HintServiceMixin,
    ReportSchedulerMixin,
):
```

各 mixin 通过 `TYPE_CHECKING` 声明宿主字段契约：

```python
if TYPE_CHECKING:
    ws: Any
    session_id: int
    _client_access_token: str
    ...
```

**问题：**

- 字段在 `InterviewWSHandler.__init__` 中注入，mixin 在运行时看不到字段声明，仅靠约定。
- 新增字段时需要在 `ws_handler.py` 和多个 mixin 的 `TYPE_CHECKING` 块中同步。
- 单元测试需要构造完整 handler 实例，难以单独测试某个 mixin。

**建议：** 引入显式的 `ConnectionContext` dataclass，把 mixin 改为接收 context 的函数/类，降低隐式耦合。

#### 2.8.3 `InterviewRunner` 与 `InterviewAgent` 边界

- `InterviewRunner`：负责“回合”级流程（开场、常规、收尾），调用 LLM、工具、RAG。
- `InterviewAgent`：负责“会话”级状态（消息历史、阶段索引、持久化）。

**问题：**

- `runner.py` 仍直接操作 `self.agent.messages` 等内部字段（如 `stream_turn` 中）。
- `agent.py` 中 `save_state` 直接调用 `db.commit()`，事务控制权分散。

**建议：** 把 `InterviewAgent` 的持久化改为返回待保存状态，由 `InterviewRunner` 或更高层决定何时 `commit`。

### 2.9 测试分布

| 类别 | 数量 |
|------|------|
| 生产 Python 文件（不含 tests/alembic） | 138 |
| 测试文件 | 45 |
| 测试函数/类 | 328 |

后端测试数量可观，但需要注意：

- 多个测试通过 `ws_handler` 访问私有成员（如 `_SentenceTTSQueue`、`_is_echo_of_assistant`），导致生产代码中保留 `# noqa: F401` 的测试专用 import。
- 某些测试文件（如 `services/tests/test_main.py`）测试的是聚合入口，对服务间集成依赖较强。

### 2.10 后端关键正面观察

- **三服务无循环业务依赖**，聚合入口职责单一。
- **`shared/app_factory.py`** 统一了独立入口的 CORS、health、trace、错误处理，避免重复。
- **安全配置集中**：`services/main.py` 中 CORS 通配检测、prod 必须显式 SECRET_KEY、请求 ID 校验等。
- **错误 envelope 统一**：前后端 `APIError` / `ApiErrorBody` 字段对齐。
- **文件上传安全**：魔数嗅探、扩展名校验、大小上限、路径越界校验均已在 `resume.py` / `security.py` 中实现。

---

## 3. 前端架构审查

### 3.1 顶层结构

```
apps/web/src/
├── app/                # Next.js App Router 页面
├── components/         # 通用组件 + 业务组件
├── features/           # 业务/技术能力封装
├── lib/                # 工具函数、API 客户端
├── config/             # 静态配置
├── types/              # TypeScript 类型
└── ...
```

### 3.2 文件规模

| 文件 | 行数 | 问题 |
|------|------|------|
| `app/interview/[id]/page.tsx` | 941 | 上帝页面 |
| `app/resume/page.tsx` | 846 | 表单+分析结果混杂 |
| `app/profile/page.tsx` | 722 | 表单字段过多 |
| `app/settings/page.tsx` | 664 | 配置项过多 |
| `app/prep/page.tsx` | 416 | 尚可，但可拆分 |
| `app/page.tsx` | 419 | 首页 Landing |
| `features/media/useAudioRecorder.ts` | 614 | 复杂 hook |
| `features/avatar/TalkingHeadAvatar.tsx` | 480 | 3D 形象逻辑 |
| `types/index.ts` | 506 | 类型大杂烩 |

### 3.3 页面组件过大

以 `app/interview/[id]/page.tsx` 为例：

- 84 个函数/箭头函数
- 65 个 React hook 调用（`useEffect`、`useState`、`useRef`、`useCallback`）
- 同时处理：WS 连接、音频录制、TTS 播放、视频面板、消息渲染、面试流程、静默追问、打断、报告跳转等。

**影响：**

- 单一文件承担过多职责，难以单元测试。
- 任何小改动都需要理解整页逻辑。
- React 依赖数组极易出错。

**建议：**

- 按业务域拆分为 `features/interview/`：
  - `hooks/useInterviewRoom.ts`：会话生命周期、消息、阶段、打断
  - `hooks/useInterviewAudio.ts`：封装 `useAudioRecorder` + `useTTSPlayer`
  - `components/ChatPanel.tsx`
  - `components/ControlBar.tsx`
  - `components/AvatarStage.tsx`
- 页面 `page.tsx` 只负责组装和路由参数读取。

### 3.4 `use client` 泛滥

统计：

- `app/` 下 12 个 `use client`
- `components/` 下 18 个 `use client`
- `features/` 下 2 个 `use client`

**影响：** 几乎所有页面和组件都是客户端组件，Next.js 的 RSC/SSR 优势未利用。首屏渲染、SEO、bundle 大小均未优化。

**建议：**

- 把纯展示组件（`CollapsibleSection`、`MarkdownContent`、`SearchResultCards`）改为 Server Component。
- 把数据获取逻辑抽到 Server Action 或 API Route Handler。
- 仅在需要浏览器 API（WebSocket、MediaRecorder、AudioContext、Three.js）的组件上保留 `use client`。

### 3.5 `features` 层未承担业务逻辑

当前 `features/`：

```
features/
├── avatar/
│   ├── InterviewerAvatar.tsx
│   └── TalkingHeadAvatar.tsx
└── media/
    ├── useAudioRecorder.ts
    ├── useInterviewWS.ts
    └── useTTSPlayer.ts
```

这些都是**技术能力**（avatar 渲染、音频/WS），不是**业务 feature**。没有 `features/interview/`、`features/resume/`、`features/prep/` 等业务聚合。

**建议：** 按业务域重组 `features/`：

```
features/
├── interview/
│   ├── components/
│   ├── hooks/
│   └── stores/
├── resume/
├── prep/
├── avatar/
└── media/
```

### 3.6 类型定义集中且重复

`types/index.ts` 506 行，包含：

- LLM / Stage 配置类型
- 用户档案 / 简历 / 候选人档案类型
- 面试会话 / 消息 / 报告 / 成长类型
- SSE / WebSocket 事件类型
- 错误 envelope 类型

**问题：**

- 与后端 Pydantic 模型大量重复。
- 单一文件过大，合并冲突风险高。

**建议：**

- 至少按域拆分为 `types/api.ts`、`types/interview.ts`、`types/agent.ts`、`types/common.ts`。
- 长期引入 OpenAPI / Pydantic-to-TypeScript codegen，从后端 schema 自动生成前端类型。

### 3.7 API 客户端

#### 3.7.1 结构

- `lib/api/base.ts`：fetch 封装、SSE 解析、错误解析、超时控制。
- `lib/api/apiService.ts`：api_service 客户端。
- `lib/api/agentService.ts`：agent_service 客户端。
- `lib/api/interviewService.ts`：interview_service 客户端。

#### 3.7.2 问题

- `base.ts` 的 `request()` 函数承担超时、signal 合并、错误解析、JSON 解析多项职责，238 行略显臃肿。
- `apiService.uploadResume()` 混用了直接 `fetch()`，没有走统一 `request()`，导致上传错误处理与 base 不一致。
- `interviewService.ts` 注释承认跨域调用 `api_service` 的简历接口，前端已破坏服务边界。

**建议：**

- 把 `request()` 拆分为 `buildRequestInit`、`applyTimeout`、`parseResponse` 等函数。
- `uploadResume` 统一走 `request()`，支持 `FormData`。
- 面试域需要的简历列表应由后端 `interview_service` 提供聚合接口，或明确由 BFF/聚合层转发，而不是前端直接调两个服务。

### 3.8 测试覆盖

- 前端测试总计 **247 行**，仅覆盖：
  - `lib/api.test.ts`
  - `lib/cnText.test.ts`
  - `lib/thinkStream.test.ts`
- 复杂 hook（`useInterviewWS`、`useAudioRecorder`、`useTTSPlayer`）无测试。
- 页面组件无测试。

**建议：**

- 为 `useInterviewWS` 编写基于 `ws` mock 的单元测试。
- 为 `useAudioRecorder` 和 `useTTSPlayer` 编写基于 Web Audio API / MediaRecorder mock 的测试。
- 页面组件测试使用 `@testing-library/react` + MSW。

### 3.9 前端关键正面观察

- `@/` alias 使用一致，没有混乱的相对路径。
- 错误处理与后端 envelope 对齐，`ApiError` 类携带 code/hint/traceId/retryable。
- `useInterviewWS` 对 React Strict Mode 的世代号处理较细致，避免旧连接误重连。
- `useTTSPlayer` 对音频解锁、失败缓冲、打断停止的处理较完整。

---

## 4. 跨层问题

### 4.1 前后端类型契约不同步

| 后端 | 前端 |
|------|------|
| `shared/schemas/__init__.py` 中的 `LLMSettingsResponse` | `types/index.ts` 中的 `LLMSettings` |
| `interview_service/schemas/__init__.py` 中的 `InterviewReport` | `types/index.ts` 中的 `InterviewReport` |
| `api_service/schemas/__init__.py` 中的 `ResumeAnalysis` | `types/index.ts` 中的 `ResumeAnalysis` |

这些类型目前靠手工维护，字段注释中偶有“与后端对齐”的说明，但无强制校验。

**建议：** 引入 `openapi-typescript` 或自研 Pydantic-to-TS 脚本，在 CI 中校验类型同步。

### 4.2 前端破坏服务边界

`interviewService.ts` 注释：

> 注意（微服务化预留）：本域在单进程聚合下跨域调用 api_service 的简历接口（`listResumes` 属 api 域）。将来服务拆分时，此依赖需改为显式聚合 base URL。

**问题：** 前端直接调用两个不同域的接口，增加了未来拆分的复杂度。

**建议：** 由后端 `interview_service` 提供 `GET /interview/resumes` 代理/聚合接口，前端只与 `interview_service` 交互。

---

## 5. 具体改进建议（按优先级）

### 5.1 高优先级

1. **拆分 `interview_service` 实时层**
   - 把 `connection_lifecycle.py` 拆为 `auth.py`、`heartbeat.py`、`dispatch.py`。
   - 把 mixin 的隐式字段契约改为显式 `ConnectionContext`。
   - 目标：将 `InterviewWSHandler` 缩减到 200 行以内。

2. **前端按业务 feature 重组**
   - 新建 `features/interview/`、`features/resume/`、`features/prep/`。
   - 把 `app/interview/[id]/page.tsx` 中的业务逻辑抽到 `features/interview/hooks/` 和 `features/interview/components/`。
   - 目标：`page.tsx` 只负责组装。

3. **精简 `shared` 包**
   - 拆分 `shared/capabilities/ai/llm/client.py`。
   - 拆分 `shared/core/security.py`。
   - 把 `LLMSettings` / `StageConfig` 从 `shared/models` 移到 `shared/infrastructure/models.py` 或 `shared/core/config_models.py`。

### 5.2 中优先级

4. **清理空包与兼容代码**
   - 删除或填充 30 个空 `__init__.py`。
   - 制定废弃周期，逐步删除 20+ 处“兼容旧”分支。

5. **引入类型契约生成**
   - 至少把 `types/index.ts` 按域拆分为多个文件。
   - 长期引入 Pydantic-to-TypeScript codegen，并在 CI 中校验。

6. **提升前端测试覆盖**
   - 为 `useInterviewWS`、`useAudioRecorder`、`useTTSPlayer` 添加单元测试。
   - 为关键页面组件添加集成测试。

### 5.3 低优先级

7. **优化 Server Component 使用**
   - 把纯展示组件改为 RSC，减少 `use client` 数量。

8. **统一文件上传路径**
   - `apiService.uploadResume` 改用统一的 `request()` 封装。

9. **标准化命名**
   - `InterviewAgent`（状态机）考虑改名为 `InterviewSessionState` 或 `InterviewContext`。
   - `InterviewOrchestrator` 改名为 `NudgeGenerator` 等更贴切的名称。

---

## 6. 风险与注意事项

- **重构实时层是高风险操作**：WebSocket 话轮锁、打断、TTS 队列、播放完成同步等逻辑存在复杂的时序依赖，重构时必须保留现有行为，建议先写高覆盖的契约测试。
- **兼容代码不可一次性删除**：`LLMSettings` 与 `StageConfig` 的兼容路径目前仍在生产中使用，删除前需要数据迁移和前端同步。
- **前端大页面拆分需保持状态同步**：`app/interview/[id]/page.tsx` 中大量 `useRef` 和回调引用拆分后需确保引用稳定性，避免引入竞态。

---

## 7. 结论

RealMock 项目已经从早期的“大 backend”演进为“模块化单体”，三服务边界基本清晰，基础设施（配置、安全、日志、错误处理）已有统一抽象。但项目目前处于**“能跑但难改”**的状态：

- 后端 `interview_service` 与 `shared` 包膨胀，命名空间与兼容代码削弱了模块化带来的好处。
- 前端页面组件过大，`features` 层未真正发挥作用，测试覆盖不足。

建议优先处理：

1. `interview_service` 实时层拆分；
2. 前端按业务 feature 重组；
3. `shared` 包职责精简。

这三项完成后，项目的可维护性将有显著提升，也为未来拆分为独立微服务或引入 BFF 打下良好基础。

---

*报告生成方式：基于代码静态分析、AST 统计、文件读取与人工审查，未执行运行时测试。*
