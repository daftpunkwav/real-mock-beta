# 架构审查修复计划 — 2026-09-01

> 基于 `architecture-review-20260901-deepseek-v4-flash.md` 与 `architecture-review-20260901-Composer.md` 的**批判性复核**与可执行修复清单。  
> 目的：任务中断时可据此恢复；每完成一项对应独立 commit。

---

## 1. 对两份报告的批判性结论

### 1.1 两份报告一致且可信的部分

| 结论 | 复核 |
| --- | --- |
| 三服务 import 层零互引、包级无环 | ✅ 与源码一致 |
| 生产代码无 >500 行上帝文件（2026-08 重构有效） | ✅ |
| `ResumePickerItem` 三处重复定义 | ✅ agent / interview / 前端 types |
| `_timed` 在 models.py 与 settings.py 重复 | ✅ |
| `list_resume_picker` 在 prep_lists 与 sessions 重复 | ✅ |
| 前端 `components/effects/` 无引用 | ✅ grep 零 import |
| 多条 API client 方法无调用方 | ✅ 已逐方法核对 |
| `build_context_prefix` / `set_voice` / `reportNavTimerRef` 死代码 | ✅ |
| `llm_client` ↔ `llm_client_ext` 运行期双向 import | ✅ |
| `model_profiles` 缺 DB 级 UNIQUE(provider_id, model) | ✅ 仅应用层先查后插 |
| realtime / report 大量 `except Exception: pass` 缺日志 | ✅ |

### 1.2 Composer 标为 P0、但本次**不代码修复**的项（已知架构约束）

| 报告项 | 批判性判断 |
| --- | --- |
| 默认单一 `database_url` SQLite | **模块化单体**的 intentional design（`pyproject.toml` 自述）。拆库是微服务化项目，非缺陷修复。 |
| `shared.models` 跨域 ORM（Resume/UserProfile） | 同上；三服务共库共表与 import 单向依赖并存是合理单体形态。应**文档化变更 checklist**，而非本次拆表。 |
| WS `session_registry` 进程内租约 | **真实风险**，但修复依赖部署决策（单 worker vs Redis/DB 分布式租约）。本次：补日志 + 在代码/文档标明单进程假设；分布式租约列为后续迭代。 |

### 1.3 Deepseek 报告需打折或延后的项

| 报告项 | 判断 |
| --- | --- |
| interview 8-hook / 25-ref「依赖注入爆炸」 | 真实技术债，但重构面大、行为风险高；**不在本批次**。 |
| `useAudioRecorder` 341 行拆分 | 同上，单独迭代。 |
| OpenAPI → TS 契约单轨 | 高收益但需工具链决策；本批次仅 consolidation 类低风险项。 |
| shared 平台层 interview 业务字段回迁 | 微服务化前置项，非当前阻塞。 |
| 116 处测试访问私有符号 | 重构锁定面，需专项而非顺手改。 |

### 1.4 报告间分歧

- **P0 计数**：Composer 3 项 vs Deepseek 0 项 — 差异在「共享库是否算 P0」。本计划采纳：**共库共表记为已知约束**，不标 P0 阻塞。
- **死代码 `history/index.ts`**：barrel 文件本身可被页面直引路径绕过，但组件仍在用；**不删 history feature**，仅忽略 barrel 未引用告警。

---

## 2. 本批次修复清单（按 commit 顺序）

| # | Commit 主题 | 状态 |
| --- | --- | --- |
| 1 | `docs: 架构审查修复计划` | ✅ 7a300bf |
| 2 | `chore(web): 删除未引用 effects 组件包` | ✅ fcd1dd9 |
| 3 | `chore(web): 移除 API client 死方法` | ✅ a5a90bf |
| 4 | `refactor(interview): 删除 build_context_prefix 与 set_voice` | ✅ 9549307 |
| 5 | `refactor(web): 移除未使用的 reportNavTimerRef` | ✅ 5f3f5e2 |
| 6 | `refactor(shared): 统一 ResumePickerItem 契约` | ✅ 9bc9100 |
| 7 | `refactor(api): 收敛 _timed 重复实现` | ✅ da646dd |
| 8 | `refactor(shared): 收敛 list_resume_picker` | ✅ d9fbc3a |
| 9 | `fix(api): model_profiles 增加 UNIQUE 约束` | ✅ 0537920 |
| 10 | `refactor(llm): llm_client 运行期环改延迟导入` | ✅ 44b5c30 |
| 11 | `fix(report): 吞错路径补 debug 日志` | ✅ 0b5869d |
| 12 | `fix(realtime): session_registry 吞错补日志` | ✅ 731e5fe |
| 13 | `refactor(web): SearchResultCards 复用 safeAbsoluteHttpUrl` | ✅ a118e11 |
| 14 | `chore: gitignore .tmp_head_review` | ✅ 663a76d |
| 15 | `fix(config): StepFun RAG 缺 vector_store 时打 warning` | ✅ 4009f79 |

---

## 3. 验证策略

每批 commit 后：

```bash
cd services && pytest tests/test_smoke.py tests/test_error_handlers.py tests/test_api_v1_paths.py -q
cd apps/web && npx vitest run
```

全批次结束后跑 broader pytest（若时间允许）。

---

## 4. 明确不在本批次范围

- 分布式 WS 租约 / 多 worker 限流 / Whisper 跨进程缓存
- `useInterviewRoom*` 状态域重构、`useAudioRecorder` 拆分
- OpenAPI 生成、pipeline 三轨配置收敛、`report→growth` 事件化
- `chroma_*` 工作区清理（已在 `.gitignore`，现存目录需本地手动删）
- `shared/config` interview 字段回迁、`main.py` 双前缀 router 工厂

---

*最后更新：2026-09-01 · 与修复 commit 同步更新「状态」列*
