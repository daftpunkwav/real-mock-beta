# 模型能力体系与处理器选择 — 设计稿

> 状态:实施中。本文档是本轮改动的蓝图:先存储后 UI,兼容层保证运行时零回归。

## 目标

1. **能力声明制模型条目**:一条模型记录声明能力位(对话/思考、视觉输入、语音输入、语音输出、思考强度)与参数(上下文窗口、最大输出)。一个模型支持多能力时只录一遍,三个任务绑定可指向同一条目。
2. **任务绑定(task binding)**:`chat`(对话/思考)、`stt`(语音输入)、`tts`(语音输出)三个任务各自绑定一个模型条目;语音任务额外带降级策略(handler/mode)。任务绑定 = 该任务的默认处理器。
3. **场景覆盖**:面试准备输入框即时选「模型 + 思考强度」;模拟面试创建时为三个任务分别选模型 + 思考强度;简历评价固定用默认 chat 绑定 + 最大思考强度。
4. **命名中立**:模型条目与能力字段用中立命名(chat/vision/audio_input/audio_output/reasoning),不绑定用途;「处理器」只存在于任务绑定层。

## 数据模型(后端 SQLite,经 MIGRATIONS 建表)

### `llm_providers` — 供应商(API 凭证归属级)
| 列 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | |
| name | VARCHAR UNIQUE | 显示名(如 MiniMax) |
| api_base | VARCHAR | |
| protocol | VARCHAR | openai_chat / anthropic_messages / openai_responses |
| api_key_enc | VARCHAR | AES-GCM(`enc:` 前缀,复用 secrets.py);空=未设 |
| enabled | BOOLEAN | 默认 1 |
| created_at / updated_at | DATETIME | |

### `model_profiles` — 模型条目(能力声明)
| 列 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | |
| provider_id | INTEGER FK→llm_providers | |
| model | VARCHAR | 模型名(发往 API) |
| display_name | VARCHAR | 空=用 model |
| context_window | INTEGER | 0=未知(不参与压缩估算/圆环) |
| max_output | INTEGER | 默认 4096 |
| cap_chat / cap_vision / cap_audio_in / cap_audio_out / cap_reasoning | BOOLEAN | 能力位;cap_reasoning=支持思考强度参数 |
| extras | TEXT(JSON) | 任务级补充凭证(asr_app_id、tts_voice 等,密钥键沿用 pipeline_config 加密规则) |
| enabled | BOOLEAN | |
| created_at / updated_at | DATETIME | UNIQUE(provider_id, model) |

### `task_bindings` — 任务绑定(默认处理器)
| 列 | 类型 | 说明 |
|---|---|---|
| task | VARCHAR UNIQUE | chat / stt / tts |
| profile_id | INTEGER FK→model_profiles | |
| fallback_handler | VARCHAR | 仅 stt/tts 有意义(默认 local / edge) |
| fallback_mode | VARCHAR | none / text_only / …沿用现有取值 |
| updated_at | DATETIME | |

### 一次性迁移
启动时(migrate 后)若 `model_profiles` 空而 `stage_configs` 有数据:
reason→chat 绑定、recognize→stt、speak→tts,按行建 provider+profile(能力位从 supports_* 映射:reason→cap_chat,vision 保留;recognize→cap_audio_in;speak→cap_audio_out),fallback 原样带入。`stage_configs` 表保留不删(回滚安全),运行时不再读它(除迁移判断)。

## API(`/api/v1/settings`,全部 require_local_peer)

- `GET /providers` → 供应商+模型条目树(模型含能力位;api_key 只回 has_api_key)
- `POST /providers` / `PUT /providers/{id}` / `DELETE /providers/{id}`(有模型引用时 409)
- `POST /providers/{id}/models` / `PUT /models/{id}` / `DELETE /models/{id}`(被绑定引用时 409)
- `GET /bindings` / `PUT /bindings/{task}`(body: profile_id, fallback_handler?, fallback_mode?)
- `POST /test/model/{profile_id}` → 连通性测试(复用 stage_tests 逻辑)

## 兼容适配层(关键解耦点)

`shared/services/pipeline_config.py::get_stage_config_for_runtime(db, stage)` 改为:
- reason→task chat、recognize→task stt、speak→task tts;
- 由绑定+供应商+条目组装**与原 stage dict 同构**的 dict(stage 字段填映射名,便于日志);extras 合并(供应商级无,条目级 extras)。
- 下游 `LLMClient.from_db`、`build_stt_credentials`、`build_tts_credentials`、`get_context_window` **零改动**。

### 思考强度(reasoning effort)
- 取值:`low | medium | high | max`;仅当模型条目 `cap_reasoning` 时下发。
- 协议映射:openai_chat→`reasoning_effort`(max→high);openai_responses→`reasoning.effort`;anthropic_messages→`thinking:{type:enabled,budget_tokens}`(low 4096 / medium 8192 / high 16384 / max 32768)。
- `LLMClient` 增加 `reasoning_effort` 构造参数与 `from_profile()`;`from_db(db, *, reasoning_effort=None, profile_id=None)` 扩展:profile_id 覆盖默认绑定(场景选择入口)。

## 场景接线

- **Prep**:`POST .../message/stream` 请求体加可选 `model_profile_id`、`reasoning_effort`;路由构建 `LLMClient.from_db(db, profile_id=..., reasoning_effort=...)`。
- **模拟面试**:`POST /interview/sessions` body 加可选 `ai`(三任务 profile_id + effort),存 `interview_sessions.ai_overrides`(JSON,migrate 补列);`connection_lifecycle.py` / 路由构建客户端时按会话覆盖解析。
- **简历评价**:`analyze_resume` 用 `from_db(db, reasoning_effort="max")`。

## 前端

- **设置页**:左侧供应商列表(+新增),右侧供应商编辑(api_base/protocol/key/启用)+ 模型条目列表(能力勾选、context_window、max_output、extras)+ 底部「任务绑定」区(chat/stt/tts 各选 profile + 语音降级)。测试按钮逐条目。
- **prep 输入框**:左侧上下文使用环(token_usage / 所选模型 context_window)、模型下拉(仅 cap_chat 条目)、思考强度下拉(所选模型 cap_reasoning 才显示);发送时随消息携带。顶部「辅导中·N条 / Token」行删除;右栏「会话状态」「使用提示」卡片删除。
- **模拟面试创建页**:三个任务各一个下拉 + 思考强度;随创建会话提交。

## 验证

- 后端:迁移幂等测试、绑定 CRUD 测试、兼容 dict 同构测试、prep 携带 profile 的构造测试;全量 pytest。
- 前端:tsc + 手动(设置页录入 → prep 选择器出现 → 刷新执行过程仍在)。
