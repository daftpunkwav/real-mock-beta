"""企业面试风格知识库。"""

from shared.schemas import CompanyInfo

# 内置企业面试模型
BUILTIN_COMPANIES: list[dict] = [
    {
        "id": "bytedance",
        "name": "字节跳动",
        "style": "高频追问、强项目深挖、重视业务思考与数据量化",
        "focus_areas": ["项目深挖", "业务理解", "性能优化", "系统设计", "算法基础"],
        "sample_questions": [
            "你刚才说优化了接口性能，请具体解释优化前后的 QPS 数据。",
            "这个方案的业务价值是什么？如何衡量成功？",
            "如果流量增长 10 倍，你的架构如何扩展？",
        ],
        "interview_flow": "自我介绍 → 项目深挖(40%) → 技术基础 → 系统设计 → 反问",
        "pressure_level": "高",
    },
    {
        "id": "tencent",
        "name": "腾讯",
        "style": "技术基础扎实、项目经验、团队协作与故障处理",
        "focus_areas": ["基础知识", "项目经验", "团队协作", "故障处理", "代码质量"],
        "sample_questions": [
            "如果线上出现重大事故，你如何定位和处理？",
            "描述一次你与同事产生技术分歧的经历，如何解决的？",
            "Explain the difference between TCP and UDP.",
        ],
        "interview_flow": "自我介绍 → 基础知识 → 项目经历 → 情景题 → 反问",
        "pressure_level": "中",
    },
    {
        "id": "alibaba",
        "name": "阿里巴巴",
        "style": "业务思考、技术深度、价值观匹配",
        "focus_areas": ["业务理解", "技术深度", "分布式系统", "高并发", "价值观"],
        "sample_questions": [
            "你如何理解这个业务场景的核心痛点？",
            "设计一个支持千万级用户的秒杀系统。",
            "描述你最有成就感的项目，你在其中扮演什么角色？",
        ],
        "interview_flow": "自我介绍 → 项目经历 → 技术深挖 → 系统设计 → 价值观 → 反问",
        "pressure_level": "中高",
    },
    {
        "id": "meituan",
        "name": "美团",
        "style": "工程能力、业务落地、问题解决",
        "focus_areas": ["工程实践", "业务落地", "性能优化", "数据驱动"],
        "sample_questions": [
            "你如何用数据驱动技术决策？",
            "描述一个你从 0 到 1 落地的项目。",
        ],
        "interview_flow": "自我介绍 → 项目 → 技术 → 业务场景 → 反问",
        "pressure_level": "中",
    },
    {
        "id": "mihoyo",
        "name": "米哈游",
        "style": "项目经历、引擎理解、性能优化、游戏开发 passion",
        "focus_areas": ["游戏引擎", "性能优化", "渲染管线", "项目经验", "GC/内存"],
        "sample_questions": [
            "Unity 中 GC 造成卡顿，你会如何排查？",
            "描述你参与的游戏项目中最有挑战性的技术问题。",
            "如何优化 Draw Call 数量？",
        ],
        "interview_flow": "自我介绍 → 项目深挖 → 引擎/图形 → 算法 → 反问",
        "pressure_level": "中高",
    },
    {
        "id": "openai",
        "name": "OpenAI",
        "style": "技术深度、研究能力、系统设计、AI/ML 专长",
        "focus_areas": ["机器学习", "系统设计", "编程能力", "研究思维", "工程实践"],
        "sample_questions": [
            "Design a distributed training system for large language models.",
            "How would you debug a model that performs well on training but poorly in production?",
        ],
        "interview_flow": "自我介绍 → 技术深挖 → Coding → System Design → 反问",
        "pressure_level": "高",
    },
    {
        "id": "google",
        "name": "Google",
        "style": "算法、系统设计、领导力、Googleyness",
        "focus_areas": ["算法", "系统设计", "代码质量", "领导力", "创新思维"],
        "sample_questions": [
            "Design Google Maps routing algorithm at scale.",
            "Tell me about a time you had to make a difficult technical trade-off.",
        ],
        "interview_flow": "自我介绍 → Coding → System Design → Behavioral → 反问",
        "pressure_level": "高",
    },
]


def get_all_companies() -> list[CompanyInfo]:
    companies = []
    for c in BUILTIN_COMPANIES:
        companies.append(CompanyInfo(
            id=c["id"],
            name=c["name"],
            style=c["style"],
            focus_areas=c["focus_areas"],
            sample_questions=c["sample_questions"],
        ))
    return companies


def get_company_by_id(company_id: str) -> dict | None:
    for c in BUILTIN_COMPANIES:
        if c["id"] == company_id or c["name"] == company_id:
            return c
    return None


def get_company_context(company_id: str) -> str:
    """为 Agent 生成企业面试风格上下文。"""
    company = get_company_by_id(company_id)
    if not company:
        return "通用技术面试风格：注重基础、项目经验和技术深度。"

    return f"""## 目标公司：{company['name']}
面试风格：{company['style']}
重点领域：{', '.join(company['focus_areas'])}
典型面试流程：{company['interview_flow']}
压力等级：{company['pressure_level']}
参考问题风格：
{chr(10).join(f'- {q}' for q in company['sample_questions'])}"""
