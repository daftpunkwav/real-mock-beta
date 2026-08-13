"""应用配置模块（共享平台层）。"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from shared.core.constants import DEFAULT_RAG_BACKEND, RAGBackendKind

# 共享层根目录（services/shared/）：数据、上传、.env 集中于此
SHARED_ROOT = Path(__file__).resolve().parent


class Settings(BaseSettings):
    """全局配置，支持环境变量与 .env 文件。

    环境变量均使用无前缀命名（CORS_ORIGINS / ENV / SECRET_KEY / TEST_MODE / …）。
    """

    model_config = SettingsConfigDict(
        env_file=SHARED_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    # LLM BYOK（不再提供默认模型，避免用户未配置时误用公共默认）
    llm_api_base: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    llm_max_tokens: int = 4096
    llm_context_window: int = 128000

    # LLM 嵌入（可选）：None 时回退到上方 LLM BYOK 配置
    llm_embeddings_base: str | None = None
    llm_embeddings_key: str | None = None
    llm_embeddings_model: str | None = None

    # RAG 后端选择
    rag_backend: RAGBackendKind = DEFAULT_RAG_BACKEND
    # StepFun 后端专用：若已存在 StepFun vector_store，直接复用 ID；留空则启动时自动创建。
    stepfun_vector_store_id: str | None = None

    # 服务
    database_url: str = f"sqlite:///{SHARED_ROOT / 'data' / 'app.db'}"
    upload_dir: str = str(SHARED_ROOT / "uploads")
    cors_origins: str = Field(
        # 端口规划：前端 8080 / 后端 8081；其他服务依次顺延 8082、8083…
        default="http://localhost:8080,http://127.0.0.1:8080",
    )
    # 默认仅本机；局域网调试请显式设 HOST=0.0.0.0
    host: str = "127.0.0.1"
    port: int = Field(default=8081, ge=1, le=65535)
    env: str = Field(
        default="dev",
        description="dev / prod，决定 allow_local_llm 与 CORS 严格度",
    )

    # 语音：默认走 OpenAI 兼容云端 transcriptions（复用 LLM BYOK）；
    # 填 tiny/base/small/... 时偏向本地 faster-whisper。
    whisper_model: str = "whisper-1"
    tts_voice: str = "zh-CN-XiaoxiaoNeural"
    silence_nudge_seconds: int = Field(default=25, ge=1, le=600)

    # GitHub（面试核验工具；可选 PAT，提高 API 配额）
    github_token: str = ""
    # 面试 Agent 是否启用 function calling 工具循环
    interview_tools_enabled: bool = True
    interview_max_tool_rounds: int = Field(default=3, ge=0, le=6)

    # LLM 调用：是否允许本机/私网 base_url。生产必须为 False。
    allow_local_llm: bool = Field(default=False)

    # 限流：可信任的反向代理 CIDR 列表（逗号分隔）；空表示仅 request.client.host。
    trusted_proxy_cidrs: str = Field(default="")

    # Cookie Secure：None=自动（https 或可信代理 X-Forwarded-Proto=https）
    cookie_secure: bool | None = Field(default=None)

    @field_validator("cors_origins")
    @classmethod
    def _strip_cors(cls, v: str) -> str:
        """清理每个 origin 两侧的空白，便于后续拆分。"""
        return ",".join(o.strip() for o in v.split(",") if o.strip())

    @property
    def cors_origin_list(self) -> list[str]:
        return [o for o in self.cors_origins.split(",") if o]

    @property
    def is_prod(self) -> bool:
        return self.env.strip().lower() == "prod"

    @property
    def trusted_proxy_cidr_list(self) -> list[str]:
        return [c.strip() for c in self.trusted_proxy_cidrs.split(",") if c.strip()]

    @property
    def effective_embeddings_base(self) -> str:
        """解析后的 embeddings base：独立配置优先，否则回退到 chat base。"""
        return (self.llm_embeddings_base or self.llm_api_base).rstrip("/")

    @property
    def effective_embeddings_key(self) -> str:
        return self.llm_embeddings_key or self.llm_api_key

    @property
    def effective_embeddings_model(self) -> str:
        return self.llm_embeddings_model or self.llm_model

    @model_validator(mode="after")
    def _validate_cross_fields(self) -> "Settings":
        """跨字段配置校验。"""
        if self.is_prod and self.allow_local_llm:
            raise ValueError("生产环境 (env=prod) 不允许 allow_local_llm=True")
        if self.rag_backend == RAGBackendKind.STEPFUN and not self.stepfun_vector_store_id:
            # 不阻断启动（启动时自动创建），但打 warning
            pass
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
