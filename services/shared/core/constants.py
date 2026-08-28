"""全局协议常量。

集中放置前后端契约中用到的字符串字面量，便于：

- 前端 ``src/config/*.ts`` 与后端此处一一对照；
- 重命名 / 协议演进时编辑器可以定位所有引用；
- 避免 ``"foo"`` 散落在数十个文件中。

面试专属枚举（阶段 / 工作流 / 人格风格 / 追问分类 / WebSocket 事件）已下沉到
``interview_service.constants``，本模块只保留三服务真正共用的平台常量。

改动任何一个常量前，请同时改两处并提交一个原子 commit。
"""

from __future__ import annotations

from enum import StrEnum


# ── LLM 协议 ────────────────────────────────────────


class LLMProtocol(StrEnum):
    OPENAI_CHAT = "openai_chat"
    ANTHROPIC_MESSAGES = "anthropic_messages"
    OPENAI_RESPONSES = "openai_responses"


DEFAULT_LLM_PROTOCOL = LLMProtocol.OPENAI_CHAT


# 三处理器阶段标识
class PipelineStage(StrEnum):
    RECOGNIZE = "recognize"
    REASON = "reason"
    SPEAK = "speak"


# ── RAG 后端 ────────────────────────────────────────


class RAGBackendKind(StrEnum):
    """企业知识库 RAG 的实现后端。

    - ``local``:本地 Chroma + 调用 LLM 提供商的 ``/embeddings`` 端点。
      适用于 OpenAI / DeepSeek / SiliconFlow / Moonshot / GLM 等所有暴露
      OpenAI 兼容 embeddings 接口的 provider。
    - ``stepfun``:StepFun 托管的 ``/vector_stores`` 检索，检索通过
      ``tools[].type=retrieval`` 在 chat 调用时由 StepFun 服务端完成。
    - ``none``:完全关闭企业知识库检索。
    """

    LOCAL = "local"
    STEPFUN = "stepfun"
    NONE = "none"


DEFAULT_RAG_BACKEND = RAGBackendKind.LOCAL


# ── 会话状态 ────────────────────────────────────────


class SessionStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


# ── SSE 事件 ────────────────────────────────────────


class SSEMessageType(StrEnum):
    TOKEN = "token"
    DONE = "done"
    ERROR = "error"


# ── 速率限制 ────────────────────────────────────────

DEFAULT_RATE_LIMIT_PER_MINUTE = 60
DEFAULT_LLM_RATE_LIMIT_PER_MINUTE = 10
# 面试/辅导会话创建：防局域网批量建会话烧配额
DEFAULT_SESSION_CREATE_RATE_LIMIT_PER_MINUTE = 20

# HTTP / WS 用户文本上限（字符）
MAX_USER_TEXT_CHARS = 16_000
MAX_CONFIG_STR_CHARS = 200


# ── HTTP 头 / 安全 ────────────────────────────────────────

API_KEY_ENCRYPTION_VERSION = "enc:v2"
TRACE_ID_HEADER = "X-Trace-Id"


# ── 简历分析 ────────────────────────────────────────

RESUME_MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB
RESUME_ALLOWED_EXTENSIONS: frozenset[str] = frozenset({"pdf", "docx", "doc", "md", "txt"})


# ── WebSocket / 面试运行时 ────────────────────────────────────────

HEARTBEAT_TIMEOUT_SEC = 30.0
HEARTBEAT_MAX_MISSES = 3
AUDIO_BUFFER_MAX_BYTES = 5 * 1024 * 1024  # 5 MB
TTS_QUEUE_MAX_SIZE = 50
