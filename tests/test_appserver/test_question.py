"""Appserver stdio question broker — same shape as JSON-RPC approval."""

from __future__ import annotations

import asyncio

import pytest

from appserver.question import PipeQuestionBroker
from appserver.runtime import bind_prompt_context, reset_prompt_context
from core.question import QuestionOption, QuestionRequest


@pytest.mark.asyncio
async def test_pipe_question_round_trip():
    async def send_request(method: str, params: dict) -> dict:
        assert method == "question/request"
        assert params["session_id"] == "s1"
        assert params["question"] == "哪个环节慢？"
        assert params["input_type"] == "choice"
        return {"question_id": params["question_id"], "answer": "response"}

    broker = PipeQuestionBroker(send_request, timeout=5.0)
    tokens = bind_prompt_context("s1", None)
    try:
        response = await broker.ask(
            QuestionRequest(
                question="哪个环节慢？",
                header="确认问题",
                options=[
                    QuestionOption(label="回复慢", value="response"),
                    QuestionOption(label="任务慢", value="task"),
                ],
            )
        )
    finally:
        reset_prompt_context(tokens)
    assert response.answer == "response"
    assert response.cancelled is False
    assert response.unavailable is False


@pytest.mark.asyncio
async def test_pipe_question_timeout_marks_timed_out():
    async def hang(_method: str, _params: dict) -> dict:
        await asyncio.sleep(0.2)
        return {"answer": "late"}

    broker = PipeQuestionBroker(hang, timeout=0.05)
    response = await broker.ask(QuestionRequest(question="还在吗？"))
    assert response.timed_out is True
    assert response.answer is None


@pytest.mark.asyncio
async def test_pipe_question_send_failure_marks_unavailable():
    async def boom(_method: str, _params: dict) -> dict:
        raise RuntimeError("client gone")

    broker = PipeQuestionBroker(boom, timeout=5.0)
    response = await broker.ask(QuestionRequest(question="还在吗？"))
    assert response.unavailable is True
    assert response.answer is None
