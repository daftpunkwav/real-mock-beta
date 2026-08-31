"""InterviewRunner 单元测试。"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator


from shared.models import LLMSettings
from interview_service.models import InterviewSession
from interview_service.services.interview.events import EventKind
from interview_service.services.interview.runner import InterviewRunner
from tests.fakes import FakeLLMClient


def _make_session(db) -> InterviewSession:
    s = InterviewSession(
        profile_id=1,
        role="后端工程师",
        level="中级工程师",
        company="bytedance",
        workflow_type="technical",
        personality="professional",
        strictness=3,
        interview_style="deep_dive",
        avatar_id="professional_male",
        scene_id="meeting_room",
        status="pending",
        current_phase="identity_check",
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


async def _consume(events: AsyncIterator) -> list:
    return [e async for e in events]


def _proto_tokens(say: str, **controls) -> list[str]:
    """构造 say-first 协议 JSON 并切成多段，模拟流式输出（覆盖跨 token 场景）。"""
    payload = {
        "say": say,
        "v": 1,
        "wait_seconds": 30,
        "emotion": "neutral",
        "phase_complete": False,
        "interview_complete": False,
        "turn_score": None,
        "probe": None,
        "sources": [],
    }
    payload.update(controls)
    text = json.dumps(payload, ensure_ascii=False)
    return [text[i : i + 7] for i in range(0, len(text), 7)]


def test_stream_opening_records_first_question(db) -> None:
    """开场回合应流式输出 say 明文并保存状态；控制字段随 TURN_COMPLETE 下发。"""
    session = _make_session(db)
    say = "你好，我是面试官。请自我介绍一下。"
    llm = FakeLLMClient(tokens=_proto_tokens(say, wait_seconds=60))
    runner = InterviewRunner(session, llm)

    events = []
    import asyncio

    async def run():
        async for e in runner.stream_opening(db):
            events.append(e)

    asyncio.run(run())

    tokens = [e.token for e in events if e.kind == EventKind.TOKEN]
    assert "".join(tokens) == say

    turn_done = next(e for e in events if e.kind == EventKind.TURN_COMPLETE)
    assert turn_done.content == say
    assert turn_done.phase_id == "identity_check"
    assert turn_done.is_complete is False
    assert turn_done.wait_seconds == 60

    db.refresh(session)
    assert session.status == "active"
    assert session.started_at is not None
    state = json.loads(session.agent_state)
    assert state["phase_idx"] == 0
    assert state["questions_in_phase"] == 1


def test_stream_turn_plain_text_falls_back(db) -> None:
    """模型未按协议输出（纯文本）时应整体降级为 say，回合不中断。"""
    session = _make_session(db)
    session.agent_state = json.dumps({"phase_idx": 3, "questions_in_phase": 0})
    session.current_phase = "project_deep_dive"
    db.commit()
    db.refresh(session)

    llm = FakeLLMClient(tokens=["直接说话，", "没有 JSON 结构。"])
    runner = InterviewRunner(session, llm)

    import asyncio

    async def run():
        events = []
        async for e in runner.stream_turn("我叫张三", db):
            events.append(e)
        return events

    events = asyncio.run(run())
    turn_done = next(e for e in events if e.kind == EventKind.TURN_COMPLETE)
    assert turn_done.content == "直接说话，没有 JSON 结构。"
    assert turn_done.phase_changed is False
    assert turn_done.emotion == "neutral"


def test_stream_turn_increments_question_count(db) -> None:
    """普通回合在未达 max_questions 时不应触发 phase_changed。"""
    session = _make_session(db)
    # 手动把 phase_idx 推到 project_deep_dive（max=6）避免自动 advance
    session.agent_state = json.dumps({"phase_idx": 3, "questions_in_phase": 0})
    session.current_phase = "project_deep_dive"
    db.commit()
    db.refresh(session)

    llm = FakeLLMClient(tokens=["好的，", "请讲讲你最擅长的项目。"])
    runner = InterviewRunner(session, llm)

    import asyncio

    async def run():
        events = []
        async for e in runner.stream_turn("我叫张三", db):
            events.append(e)
        return events

    events = asyncio.run(run())
    turn_done = next(e for e in events if e.kind == EventKind.TURN_COMPLETE)
    assert turn_done.phase_id == "project_deep_dive"
    assert turn_done.phase_changed is False

    db.refresh(session)
    state = json.loads(session.agent_state)
    assert state["questions_in_phase"] == 1


def test_stream_turn_advances_phase_on_marker(db) -> None:
    """回合协议 phase_complete=true 时应推进到下一阶段。"""
    session = _make_session(db)
    llm = FakeLLMClient(
        stream_sequences=[
            _proto_tokens("你好，先核实一下身份信息。"),  # 开场
            _proto_tokens("好的，身份确认完毕。", phase_complete=True),  # 回合
        ]
    )
    runner = InterviewRunner(session, llm)

    import asyncio

    async def run():
        async for _ in runner.stream_opening(db):
            pass
        events = []
        async for e in runner.stream_turn("我叫张三", db):
            events.append(e)
        return events

    events = asyncio.run(run())
    turn_done = next(e for e in events if e.kind == EventKind.TURN_COMPLETE)
    assert turn_done.phase_changed is True
    assert turn_done.phase_id == "self_intro"

    db.refresh(session)
    state = json.loads(session.agent_state)
    assert state["phase_idx"] == 1
    assert state["questions_in_phase"] == 0


def test_stream_turn_advances_phase_on_max_reached(db) -> None:
    """问题数达到当前阶段 max 时自动推进（无需协议标志）。"""
    session = _make_session(db)
    # identity_check 阶段 max_questions = 1
    llm = FakeLLMClient(tokens=_proto_tokens("继续。"))
    runner = InterviewRunner(session, llm)

    import asyncio

    async def run():
        async for _ in runner.stream_opening(db):
            pass
        events = []
        async for e in runner.stream_turn("回答", db):
            events.append(e)
        return events

    events = asyncio.run(run())
    turn_done = next(e for e in events if e.kind == EventKind.TURN_COMPLETE)
    assert turn_done.phase_changed is True
    assert turn_done.phase_id == "self_intro"


def test_stream_turn_marks_complete_on_interview_flag(db) -> None:
    """协议 interview_complete=true 应结束面试。"""
    session = _make_session(db)
    llm = FakeLLMClient(
        tokens=_proto_tokens("面试结束，感谢你的时间。", interview_complete=True)
    )
    runner = InterviewRunner(session, llm)

    import asyncio

    async def run():
        events = []
        async for e in runner.stream_turn("最后一条回答", db):
            events.append(e)
        return events

    events = asyncio.run(run())
    turn_done = next(e for e in events if e.kind == EventKind.TURN_COMPLETE)
    assert turn_done.is_complete is True

    db.refresh(session)
    assert session.status == "completed"
    assert session.ended_at is not None


def test_stream_turn_with_face_appends_hints(db) -> None:
    """面部分析提示应拼接到 LLM 消息文本。"""
    session = _make_session(db)
    llm = FakeLLMClient(tokens=["好。"])
    runner = InterviewRunner(session, llm)

    import asyncio

    async def run():
        async for _ in runner.stream_turn("我在听", db, face={
            "face_detected": True,
            "looking_away": True,
            "nervousness": 0.8,
        }):
            pass

    asyncio.run(run())

    last_call = llm.stream_calls[-1]
    user_msg = next(m for m in reversed(last_call) if m["role"] == "user")
    assert "面部分析" in user_msg["content"]
    assert "看镜头" in user_msg["content"]
    assert "紧张" in user_msg["content"]


def test_stream_turn_emits_error_on_llm_failure(db, monkeypatch) -> None:
    """LLM 抛错时应输出 ERROR 事件而不崩溃。"""
    session = _make_session(db)

    class BrokenLLM(FakeLLMClient):
        async def chat_stream(self, messages, temperature: float = 0.75, tools=None):
            raise RuntimeError("LLM 不可用")
            yield  # unreachable，但让 mypy 满意

    runner = InterviewRunner(session, BrokenLLM())
    import asyncio

    async def run():
        events = []
        async for e in runner.stream_turn("测试", db):
            events.append(e)
        return events

    events = asyncio.run(run())
    errors = [e for e in events if e.kind == EventKind.ERROR]
    assert errors and "暂时不可用" in (errors[0].error or "")


def test_stream_turn_injects_followup_probe_when_vague(db) -> None:
    """模糊回答触发追问引导注入到 LLM messages。"""
    session = _make_session(db)
    # 注入上一轮 LLM 提问
    session.messages = json.dumps([
        {"role": "system", "content": "你是面试官"},
        {"role": "assistant", "content": "请描述一次性能优化经历"},
    ])
    db.commit()
    db.refresh(session)

    llm = FakeLLMClient(tokens=["好的。"])
    runner = InterviewRunner(session, llm)

    import asyncio

    async def run():
        async for _ in runner.stream_turn("差不多就是这样吧", db):
            pass

    asyncio.run(run())

    last_call = llm.stream_calls[-1]
    system_msgs = [m["content"] for m in last_call if m["role"] == "system"]
    assert any("追问引导" in s and "vague" in s for s in system_msgs), system_msgs


def test_stream_turn_no_followup_probe_when_solid(db) -> None:
    """具体回答不应触发追问引导。"""
    session = _make_session(db)
    session.messages = json.dumps([
        {"role": "system", "content": "你是面试官"},
        {"role": "assistant", "content": "请说说性能优化的效果"},
    ])
    db.commit()
    db.refresh(session)

    llm = FakeLLMClient(tokens=["好。"])
    runner = InterviewRunner(session, llm)

    import asyncio

    async def run():
        async for _ in runner.stream_turn(
            "接口 RT 从 200ms 降到 35ms，QPS 提升 5 倍，错误率下降 90%。",
            db,
        ):
            pass

    asyncio.run(run())

    last_call = llm.stream_calls[-1]
    system_msgs = [m["content"] for m in last_call if m["role"] == "system"]
    assert not any("追问引导" in s for s in system_msgs)


def test_stream_turn_applies_context_compression(db) -> None:
    """context_window 较小时应触发上下文压缩。"""
    session = _make_session(db)
    # 写入 200 条 user/assistant 对话，迫使压缩
    base = [{"role": "system", "content": "你是面试官"}]
    base += [
        {"role": "user" if i % 2 == 0 else "assistant",
         "content": "对话内容" * 20}
        for i in range(40)
    ]
    session.messages = json.dumps(base, ensure_ascii=False)
    settings = db.query(LLMSettings).filter(LLMSettings.id == 1).first()
    if settings is None:
        settings = LLMSettings(id=1, api_key="x", api_base="http://x", model="m",
                                context_window=500, max_tokens=100)
        db.add(settings)
    else:
        settings.context_window = 500
    db.commit()
    db.refresh(session)

    llm = FakeLLMClient(tokens=["好。"])
    runner = InterviewRunner(session, llm)

    import asyncio

    async def run():
        async for _ in runner.stream_turn("新回答", db):
            pass

    asyncio.run(run())

    last_call = llm.stream_calls[-1]
    # 压缩后消息数应少于原始
    assert len(last_call) < len(base) + 1  # +1 for new user msg
    # 应包含压缩说明
    assert any("上下文压缩" in m.get("content", "") for m in last_call)


def test_stream_turn_injects_rag_context(db) -> None:
    """当 RAG 命中时，检索片段应作为 system 消息注入到 LLM 调用。"""
    import uuid
    from pathlib import Path

    # 用临时目录隔离 chroma
    chroma_dir = Path(db.get_bind().url.database).parent / f"chroma_{uuid.uuid4().hex[:6]}"
    chroma_dir.mkdir(parents=True, exist_ok=True)


    class _StubRAG:
        def __init__(self):
            self.embed_called_with: list[str] = []

        async def query_for_company(self, query, company_id, top_k=4):
            self.embed_called_with.append(query)
            return [
                {
                    "text": f"{company_id} 风格：高频追问",
                    "metadata": {"company_id": company_id, "section": "style"},
                    "distance": 0.1,
                },
            ]

        async def query(self, query, top_k=3, company_id=None):
            return []

    rag = _StubRAG()
    session = _make_session(db)
    session.messages = json.dumps([
        {"role": "system", "content": "你是面试官"},
        {"role": "assistant", "content": "请说说性能优化"},
    ], ensure_ascii=False)
    db.commit()
    db.refresh(session)

    llm = FakeLLMClient(tokens=["好。"])
    runner = InterviewRunner(session, llm, rag=rag)

    import asyncio

    async def run():
        async for _ in runner.stream_turn("接口 RT 从 200ms 降到 35ms", db):
            pass

    asyncio.run(run())

    last_call = llm.stream_calls[-1]
    system_msgs = [m["content"] for m in last_call if m["role"] == "system"]
    assert any("企业知识库检索补充" in s and "bytedance" in s for s in system_msgs), system_msgs


def test_stream_turn_skips_rag_when_no_hits(db) -> None:
    """RAG 无命中时不应注入空片段。"""
    class _EmptyRAG:
        async def query_for_company(self, query, company_id, top_k=4):
            return []
        async def query(self, query, top_k=3, company_id=None):
            return []

    rag = _EmptyRAG()
    session = _make_session(db)
    session.messages = json.dumps([
        {"role": "system", "content": "你是面试官"},
        {"role": "assistant", "content": "自我介绍"},
    ], ensure_ascii=False)
    db.commit()
    db.refresh(session)

    llm = FakeLLMClient(tokens=["好。"])
    runner = InterviewRunner(session, llm, rag=rag)

    import asyncio

    async def run():
        async for _ in runner.stream_turn("我叫张三", db):
            pass

    asyncio.run(run())

    last_call = llm.stream_calls[-1]
    system_msgs = [m["content"] for m in last_call if m["role"] == "system"]
    assert not any("企业知识库" in s for s in system_msgs)


def test_stream_turn_rag_error_does_not_break_turn(db) -> None:
    """RAG 抛错时面试回合应正常完成，不影响主流程。"""
    class _BrokenRAG:
        async def query_for_company(self, query, company_id, top_k=4):
            raise RuntimeError("RAG unavailable")
        async def query(self, query, top_k=3, company_id=None):
            raise RuntimeError("RAG unavailable")

    rag = _BrokenRAG()
    session = _make_session(db)
    session.messages = json.dumps([
        {"role": "system", "content": "你是面试官"},
        {"role": "assistant", "content": "自我介绍"},
    ], ensure_ascii=False)
    db.commit()
    db.refresh(session)

    llm = FakeLLMClient(tokens=["好的。"])
    runner = InterviewRunner(session, llm, rag=rag)

    import asyncio

    async def run():
        events = []
        async for e in runner.stream_turn("我叫李四", db):
            events.append(e)
        return events

    events = asyncio.run(run())
    # 应有 turn_done 且无 error
    assert any(e.kind.value == "turn_done" for e in events)
    assert not any(e.kind.value == "error" for e in events)


def test_agent_public_methods_no_longer_underscore(db) -> None:
    """确保私有字段已被收敛为公共方法（防止 ws_handler 直接访问）。"""
    from interview_service.services.interview.session_state import InterviewSessionState

    public = {
        "save_state", "current_phase", "phases_remaining",
        "mark_active", "mark_completed",
        "record_user_text", "record_assistant_text",
        "advance_phase_if_needed",
        "build_opening_prompt", "refresh_system_memory",
        "set_questions_in_phase", "reset_messages",
    }
    assert public.issubset(set(dir(InterviewSessionState)))


def test_refresh_system_memory_updates_asked_questions(db) -> None:
    """每回合刷新 system prompt 中的结构化记忆，使 asked_questions 反映最新值。"""
    from interview_service.services.interview.session_state import InterviewSessionState

    session = _make_session(db)
    session.messages = json.dumps([
        {"role": "system", "content": "你是面试官"},
    ], ensure_ascii=False)
    db.commit()
    db.refresh(session)

    llm = FakeLLMClient(tokens=["好。"])
    agent = InterviewSessionState(session, llm)
    # 模拟开场后已问过一个问题
    agent.agent_state.setdefault("asked_questions", [])
    agent.agent_state["asked_questions"].append("请介绍一下你的 Redis 缓存设计方案")
    agent.refresh_system_memory()

    system_content = agent.messages[0]["content"]
    assert "会话结构化记忆" in system_content
    assert "Redis 缓存设计方案" in system_content


def test_refresh_system_memory_replaces_old_memory(db) -> None:
    """刷新应替换旧记忆段落而非重复追加。"""
    from interview_service.services.interview.session_state import InterviewSessionState

    session = _make_session(db)
    session.messages = json.dumps([
        {"role": "system", "content": (
            "你是面试官\n\n"
            "## 会话结构化记忆（请勿重复已问问题）\n"
            "已问问题摘要：\n- 旧问题A"
        )},
    ], ensure_ascii=False)
    db.commit()
    db.refresh(session)

    agent = InterviewSessionState(session, FakeLLMClient())
    agent.agent_state.setdefault("asked_questions", [])
    agent.agent_state["asked_questions"] = ["新问题B"]
    agent.refresh_system_memory()

    system_content = agent.messages[0]["content"]
    # 旧记忆应被替换：不再包含旧问题A，应包含新问题B
    assert "旧问题A" not in system_content
    assert "新问题B" in system_content
    # 不应出现两段记忆标记
    assert system_content.count("## 会话结构化记忆") == 1


def test_stream_turn_records_weak_point_on_followup(db) -> None:
    """追问触发时应记录薄弱线索到 agent_state.weak_points。"""
    session = _make_session(db)
    session.messages = json.dumps([
        {"role": "system", "content": "你是面试官"},
        {"role": "assistant", "content": "请描述一次性能优化经历"},
    ])
    db.commit()
    db.refresh(session)

    llm = FakeLLMClient(tokens=["好的。"])
    runner = InterviewRunner(session, llm)

    import asyncio

    async def run():
        async for _ in runner.stream_turn("差不多就是这样吧", db):
            pass

    asyncio.run(run())

    db.refresh(session)
    state = json.loads(session.agent_state)
    weak = state.get("weak_points") or []
    # 追问触发后应有至少一条薄弱线索，且标注了 category
    assert weak, f"weak_points 不应为空: {state}"
    assert any("vague" in w for w in weak)
    # 真实追问类别应记录到 followup_clues（供系统学习统计）
    clues = state.get("followup_clues") or []
    assert "vague" in clues, f"followup_clues 应包含 vague: {clues}"


def test_build_opening_prompt_includes_system_learning(db, monkeypatch) -> None:
    """开场 prompt 应注入系统学习摘要（自我成长反哺闭环）。"""
    from interview_service.services.growth import learning as learning_mod

    # mock 系统学习数据：该公司低均分 + 有薄弱线索
    monkeypatch.setattr(
        learning_mod, "get_system_insights",
        lambda limit=10: {
            "avg_scores_by_company": {"bytedance": 65},
            "recent_probes": [
                {"company": "bytedance", "role": "后端工程师",
                 "point": "缓存一致性理解不足"},
            ],
        },
    )

    session = _make_session(db)  # company=bytedance role=后端工程师
    llm = FakeLLMClient()
    runner = InterviewRunner(session, llm)

    import asyncio

    async def run():
        async for _ in runner.stream_opening(db):
            pass

    asyncio.run(run())

    system_content = runner.agent.messages[0]["content"]
    # 应包含系统学习摘要，引用历史均分与薄弱线索
    assert "系统学习摘要" in system_content
    assert "65" in system_content
    assert "缓存一致性" in system_content


def test_build_opening_prompt_without_system_learning(db, monkeypatch) -> None:
    """无系统学习数据时不应注入空摘要段落。"""
    from interview_service.services.growth import learning as learning_mod

    monkeypatch.setattr(
        learning_mod, "get_system_insights",
        lambda limit=10: {
            "avg_scores_by_company": {},
            "recent_probes": [],
        },
    )

    session = _make_session(db)
    llm = FakeLLMClient()
    runner = InterviewRunner(session, llm)

    import asyncio

    async def run():
        async for _ in runner.stream_opening(db):
            pass

    asyncio.run(run())

    system_content = runner.agent.messages[0]["content"]
    assert "系统学习摘要" not in system_content


def test_reverse_qa_phase_injects_company_representative_prompt(db) -> None:
    """进入反问环节时应注入「公司代表角色」专门 prompt。"""

    session = _make_session(db)
    # 把 phase_idx 设到 reverse_qa 前一阶段（scenario），questions_in_phase
    # 设为 max，使 advance_phase_if_needed 推进到 reverse_qa
    session.agent_state = json.dumps({
        "phase_idx": 6,  # scenario
        "questions_in_phase": 2,  # scenario.max_questions=2
    })
    session.current_phase = "scenario"
    db.commit()
    db.refresh(session)

    llm = FakeLLMClient(tokens=["好的，进入反问。"])
    runner = InterviewRunner(session, llm)

    import asyncio

    async def run():
        async for _ in runner.stream_turn("我的回答", db):
            pass

    asyncio.run(run())

    # 推进到 reverse_qa 后，messages 中应有公司代表 prompt
    system_msgs = [m["content"] for m in runner.agent.messages if m["role"] == "system"]
    reverse_qa_msg = next(
        (s for s in system_msgs if "角色切换" in s and "代表" in s), None
    )
    assert reverse_qa_msg is not None, f"未找到公司代表 prompt: {system_msgs}"
    # 应包含公司知识（bytedance -> 字节跳动）
    assert "字节跳动" in reverse_qa_msg
    # 应强调坦诚说明未覆盖内容
    assert "没有确切信息" in reverse_qa_msg


def test_non_reverse_qa_phase_uses_generic_entry_message(db) -> None:
    """非反问环节的阶段推进应使用通用引导，不含公司代表 prompt。"""
    session = _make_session(db)
    # identity_check(idx=0, max=1) -> 推进到 self_intro
    session.agent_state = json.dumps({"phase_idx": 0, "questions_in_phase": 1})
    session.current_phase = "identity_check"
    db.commit()
    db.refresh(session)

    llm = FakeLLMClient(tokens=["好的。"])
    runner = InterviewRunner(session, llm)

    import asyncio

    async def run():
        async for _ in runner.stream_turn("回答", db):
            pass

    asyncio.run(run())

    system_msgs = [m["content"] for m in runner.agent.messages if m["role"] == "system"]
    # 进入 self_intro 的消息应是通用引导，不含「角色切换」
    entry_msgs = [s for s in system_msgs if "进入新阶段" in s]
    assert entry_msgs, f"应有阶段进入消息: {system_msgs}"
    assert not any("角色切换" in s for s in entry_msgs)