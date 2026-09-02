# 部署与运行时约束

> RealMock 当前为 **模块化单体**：代码分 `api_service` / `agent_service` / `interview_service` 三包，**默认单进程聚合**（`services/main.py`）。以下约束来自架构审查复核，非缺陷，但影响水平扩展与拆库决策。

---

## 1. 部署形态

| 形态 | 入口 | 适用 |
| --- | --- | --- |
| 聚合（默认） | `uvicorn services.main:app` | 本地开发、单机部署 |
| 独立服务 | 各服务 `main.py` + `shared/app_factory` | 调试单域、未来多进程雏形 |

环境变量集中在 `services/shared/.env`（`API_DATABASE_URL`、`SESSIONS_DATABASE_URL`、`SECRET_KEY`、`CORS_ORIGINS` 等；legacy `DATABASE_URL` 映射 sessions 库）。

---

## 2. 已知运行时约束

### 2.1 双 SQLite 库

- 默认 **api.db**（档案/简历/处理器配置）+ **sessions.db**（面试/Prep/租约/限流桶）；见 `docs/dual-database.md`。
- `UserProfile` / `Resume` 在 api 库；agent/interview **读**须经 `candidate_read`（禁止直接 import ORM）。
- 仅有 legacy `app.db` 时启动会自动拆库；备份须同时复制两个文件。

### 2.2 WebSocket 单连接租约（单进程）

- ``interview_service/realtime/core/session_registry.py`` 使用 ``WsConnectionRegistry`` 封装进程内状态；可选 ``ws_lease_backend=database``（``ws_session_leases`` 表）。
- **多 Uvicorn worker 或多实例 + LB** 时，应启用 ``WS_LEASE_BACKEND=database``；心跳循环会校验 DB 租约 token，失效连接主动断开。
- 同进程内仍会顶替旧连接。本地单体默认 ``memory`` 即可。

### 2.3 限流

- 默认 `RATELIMIT_BACKEND=memory`（进程内）；多 worker 时设 `database` 使用 `rate_limit_buckets` 表。

### 2.4 进程内全局态

| 组件 | 影响 |
| --- | --- |
| `WsConnectionRegistry` | 多实例 WS 租约（可注入/重置，测试友好） |
| `core/ratelimit` 桶 | 多 worker 限额放大 |
| `stt/whisper` 模型缓存 | 多 worker 各载一份 |
| `get_settings()` lru_cache | 测试须 import 前设 env；避免模块级绑定 |
| `report_persist_cas._REPORT_LOCKS` | 单会话报告生成互斥；生成结束即释放，非长跑泄漏源 |

### 2.5 多 worker / 多实例 Checklist

部署 `uvicorn --workers N` 或水平扩容前确认：

| 变量 | 单进程默认 | 多实例推荐 |
| --- | --- | --- |
| `WS_LEASE_BACKEND` | `memory` | `database` |
| `RATELIMIT_BACKEND` | `memory` | `database` |
| SQLite 路径 | 本地文件 | 共享存储或迁 PostgreSQL |
| Whisper 本地 STT | 每 worker 各载模型 | 改用云 STT 或接受内存 × N |

未切换 backend 时：**限流配额放大 N 倍**、**同 session 可能多路 WS**（租约仅进程内有效）。

## 3. 共享表变更 Checklist

修改 `shared.models` 或 `shared/core/config_models` 时：

1. Alembic / `shared/core/migrate.py` 列补全（SQLite 幂等）。
2. `pytest services/tests/test_smoke.py` + 域相关集成测试。
3. 若字段暴露给前端：更新 `apps/web/src/types/` 与 API client。
4. 若影响 Prep / Interview 读简历：跑 `test_prep_*` / `test_runner` / WS 相关测试。

---

## 4. 生产门禁

- `env=prod` 须显式 `SECRET_KEY`（≥16 字节）。
- 生产禁止 `CORS_ORIGINS=*` 与 `allow_local_llm=True`。
- WS 生产环境拒绝 query token（仅 Cookie / 子协议）。

---

## 5. 何时升级部署形态

| 目标 | 前置工作 |
| --- | --- |
| 多实例 HTTP | 分布式 WS 租约、跨进程限流、共享 DB 或拆库 |
| 微服务拆库 | Resume/Profile 写权归 api；其余服务 internal API 读 DTO |
| API v2 | 使用 `router_mount` 增加前缀，避免复制整棵 router 树 |

---

*2026-09-02*
