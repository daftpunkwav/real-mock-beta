# 全目录文件组织审计 — 2026-09-01

> 原则：**按业务边界加一层子目录**，避免平铺 ≥6 个同域文件；单文件 &lt;150 行且子域清晰则保持扁平。  
> 与 [`package-layout.md`](package-layout.md) 一致：子域内用**平铺模块**，不在子域内再套三级目录。

---

## 1. 需要子目录（本批次处理）

| 目录 | 文件数 | 建议子包 | 状态 |
| --- | --- | --- | --- |
| `api_service/routes/` | 7 | `resume/`、`settings/`、`profile.py` 顶层 | ✅ |
| `interview_service/routes/` | 6 | `interview/`、`reports/`、`ws/`、`options.py` | ✅ |
| `interview_service/realtime/` | 26 | `core/`、`connection/`、`turn/`、`voice/`、`control/` | ✅ |
| `shared/schemas/` | 4 模块 | `pipeline.py`、`errors.py`、`candidate.py` | ✅ |
| `apps/web/src/types/` | 11 | `generated/`（OpenAPI）、`domains/`（手写 WS 等） | ✅ |
| `apps/web/src/features/interview/hooks/` | 12 | `room/` 子目录 | ✅ |
| `apps/web/src/features/media/` | 9 | `recorder/` 子目录 | ✅ |

---

## 2. 已合理，暂不拆

| 目录 | 说明 |
| --- | --- |
| `agent_service/agents/prep/` | 7 文件，单业务 Prep，已按职责分文件 |
| `api_service/services/resume/` | 6 文件，分析管线已分子模块 |
| `interview_service/services/interview/` | 22 文件，单域引擎；再拆 `report/` 子包收益低 |
| `shared/capabilities/ai/llm/client/` | 18 文件，已是包内平铺 |
| `shared/core/` | 17 文件，平台核心，文件名即职责 |
| `apps/web/src/features/resume/components/` | 27 组件，UI 粒度文件，不宜再套目录 |

---

## 3. 子包命名约定

```
routes/{domain}/router.py   # 路由聚合（add_api_route）
routes/{domain}/*.py        # 无装饰器 handler

realtime/{layer}/           # core | connection | turn | voice | control

schemas/{domain}.py         # 或 schemas/{domain}/ 当单域类型 >250 行

types/domains/*.ts          # 手写域类型
types/generated/api.d.ts    # OpenAPI 生成（只读）
```

---

## 4. 架构任务批次（与目录重组并行）

| 批次 | 内容 |
| --- | --- |
| A | 目录审计 + api routes 子包 |
| B | interview routes + realtime 子包 |
| C | shared/schemas + web/types + OpenAPI 生成 |
| D | interview hooks + audio recorder 拆分 |
| E | pipeline 收敛 + report→growth 解耦 |
| F | DB 分布式 WS 租约 |

---

*每批次独立 commit，详见 `architecture-fix-plan-20260901.md` 更新节*
