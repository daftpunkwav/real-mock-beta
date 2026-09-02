"""语音与提纲 mixin 聚合。"""

from interview_service.realtime.control.hint import ReferenceHintMixin
from interview_service.realtime.voice.pipeline import VoicePipelineMixin


class MediaStackMixin(VoicePipelineMixin, ReferenceHintMixin):
    """STT/TTS 管道与参考提纲。"""


__all__ = ["MediaStackMixin"]
