# 双 SQLite 库布局

> **api.db**：档案 / 简历 / 处理器配置（`api_service` 写权）  
> **sessions.db**：面试 / Prep / 租约 / 限流桶

## 环境变量

```env
API_DATABASE_URL=sqlite:///.../shared/data/api.db
SESSIONS_DATABASE_URL=sqlite:///.../shared/data/sessions.db
# legacy：DATABASE_URL 映射到 SESSIONS_DATABASE_URL
```

## 边界规则

- `interview_service` / `agent_service` **禁止** `from shared.models import Resume|UserProfile`
- 读档案/简历须经 `shared.services.candidate_read`
- LLM / pipeline 配置读 **api** Session；会话读写 **sessions** Session

## 从 app.db 迁移

若仅有 legacy `shared/data/app.db` 且尚无 `api.db`/`sessions.db`，启动时自动按表拆分（见 `shared/services/db_split.py`）。

## 备份

个人项目建议同时备份两个文件：

```bash
cp shared/data/api.db shared/data/backups/api-$(date +%F).db
cp shared/data/sessions.db shared/data/backups/sessions-$(date +%F).db
```
