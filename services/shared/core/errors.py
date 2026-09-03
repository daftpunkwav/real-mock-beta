"""全站错误码注册表（权威实现，目录定义见 docs/spec/ERROR_CODES.md）。

用法：
    from shared.core.errors import raise_error

    raise_error("A1005")                       # 用目录默认文案
    raise_error("A0413", max=10)               # 格式化 message 中的 {max}
    raise_error("C0001", cause=e)              # 链式保留原始异常

设计要点：
- ``ApiBusinessError`` 继承 ``HTTPException``，所有既有 ``except HTTPException``
  与 ``main.py`` 的 envelope handler 自动兼容；
- handler 通过 ``exc.error_code`` 属性识别业务错误码，未迁移的旧
  ``raise HTTPException`` 走 ``http_{status}`` 兜底码，互不干扰。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import NoReturn

from fastapi import HTTPException


@dataclass(frozen=True)
class ErrorSpec:
    """单条错误码规格。"""

    code: str
    http_status: int
    message: str          # 中文默认文案（可含 {name} 格式占位）
    hint: str = ""        # 中文处置建议
    retryable: bool = False


# ---------------------------------------------------------------------------
# 目录（与 docs/spec/ERROR_CODES.md §3 一一对应；新增错误码先改文档再改这里）
# ---------------------------------------------------------------------------

CATALOG: dict[str, ErrorSpec] = {
    # A0 通用
    "A0001": ErrorSpec("A0001", 422, "请求参数校验失败", "请检查输入内容是否完整、格式是否正确"),
    "A0002": ErrorSpec("A0002", 429, "请求过于频繁，请稍后再试", "请放慢操作频率；连续触发请等待 1 分钟", True),
    "A0003": ErrorSpec("A0003", 400, "文本过长（上限 {max} 字符）", "请分段输入或精简内容"),
    "A0004": ErrorSpec("A0004", 400, "音频过大，请分段说话或改用文字输入", "单次发言请控制在 2 分钟内"),
    "A0005": ErrorSpec("A0005", 400, "文件为空", "请选择非空文件重新上传"),
    "A0006": ErrorSpec("A0006", 400, "请先配置 API Key", "请到「设置」页填写思考处理器的 API Base 与 Key"),
    "A0007": ErrorSpec("A0007", 400, "URL 不安全", "仅允许 https 公网地址；本地模型请在 .env 显式开启 ALLOW_LOCAL_LLM"),
    "A0401": ErrorSpec("A0401", 403, "无权访问该会话", "会话令牌已失效，请回到列表页重新进入"),
    "A0403": ErrorSpec("A0403", 403, "跨站请求被拒绝", "请从本站页面发起操作，不要直接调用接口"),
    "A0404": ErrorSpec("A0404", 404, "请求的资源不存在", "可能已被删除，请返回列表页刷新"),
    "A0405": ErrorSpec("A0405", 403, "仅允许本机访问管理接口", "请在部署本机的浏览器访问"),
    "A0413": ErrorSpec("A0413", 413, "文件超过 {max}MB 上限", "请压缩文件或改用 DOCX/TXT 格式后重试"),
    # A1 简历
    "A1001": ErrorSpec("A1001", 400, "文件名不能为空", "请检查所选文件后重试"),
    "A1002": ErrorSpec("A1002", 400, "不支持的文件格式，允许：{exts}", "请上传 PDF / DOCX / MD / TXT 格式简历"),
    "A1003": ErrorSpec("A1003", 400, "文件内容与扩展名不匹配", "文件可能已损坏或被篡改，请重新导出后再上传"),
    "A1004": ErrorSpec("A1004", 400, "文件解析失败，请检查格式", "扫描件 PDF 无法提取文字，请改用文字版或 DOCX"),
    "A1005": ErrorSpec("A1005", 404, "简历不存在", "简历可能已被删除，请刷新列表"),
    # A2 面试
    "A2001": ErrorSpec("A2001", 404, "面试会话不存在", "会话可能已过期或删除，请新建面试"),
    "A2002": ErrorSpec("A2002", 400, "面试已结束", "本场面试已完成，可前往报告页查看结果"),
    "A2003": ErrorSpec("A2003", 400, "面试尚未结束", "请先完成面试再查看报告"),
    "A2004": ErrorSpec("A2004", 404, "报告尚未生成", "报告正在后台生成中，请稍后刷新；若长时间未生成请点击重试", True),
    # A3 辅导
    "A3001": ErrorSpec("A3001", 404, "辅导会话不存在", "会话可能已过期，请新建辅导会话"),
    "A3002": ErrorSpec("A3002", 400, "辅导会话已结束", "本辅导会话已关闭，请新建会话"),
    # A4 设置
    "A4001": ErrorSpec("A4001", 400, "所选供应商不支持面试思考", "请在设置页更换支持 Chat Completions 的供应商"),
    "A4002": ErrorSpec("A4002", 400, "该识别处理者不支持转写", "请更换识别处理器或改用本地 Whisper"),
    "A4003": ErrorSpec("A4003", 400, "语音配置无效", "请检查识别/播报处理器的 Base、Key、模型名是否完整"),
    "A4004": ErrorSpec("A4004", 400, "stage 须为 recognize / reason / speak", "请从设置页按钮发起测试，勿直接调用"),
    "A4005": ErrorSpec("A4005", 404, "供应商或模型条目不存在", "可能已被删除，请刷新设置页后重试"),
    # B 系统
    "B0001": ErrorSpec("B0001", 500, "服务器内部错误，请稍后重试", "若反复出现，请携带 trace_id 反馈给开发者", True),
    "B1001": ErrorSpec("B1001", 500, "结果写入失败，请稍后重试", "本地数据库写入异常；若反复出现请检查磁盘空间与文件权限", True),
    # C 第三方
    "C0001": ErrorSpec("C0001", 502, "AI 服务暂时不可用，请稍后重试", "请检查 API Key 额度与网络；持续失败请到设置页测试连通性", True),
    "C0002": ErrorSpec("C0002", 502, "模型未返回有效结果，请稍后重试", "当前模型可能不兼容（仅推理/空输出），请更换模型后重试", True),
    "C1001": ErrorSpec("C1001", 502, "报告生成失败，请稍后重试", "请到报告页点击重新生成；口头收尾内容不受影响", True),
    "C2001": ErrorSpec("C2001", 200, "未能识别语音内容，请重新说话或手动输入", "请靠近麦克风、降低环境噪音；也可改用文字作答", True),
    "C2002": ErrorSpec("C2002", 200, "语音合成失败，本轮仅显示字幕", "请检查播报处理器配置；可在设置页切换 Edge TTS", True),
    "C3001": ErrorSpec("C3001", 200, "联网搜索暂时不可用，已基于通用知识继续", "检索失败不影响主流程；如需实时信息请稍后重试", True),
    "C4001": ErrorSpec("C4001", 200, "知识库检索失败，已按无知识库模式继续", "检索降级不影响面试；请检查 RAG 配置与 embeddings 服务", True),
}


class ApiBusinessError(HTTPException):
    """携带业务错误码的 HTTP 异常。

    继承 :class:`HTTPException` 以保持与现有 ``raise HTTPException`` 调用
    的语义一致（status_code/detail），同时新增 ``error_code``/``error_hint``
    ``error_retryable`` 三个属性供 envelope handler 读取，构造业务级
    错误响应。

    支持额外响应头（429 Retry-After 等）：构造时传 ``headers=...``，或在
    raise 之前用 ``with_headers(...)`` 链式追加。envelope handler 会自动
    透传这些头到 JSONResponse。
    """

    def __init__(
        self,
        spec: ErrorSpec,
        *,
        message: str,
        cause: Exception | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(
            status_code=spec.http_status,
            detail=message,
            headers=headers,
        )
        self.error_code = spec.code
        self.error_hint = spec.hint
        self.error_retryable = spec.retryable
        if cause is not None:
            self.__cause__ = cause

    def with_headers(self, headers: dict[str, str]) -> "ApiBusinessError":
        """链式追加响应头；返回 self 以便 raise 之前组装。

        用法：`
            raise ApiBusinessError(spec, message=...)\n
                .with_headers({"Retry-After": "60"})
        `
        """
        existing = dict(self.headers or {})
        existing.update(headers)
        self.headers = existing
        return self


def get_spec(code: str) -> ErrorSpec:
    """根据错误码获取 :class:`ErrorSpec`，未注册时降级为 B0001。

    保证 :func:`raise_error` 对任意字符串都不会抛 KeyError，
    让迁移期间临时引用未注册码也能继续工作。
    """
    return CATALOG.get(code) or CATALOG["B0001"]


def raise_error(code: str, *, cause: Exception | None = None, **fmt: object) -> NoReturn:
    """抛出携带错误码的业务异常（使用目录默认 message）。

    参数:
    - code: 错误码；未注册时降级为 B0001（永不抛 KeyError）
    - cause: 链式原始异常，附加到 __cause__
    - **fmt: 格式化目录 message 中的占位符，例如
      raise_error("A0413", max=10) -> "文件超过 10MB 上限"

    需要完全自定义 message 的场景（如 settings.py 的 URL 校验动态文案）:
    raise ApiBusinessError(get_spec("A0007"), message="<动态文案>")
    """
    spec = get_spec(code)
    message = spec.message.format(**fmt) if fmt else spec.message
    raise ApiBusinessError(spec, message=message, cause=cause)


__all__ = ["CATALOG", "ApiBusinessError", "ErrorSpec", "get_spec", "raise_error"]
