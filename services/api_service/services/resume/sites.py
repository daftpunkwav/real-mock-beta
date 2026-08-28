"""求职市场 / 简历评价联网搜索的站点配置（api_service 简历域）。

当前默认不限定站点（全网检索）。后续可在 ``RESUME_MARKET_SEARCH_SITES``
中填入域名，例如牛客、BOSS 直聘，``web_search(..., sites=...)`` 会自动加
``site:`` 过滤。

从 ``shared.capabilities.knowledge.search.sites`` 下沉：仅 api_service 简历
解析消费，与三服务共用的 ``web_search`` 解耦。
"""

from __future__ import annotations

# 预留站点域名（不含协议与路径）。启用示例：
# RESUME_MARKET_SEARCH_SITES = [
#     "nowcoder.com",      # 牛客
#     "zhipin.com",        # BOSS 直聘
#     "liepin.com",        # 猎聘
#     "lagou.com",         # 拉勾
#     "linkedin.com",
# ]
RESUME_MARKET_SEARCH_SITES: list[str] = []

# 站点中文名，便于日志与调试展示
RESUME_MARKET_SITE_LABELS: dict[str, str] = {
    "nowcoder.com": "牛客",
    "zhipin.com": "BOSS直聘",
    "liepin.com": "猎聘",
    "lagou.com": "拉勾",
    "linkedin.com": "LinkedIn",
}
