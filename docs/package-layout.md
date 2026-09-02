# 包布局与契约分层约定

> 目的：在模块化单体形态下保持目录可扩展，避免「一个 `__init__.py` 膨胀成上帝文件」或过早过度分层。

---

## 1. 顶层结构（不变）

```
services/
├── shared/           # 平台：DB、配置、安全、AI/语音、跨服务契约与 ORM
├── api_service/      # 档案 / 简历 / 处理器配置 REST
├── agent_service/    # Prep 教练
├── interview_service/# 模拟面试 + WS + 报告 + 成长
├── main.py           # 聚合入口（单进程模块化单体）
└── tests/            # 跨服务集成测试
```

三业务服务 **仅依赖 `shared`**，彼此零 import。新增第四业务服务时：新建平行包 + 在 `main.py` 注册 router。

---

## 2. 契约（schemas）放哪？

| 层级 | 路径 | 何时使用 |
| --- | --- | --- |
| 跨服务 | `shared/schemas/` | 两个及以上服务（或能力层）共用的 Pydantic 类型，如 `CandidateProfile`、`ResumePickerItem`、处理器配置 envelope |
| 服务内 | `{service}/schemas/` | 仅本服务路由/服务层使用的请求/响应体 |

### 2.1 何时在 `schemas/` 下再分文件？

**推荐（当前采用）**：按**业务子域**平铺模块，**不再套一层目录**：

```
shared/schemas/
├── __init__.py    # re-export，import shared.schemas 路径不变
├── pipeline.py    # 三阶段 / LLM 处理器配置
├── errors.py      # API 错误 envelope
└── candidate.py   # CandidateProfile / ResumePickerItem / CompanyInfo

api_service/schemas/
├── __init__.py    # 仅 re-export，对外 import 路径不变
├── profile.py     # 档案 CRUD
└── resume.py      # 简历 + 评价嵌套类型

interview_service/schemas/
├── __init__.py
├── session.py     # 会话 / 回合消息
├── report.py      # 报告评分
└── options.py     # 配置页选项
```

**判断标准**：

- 单文件 **&lt; ~200 行** 且 **1 个清晰子域** → 保持单文件即可（如 `agent_service/schemas` 目前仅 re-export）。
- 单文件 **≥ ~150 行** 或 **≥ 2 个业务子域** → 拆成平铺子模块 + `__init__.py` 聚合。
- **不要**在子域尚小时再建 `schemas/resume/analysis.py` 等三级目录；等 `resume.py` 自身超过 ~250 行再拆。

### 2.2 与前端类型的关系

前端 `apps/web/src/types/`：

```
types/
├── domains/           # 手写域类型（interview WS、prep、api 配置等）
├── generated/api.d.ts # OpenAPI 生成（npm run generate:api-types）
└── index.ts           # barrel；`@/types/interview` 保留兼容 re-export
```

`openapi.json` 由 `scripts/export_openapi.py` 导出；字段变更时运行 `npm run generate:api-types`。后端 `schemas` 拆分 **不改变** HTTP JSON 形状。

---

## 3. ORM（models）放哪？

物理库拆分见 ``docs/dual-database.md``：**api.db**（档案/简历/处理器配置）与 **sessions.db**（面试/Prep/租约/限流桶）。

| 实体 | 位置 | 库 | 说明 |
| --- | --- | --- | --- |
| `UserProfile`、`Resume` | `shared/models` | api.db | 跨服务读门面 ``candidate_read`` |
| `PrepSession` | `agent_service/models` | sessions.db | Prep 专有 |
| `InterviewSession` | `interview_service/models/session.py` | sessions.db | 面试会话 |
| `GrowthRecord` | `interview_service/models/growth.py` | sessions.db | 成长记录 |
| `WsSessionLease` | `interview_service/models/ws_lease.py` | sessions.db | WS 分布式租约 |
| `RateLimitBucket` | `shared/models/rate_limit_bucket.py` | sessions.db | 多 worker 限流 |
| 处理器配置表 | `shared/core/config_models` + `shared.models` re-export | api.db | 平台配置 |

**不要**在 `api_service/models/` 再 re-export `shared.models`——新代码直接 `from shared.models import Resume`。

`interview_service/models/` 与 `schemas/` 采用相同「平铺子模块 + `__init__.py`」策略。

---

## 4. 路由与服务层

- `routes/`：HTTP 装配、限流、Depends；复杂逻辑进 `services/`。
- `services/`：按业务能力分子目录（如 `api_service/services/resume/`）。
- 聚合入口用 `shared/router_mount.include_with_legacy_api_alias` 挂载 `/api/v1` 与 `/api` 别名，避免 `main.py` 复制 router 树。

---

## 5. 新增业务能力时的检查清单

1. 契约是否跨服务？→ `shared/schemas` 或复用已有共享类型。
2. ORM 是否跨服务读？→ 默认放 `shared.models` 并文档化；仅本服务写的表放 `{service}/models/`。
3. `schemas/__init__.py` 是否超过 ~200 行？→ 按子域拆文件，保持 `from {service}.schemas import X` 不变。
4. 是否在 `main.py` 增加 `include_router`？→ 加入 `SERVICE_ROUTERS` 元组即可。
5. 是否改共享表？→ 见 `docs/deployment-constraints.md` 迁移 checklist。

---

*2026-09-02 · 与双库拆分及架构审查修复同步*
