"""B4: 压缩不毁前缀（PHASE-B §5 B4）。

把压缩从"原位改写旧消息（G2）"改为"断点前不可变、压缩只替换断点之后"：
1. 击穿测试：压缩前前缀 A → 压缩后前缀 A 字节不变（当前实现必须失败）。
2. 摘要模板 Objective / Work State / Next Move。
3. 尾部保留 25% + system 永不裁剪。
4. 不拆 assistant↔tool 对（配对守恒）。
5. 压缩后命中率有度量证据（tokens_before/after 遥测）。
"""

from __future__ import annotations

import pytest


class TestCompactionDoesNotMutatePrefix:
    """B4 判据 1：压缩不改写任何断点前消息（字节级）。"""

    def test_compaction_never_mutates_cached_prefix(self):
        """击穿测试：压缩后断点前消息字节不变（G2 回归防线）。

        断点前（前缀区）= system 消息，字节必须保持不变；
        human 是断点后消息，可被折叠（其内容进摘要）。
        """
        from RxyCode.RxyCode1_1_0.core.compaction import compact_messages

        from types import SimpleNamespace

        # 断点前（前缀区）：system —— 字节必须保持不变
        prefix_msgs = [
            SimpleNamespace(type="system", content="SYS_PREFIX", additional_kwargs={}),
            SimpleNamespace(type="human", content="USER_TASK", additional_kwargs={}),
        ]
        # 断点后（可折叠区）：assistant + tool 循环（长输出）
        tail_msgs = [
            SimpleNamespace(
                type="ai",
                content="Let me check",
                tool_calls=[{"id": "c1", "name": "read", "args": {"path": "/x"}}],
                additional_kwargs={},
            ),
            SimpleNamespace(
                type="tool", content="X" * 5000, tool_call_id="c1", additional_kwargs={}
            ),
            SimpleNamespace(
                type="ai", content="Result is ...", tool_calls=[], additional_kwargs={}
            ),
        ]
        messages = prefix_msgs + tail_msgs

        out = compact_messages(messages, tail_turns=1)

        # 断点前（system，索引 0）必须逐字节不变
        assert out[0].content == "SYS_PREFIX"
        assert out[0].additional_kwargs == {}
        # human（断点后消息）可被折叠进摘要——内容出现在摘要中或保留
        contents = [getattr(m, "content", "") for m in out]
        assert any("USER_TASK" in c for c in contents)
        # 原消息对象不被修改
        assert prefix_msgs[0].content == "SYS_PREFIX"

    def test_original_messages_not_mutated(self):
        """压缩不修改任何传入消息对象（append-only 纪律）。"""
        from RxyCode.RxyCode1_1_0.core.compaction import compact_messages

        from types import SimpleNamespace

        sys_msg = SimpleNamespace(type="system", content="SYS", additional_kwargs={})
        tool_msg = SimpleNamespace(
            type="tool", content="T" * 3000, tool_call_id="c1", additional_kwargs={}
        )
        msgs = [
            sys_msg,
            SimpleNamespace(
                type="ai",
                content="A",
                tool_calls=[{"id": "c1"}],
                additional_kwargs={},
            ),
            tool_msg,
        ]
        compact_messages(msgs, tail_turns=0)
        assert sys_msg.content == "SYS"
        assert tool_msg.content == "T" * 3000


class TestSummaryTemplate:
    """B4 判据 2：摘要模板 Objective/Work State/Next Move 三段。"""

    def test_summary_template_three_sections(self):
        from RxyCode.RxyCode1_1_0.core.compaction import build_summary_message

        summary = build_summary_message(
            objective="Fix bug X",
            work_state="Read files, root-caused to dict KeyError",
            next_move="Apply fix and run tests",
        )
        assert "Objective" in summary
        assert "Work State" in summary
        assert "Next Move" in summary

    def test_summary_carries_task_state(self):
        """摘要必须携带任务状态（调研报告共性 5，防返工）。"""
        from RxyCode.RxyCode1_1_0.core.compaction import build_summary_message

        summary = build_summary_message(
            objective="Refactor module",
            work_state="Extracted helper functions",
            next_move="Update callers",
        )
        assert "Refactor module" in summary
        assert "Extracted helper functions" in summary
        assert "Update callers" in summary


class TestTailRetention:
    """B4 判据 3：尾部保留 25% + system 不裁剪。"""

    def test_system_never_pruned(self):
        """system 永不裁剪（调研报告共性 7）。"""
        from RxyCode.RxyCode1_1_0.core.compaction import compact_messages

        from types import SimpleNamespace

        msgs = [
            SimpleNamespace(type="system", content="SYS_KEEP", additional_kwargs={}),
            SimpleNamespace(type="human", content="U", additional_kwargs={}),
            SimpleNamespace(type="ai", content="A" * 3000, additional_kwargs={}),
        ]
        out = compact_messages(msgs, tail_turns=0)
        # system 仍在头部且内容未变
        assert out[0].content == "SYS_KEEP"
        assert out[0].type == "system"

    def test_non_first_system_never_pruned(self):
        """luna 阻断项：非首位 system 消息也永不裁剪（保留在输出中）。"""
        from RxyCode.RxyCode1_1_0.core.compaction import compact_messages

        from types import SimpleNamespace

        msgs = [
            SimpleNamespace(type="system", content="SYS_1", additional_kwargs={}),
            SimpleNamespace(type="human", content="U", additional_kwargs={}),
            SimpleNamespace(type="system", content="MID_SYSTEM", additional_kwargs={}),
            SimpleNamespace(type="ai", content="A" * 3000, additional_kwargs={}),
        ]
        out = compact_messages(msgs, tail_turns=0)
        contents = [getattr(m, "content", "") for m in out]
        # 所有 system 都保留（永不裁剪）
        assert "SYS_1" in contents
        assert "MID_SYSTEM" in contents

    def test_legitimate_system_with_objective_not_deleted(self):
        """luna 阻断项 R5-1：正文含 Objective 的合法 system 不被误删。"""
        from RxyCode.RxyCode1_1_0.core.compaction import compact_messages

        from types import SimpleNamespace

        msgs = [
            SimpleNamespace(type="system", content="SYS", additional_kwargs={}),
            SimpleNamespace(
                type="system",
                content="Objective: legit system instruction",
                additional_kwargs={},
            ),
            SimpleNamespace(type="human", content="U", additional_kwargs={}),
            SimpleNamespace(type="ai", content="A" * 3000, additional_kwargs={}),
        ]
        out = compact_messages(msgs, tail_turns=0)
        contents = [getattr(m, "content", "") for m in out]
        assert "Objective: legit system instruction" in contents

    def test_system_not_promoted_when_first_message_not_system(self):
        """luna 阻断项 1：首条非 system 时，后续 system 不被提升到头部。"""
        from RxyCode.RxyCode1_1_0.core.compaction import compact_messages

        from types import SimpleNamespace

        msgs = [
            SimpleNamespace(type="human", content="U", additional_kwargs={}),
            SimpleNamespace(type="system", content="LATE_SYSTEM", additional_kwargs={}),
            SimpleNamespace(type="ai", content="A" * 3000, additional_kwargs={}),
        ]
        out = compact_messages(msgs, tail_turns=0)
        contents = [getattr(m, "content", "") for m in out]
        assert "LATE_SYSTEM" in contents

    def test_no_fold_still_single_summary(self):
        """luna 阻断项 R5-2：fold_msgs 为空路径也不产生重复摘要。"""
        from RxyCode.RxyCode1_1_0.core.compaction import compact_messages

        from types import SimpleNamespace

        # 含两个已有摘要标记的消息链 + 无可折叠内容
        msgs = [
            SimpleNamespace(type="system", content="SYS", additional_kwargs={}),
            SimpleNamespace(
                type="system",
                content="<summary>old</summary>",
                additional_kwargs={"is_compaction_summary": True},
            ),
            SimpleNamespace(type="human", content="U", additional_kwargs={}),
            SimpleNamespace(
                type="system",
                content="<summary>old2</summary>",
                additional_kwargs={"is_compaction_summary": True},
            ),
        ]
        out = compact_messages(msgs, tail_turns=2)
        summary_count = sum(
            1
            for m in out
            if (getattr(m, "additional_kwargs", None) or {}).get(
                "is_compaction_summary"
            )
        )
        assert summary_count <= 1

    def test_only_summary_messages_single_summary(self):
        """luna 阻断项 R6-1：仅首位 system + 多个已标记摘要时去重。"""
        from RxyCode.RxyCode1_1_0.core.compaction import compact_messages

        from types import SimpleNamespace

        msgs = [
            SimpleNamespace(type="system", content="SYS", additional_kwargs={}),
            SimpleNamespace(
                type="system",
                content="<summary>A</summary>",
                additional_kwargs={"is_compaction_summary": True},
            ),
            SimpleNamespace(
                type="system",
                content="<summary>B</summary>",
                additional_kwargs={"is_compaction_summary": True},
            ),
        ]
        out = compact_messages(msgs, tail_turns=2)
        summary_count = sum(
            1
            for m in out
            if (getattr(m, "additional_kwargs", None) or {}).get(
                "is_compaction_summary"
            )
        )
        # 旧摘要被去重且无新折叠内容：0 或 1 个摘要都合法（关键是不重复）
        assert summary_count <= 1
        assert out[0].content == "SYS"

    def test_repeat_compaction_preserves_summary_state(self):
        """luna 阻断项 R7-1：重复压缩不丢失既有摘要状态（防返工）。"""
        from RxyCode.RxyCode1_1_0.core.compaction import compact_messages

        from types import SimpleNamespace

        msgs = [
            SimpleNamespace(type="system", content="SYS", additional_kwargs={}),
            SimpleNamespace(type="human", content="U0", additional_kwargs={}),
            SimpleNamespace(type="ai", content="A" * 3000, additional_kwargs={}),
        ]
        # 第一次压缩
        out1 = compact_messages(msgs, tail_turns=0)
        summary1 = next(
            m
            for m in out1
            if (getattr(m, "additional_kwargs", None) or {}).get(
                "is_compaction_summary"
            )
        )
        assert "U0" in summary1.content  # 摘要携带任务状态
        # 第二次压缩（重复）
        out2 = compact_messages(out1, tail_turns=0)
        summary2 = next(
            m
            for m in out2
            if (getattr(m, "additional_kwargs", None) or {}).get(
                "is_compaction_summary"
            )
        )
        # 旧摘要状态被保留（U0 仍在摘要中）——不丢失
        assert "U0" in summary2.content

    def test_summary_uses_real_system_message(self):
        """luna 阻断项 R6-2：摘要使用正式 LangChain SystemMessage。"""
        from langchain_core.messages import SystemMessage

        from RxyCode.RxyCode1_1_0.core.compaction import compact_messages

        from types import SimpleNamespace

        msgs = [
            SimpleNamespace(type="system", content="SYS", additional_kwargs={}),
            SimpleNamespace(type="human", content="U", additional_kwargs={}),
            SimpleNamespace(type="ai", content="A" * 3000, additional_kwargs={}),
        ]
        out = compact_messages(msgs, tail_turns=0)
        summary = next(
            m
            for m in out
            if (getattr(m, "additional_kwargs", None) or {}).get(
                "is_compaction_summary"
            )
        )
        assert isinstance(summary, SystemMessage)
        # SystemMessage 可被 LangChain 序列化
        serialized = summary.model_dump() if hasattr(summary, "model_dump") else None
        assert serialized is None or isinstance(serialized, dict)

    def test_non_first_system_relative_order_kept(self):
        """luna 阻断项 R7-2：非首位 system 相对保留内容顺序不变。

        用短消息避免触发 25% 预算循环（预算循环会按设计折叠长内容）。
        """
        from RxyCode.RxyCode1_1_0.core.compaction import compact_messages

        from types import SimpleNamespace

        msgs = [
            SimpleNamespace(type="system", content="SYS", additional_kwargs={}),
            SimpleNamespace(
                type="system", content="MID_SYSTEM", additional_kwargs={}
            ),
            SimpleNamespace(type="human", content="U", additional_kwargs={}),
            SimpleNamespace(type="ai", content="A", additional_kwargs={}),
        ]
        out = compact_messages(msgs, tail_turns=1)
        # MID_SYSTEM 在 U 之前（相对顺序：原序 MID_SYSTEM → U）
        idx_mid = next(
            i for i, m in enumerate(out) if getattr(m, "content", "") == "MID_SYSTEM"
        )
        idx_u = next(
            i for i, m in enumerate(out) if getattr(m, "content", "") == "U"
        )
        assert idx_mid < idx_u

    def test_non_first_system_order_after_real_fold(self):
        """luna 阻断项 R8-1：真实折叠后 MID_SYSTEM 不被摘要前移。"""
        from RxyCode.RxyCode1_1_0.core.compaction import compact_messages

        from types import SimpleNamespace

        msgs = [
            SimpleNamespace(type="system", content="SYS", additional_kwargs={}),
            SimpleNamespace(
                type="system", content="MID_SYSTEM", additional_kwargs={}
            ),
            SimpleNamespace(type="human", content="U0", additional_kwargs={}),
            SimpleNamespace(type="ai", content="A" * 3000, additional_kwargs={}),
        ]
        out = compact_messages(msgs, tail_turns=0)
        idx_mid = next(
            i for i, m in enumerate(out) if getattr(m, "content", "") == "MID_SYSTEM"
        )
        # MID_SYSTEM 在摘要之前（原序 MID_SYSTEM 在 U0 前，U0 被折叠进摘要）
        idx_summary = next(
            i
            for i, m in enumerate(out)
            if (getattr(m, "additional_kwargs", None) or {}).get(
                "is_compaction_summary"
            )
        )
        assert idx_mid < idx_summary

    def test_summary_state_kept_when_no_fold_content(self):
        """luna 阻断项 R8-2：body 非空但无可折叠内容时摘要状态保留。"""
        from RxyCode.RxyCode1_1_0.core.compaction import compact_messages

        from types import SimpleNamespace

        msgs = [
            SimpleNamespace(type="system", content="SYS", additional_kwargs={}),
            SimpleNamespace(
                type="system",
                content="<summary>Objective: keep me</summary>",
                additional_kwargs={"is_compaction_summary": True},
            ),
            SimpleNamespace(type="human", content="U1", additional_kwargs={}),
        ]
        out = compact_messages(msgs, tail_turns=1)
        contents = [getattr(m, "content", "") for m in out]
        assert any("keep me" in c for c in contents)
        assert "U1" in contents

    def test_first_message_summary_not_duplicated(self):
        """luna 阻断项 R8-3：首条是摘要标记消息时不产生重复摘要。"""
        from RxyCode.RxyCode1_1_0.core.compaction import compact_messages

        from types import SimpleNamespace

        msgs = [
            SimpleNamespace(
                type="system",
                content="<summary>Objective: first</summary>",
                additional_kwargs={"is_compaction_summary": True},
            ),
            SimpleNamespace(type="human", content="U0", additional_kwargs={}),
            SimpleNamespace(type="ai", content="A" * 3000, additional_kwargs={}),
        ]
        out = compact_messages(msgs, tail_turns=0)
        summary_count = sum(
            1
            for m in out
            if (getattr(m, "additional_kwargs", None) or {}).get(
                "is_compaction_summary"
            )
        )
        assert summary_count == 1

    def test_tail_retained(self):
        """尾部保留最近消息（tail_turns 参数控制）。"""
        from RxyCode.RxyCode1_1_0.core.compaction import compact_messages

        from types import SimpleNamespace

        msgs = [
            SimpleNamespace(type="system", content="SYS", additional_kwargs={}),
            SimpleNamespace(type="human", content="U0", additional_kwargs={}),
            SimpleNamespace(type="ai", content="A" * 3000, additional_kwargs={}),
            SimpleNamespace(type="human", content="U1", additional_kwargs={}),
        ]
        out = compact_messages(msgs, tail_turns=1)
        # 摘要消息存在
        contents = [getattr(m, "content", "") for m in out]
        assert any("Objective" in c for c in contents)
        # 最近 1 轮（U1）保留
        assert contents[-1] == "U1"

    def test_tail_budget_25_percent_enforced(self):
        """luna 阻断项：尾部保留受 preserveRecentBudget 25% 预算约束。"""
        from RxyCode.RxyCode1_1_0.core.compaction import compact_messages

        from types import SimpleNamespace

        # 大量长消息：尾部预算 25% 下无法全保留
        msgs = [
            SimpleNamespace(type="system", content="SYS", additional_kwargs={}),
        ]
        for i in range(8):
            msgs.append(
                SimpleNamespace(type="human", content=f"U{i}" + "X" * 500, additional_kwargs={})
            )
            msgs.append(
                SimpleNamespace(type="ai", content="A" * 500, additional_kwargs={})
            )
        out, tel = compact_messages(msgs, tail_turns=2, return_telemetry=True)
        # 压缩后体积必须显著小于压缩前（预算收敛），且不超过 25% + 摘要/summary 开销
        assert tel["compacted"] is True
        assert tel["tokens_after"] < tel["tokens_before"] * 0.6
        # 摘要消息存在（压缩确实发生了）
        contents = [getattr(m, "content", "") for m in out]
        assert any("Objective" in c for c in contents)

    def test_only_one_summary_after_budget_loop(self):
        """luna 阻断项 B4-1：预算收紧后最多一个摘要（无重复）。"""
        from RxyCode.RxyCode1_1_0.core.compaction import compact_messages

        from types import SimpleNamespace

        msgs = [
            SimpleNamespace(type="system", content="SYS", additional_kwargs={}),
        ]
        for i in range(8):
            msgs.append(
                SimpleNamespace(type="human", content=f"U{i}" + "X" * 500, additional_kwargs={})
            )
            msgs.append(
                SimpleNamespace(type="ai", content="A" * 500, additional_kwargs={})
            )
        out, _tel = compact_messages(msgs, tail_turns=2, return_telemetry=True)
        summary_count = sum(
            1 for m in out if "Objective" in (getattr(m, "content", "") or "")
        )
        assert summary_count == 1, f"expected 1 summary, got {summary_count}"


class TestToolPairIntegrity:
    """B4 判据 5：压缩不拆散 assistant↔tool 配对。"""

    def test_tool_pair_never_split(self):
        """压缩后无孤儿 tool_call（API 400 防线）。"""
        from RxyCode.RxyCode1_1_0.core.cache_policy import tool_pair_integrity
        from RxyCode.RxyCode1_1_0.core.compaction import compact_messages

        from types import SimpleNamespace

        msgs = [
            SimpleNamespace(type="system", content="SYS", additional_kwargs={}),
            SimpleNamespace(type="human", content="U", additional_kwargs={}),
            SimpleNamespace(
                type="ai",
                content="checking",
                tool_calls=[{"id": "c1"}, {"id": "c2"}],
                additional_kwargs={},
            ),
            SimpleNamespace(
                type="tool", content="R1", tool_call_id="c1", additional_kwargs={}
            ),
            SimpleNamespace(
                type="tool", content="R2" * 2000, tool_call_id="c2", additional_kwargs={}
            ),
            SimpleNamespace(type="ai", content="done", tool_calls=[], additional_kwargs={}),
        ]
        out = compact_messages(msgs, tail_turns=1)
        assert tool_pair_integrity(out) is True

    def test_compaction_without_tool_calls(self):
        """无工具消息的会话压缩不报错。"""
        from RxyCode.RxyCode1_1_0.core.compaction import compact_messages

        from types import SimpleNamespace

        msgs = [
            SimpleNamespace(type="system", content="SYS", additional_kwargs={}),
            SimpleNamespace(type="human", content="U0", additional_kwargs={}),
            SimpleNamespace(type="ai", content="A" * 2000, additional_kwargs={}),
            SimpleNamespace(type="human", content="U1", additional_kwargs={}),
        ]
        out = compact_messages(msgs, tail_turns=1)
        assert len(out) >= 3


class TestCompactionTelemetry:
    """B4 判据 4：压缩遥测（tokens_before/after 审计）。"""

    def test_compaction_records_tokens_before_after(self):
        """压缩事件记录 tokens_before/after（遥测，原则 8；chars/3 口径）。"""
        from RxyCode.RxyCode1_1_0.core.compaction import compact_messages

        from types import SimpleNamespace

        msgs = [
            SimpleNamespace(type="system", content="SYS", additional_kwargs={}),
            SimpleNamespace(type="human", content="U0", additional_kwargs={}),
            SimpleNamespace(type="ai", content="A" * 5000, additional_kwargs={}),
        ]
        tokens_before = sum(
            len(m.content or "") // 3 for m in msgs
        )
        out, telemetry = compact_messages(msgs, tail_turns=0, return_telemetry=True)
        tokens_after = sum(
            len(m.content or "") // 3 for m in out
        )
        assert telemetry["tokens_before"] == tokens_before
        assert telemetry["tokens_after"] == tokens_after
        assert tokens_after < tokens_before  # 压缩应减少体积
