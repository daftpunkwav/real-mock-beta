# 共享表只读契约

> 模块化单体下 ``UserProfile`` / ``Resume`` 存于 **api.db**（``shared.models`` / ``ApiBase``）。  
> **写**权：`api_service`（上传、解析、档案 CRUD）。  
> **读**权：`agent_service` / `interview_service` 须经 ``shared.services.candidate_read``（内部走 api Session）。

会话域表（``InterviewSession``、``PrepSession``、``GrowthRecord`` 等）在 **sessions.db**。

## 门面函数

| 函数 | 用途 |
| --- | --- |
| `get_user_profile(db, profile_id)` | 面试提示词需全字段 ORM（`db` 须为 api Session） |
| `format_profile_summary(db, profile_id?)` | Prep / 文本摘要 |
| `format_resume_summary(db, resume_id)` | 简历文本摘要 |
| `get_candidate_profile(db, resume_id)` | 结构化 ``CandidateProfile`` |
| `get_resume_detail(db, resume_id)` | 简历详情（含解析字段） |

## 双库检查清单

1. interview/agent 路由：会话写 **sessions**；档案/配置读 **api**（``get_api_db`` / ``api_db_session``）。
2. 禁止 ``from shared.models import Resume|UserProfile`` 出现在 interview/agent（见 ``test_db_boundary_imports``）。
3. 备份/迁移时同时处理 ``api.db`` 与 ``sessions.db``（见 ``docs/dual-database.md``）。

## 演进

拆库前检查清单（历史）：门面改为 internal HTTP / 消息契约。当前已物理拆为双 SQLite 文件，仍保留读门面以便日后再拆服务。
