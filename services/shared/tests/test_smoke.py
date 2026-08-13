"""shared 平台层冒烟：核心模块可独立导入且契约正确。"""

from __future__ import annotations


def test_shared_core_importable() -> None:
    import shared.config
    import shared.core.constants
    import shared.core.errors
    import shared.core.security
    import shared.core.secrets
    import shared.core.session_auth
    import shared.core.logging
    import shared.core.migrate
    import shared.core.ratelimit
    import shared.database

    assert shared.core.secrets._MASTER_SALT == b"app-master-v2"
    assert shared.database.Base is not None


def test_shared_capabilities_importable() -> None:

    from shared.capabilities.knowledge.company.knowledge import get_all_companies

    assert len(get_all_companies()) >= 7


def test_shared_models_and_schemas() -> None:
    from shared.models import LLMSettings, Resume, StageConfig, UserProfile

    assert LLMSettings.__tablename__ == "llm_settings"
    assert StageConfig.__tablename__ == "stage_configs"
    assert Resume.__tablename__ == "resumes"
    assert UserProfile.__tablename__ == "user_profiles"
