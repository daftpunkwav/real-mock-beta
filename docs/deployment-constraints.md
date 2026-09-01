# 部署与运行时约束

> RealMock 当前为 **模块化单体**：代码分 `api_service` / `agent_service` / `interview_service` 三包，**默认单进程聚合**（`services/main.py`）。以下约束来自架构审查复核，非缺陷，但影响水平扩展与拆库决策。

---

## 1. 部署形态

| 形态 | 入口 | 适用 |
| --- | --- | --- |
| 聚合（默认） | `uvicorn services.main:app` | 本地开发、单机部署 |
| 独立服务 | 各服务 `main.py` + `shared/app_factory` | 调试单域、未来多进程雏形 |

环境变量集中在 `services/shared/.env`（`DATABASE_URL`、`SECRET_KEY`、`CORS_ORIGINS` 等）。

---

## 2. 已知运行时约束

### 2.1 共享数据库

- 默认 `sqlite:///{shared/data/app.db}`；三服务 ORM **共库共表**。
- `UserProfile` / `Resume` 在 `shared.models`，api 写、agent/interview 读——**无服务间 HTTP**，靠共享表隐式耦合。
- **拆库 / 微服务化前**：任何 `resumes` / `user_profiles` 迁移须跑三服务相关测试 + 前端契约。

### 2.2 WebSocket 单连接租约（单进程）

- `interview_service/realtime/session_registry.py` 使用进程内 `_active_handlers`。
- **多 Uvicorn worker 或多实例 + LB** 时，同 session 双开互斥 **失效**。
- 缓解（未默认实现）：Redis/DB 分布式租约；或文档化 **单 worker** 约束。

### 2.3 进程内全局态

| 组件 | 影响 |
| --- | --- |
| `session_registry` | 多实例 WS 租约 |
| `core/ratelimit` 桶 | 多 worker 限额放大 |
| `stt/whisper` 模型缓存 | 多 worker 各载一份 |
| `get_settings()` lru_cache | 测试须 import 前设 env |

---

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

*2026-09-01*
