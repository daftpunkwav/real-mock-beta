"""处理器配置域路由：三阶段 stages + 模型条目 models。"""

from api_service.routes.settings.models import router as models_router
from api_service.routes.settings.stages import router

__all__ = ["router", "models_router"]
