from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from runcrew.domain.activity import (
    ActivityDetail,
    ActivitySummary,
    Lap,
    SourceProvider,
    SourceRef,
    SportType,
)
from runcrew.domain.chat import ChatAnswer, ChatTurnUsage
from runcrew.policies.chat import DeepSeekGroundedChatPolicy
from runcrew.policies.deepseek import DeepSeekPolicyConfig, DeepSeekPolicyError
from runcrew.services.chat import ChatService
from runcrew.storage.database import Database
from runcrew.storage.models import ChatConversationRecord
from runcrew.storage.repositories import ActivityRepository
from runcrew.web import DemoApplication, DemoDashboardService


ANCHOR = datetime(2026, 8, 8, 8, tzinfo=timezone.utc)


def _activity(identifier: str, *, days_before: int, detail: bool = False):
    common = {
        "id": identifier,
        "source_ref": SourceRef(
            provider=SourceProvider.FIXTURE,
            external_id=f"secret-provider-{identifier}",
            fetched_at=ANCHOR,
            raw_payload_hash=f"hash-{identifier}",
        ),
        "sport_type": SportType.RUN,
        "started_at": ANCHOR - timedelta(days=days_before),
        "duration_seconds": 3600,
        "distance_meters": 10_000,
        "average_pace_seconds_per_km": 360,
        "average_heart_rate": 150,
        "training_load": 50,
        "title": "周末十公里",
    }
    if not detail:
        return ActivitySummary(**common)
    return ActivityDetail(
        **common,
        laps=[
            Lap(
                index=index,
                duration_seconds=pace,
                distance_meters=1000,
                average_pace_seconds_per_km=pace,
            )
            for index, pace in enumerate((359, 360, 361, 360), start=1)
        ],
    )


def _database(tmp_path: Path) -> tuple[Path, Database]:
    path = tmp_path / "chat.db"
    database = Database(f"sqlite:///{path.as_posix()}")
    database.create_schema()
    with database.session() as session:
        repository = ActivityRepository(session)
        repository.upsert(_activity("target", days_before=0, detail=True))
        repository.upsert(_activity("history", days_before=8))
        session.commit()
    return path, database


def test_chat_service_persists_continuous_grounded_conversation(tmp_path: Path) -> None:
    database_path, database = _database(tmp_path)
    service = ChatService(database_path=database_path)

    bootstrap = service.bootstrap()
    assert len(bootstrap.activities) == 2
    assert "secret-provider" not in bootstrap.model_dump_json()
    conversation = service.create_conversation(
        activity_id="target",
        title="聊聊周末十公里",
    )

    first = asyncio.run(
        service.send_message(
            conversation_id=conversation.id,
            content="这次训练完成得怎么样？",
        )
    )
    second = asyncio.run(
        service.send_message(
            conversation_id=conversation.id,
            content="还缺哪些数据？",
        )
    )

    assert len(first.conversation.messages) == 2
    assert len(second.conversation.messages) == 4
    assert first.review_trace
    assert first.answer.evidence_refs == ["training_completion"]
    assert first.answer.response_mode == "data_analysis"
    assert second.answer.missing_data
    assert second.context_message_count == 2
    assert second.conversation.messages[1].response_mode == "data_analysis"
    assert second.conversation.messages[1].grounded_claims
    assert all(item.model != "deepseek-v4-flash" for item in second.conversation.messages)
    with database.session() as session:
        record = session.get(ChatConversationRecord, conversation.id)
        assert record is not None
        assert record.review_snapshot_json is not None
        assert record.review_input_hash == first.conversation.review_input_hash


class _CapturingPolicy:
    def __init__(self) -> None:
        self.histories: list[list[str]] = []

    async def answer(self, *, question, activity_context, review, history):
        self.histories.append([item.content for item in history])
        return (
            ChatAnswer(
                answer=f"已基于证据回答：{question}",
                evidence_refs=["training_anomaly"],
                confidence="high",
            ),
            ChatTurnUsage(
                provider="deepseek",
                model="deepseek-test",
                total_tokens=42,
                estimated_cost_usd=0.00001,
            ),
        )


def test_chat_api_creates_conversation_and_executes_paid_mode_only_when_requested(
    tmp_path: Path,
) -> None:
    database_path, _ = _database(tmp_path)
    policy = _CapturingPolicy()
    chat_service = ChatService(
        database_path=database_path,
        deepseek_policy_factory=lambda: policy,
    )
    application = DemoApplication(
        DemoDashboardService(
            database_path=database_path,
            evaluation_directory=tmp_path / "evals",
        ),
        chat_service,
    )

    page = application.handle("GET", "/")
    engineering = application.handle("GET", "/engineering")
    assert "连续对话" in page.body.decode("utf-8")
    assert "只读" in engineering.body.decode("utf-8")

    created = application.handle(
        "POST",
        "/api/chat/conversations",
        json.dumps({"activity_id": "target", "title": "测试对话"}).encode(),
    )
    assert created.status == 201
    conversation_id = json.loads(created.body)["id"]
    turn = application.handle(
        "POST",
        f"/api/chat/conversations/{conversation_id}/messages",
        json.dumps(
            {"content": "为什么配速稳定？", "use_deepseek": True},
            ensure_ascii=False,
        ).encode("utf-8"),
    )
    payload = json.loads(turn.body)

    assert turn.status == 200
    assert payload["usage"]["model"] == "deepseek-test"
    assert payload["answer"]["evidence_refs"] == ["training_anomaly"]
    assert policy.histories == [[]]
    assert "secret-provider" not in turn.body.decode("utf-8")


class _DeepSeekTransport:
    def __init__(self) -> None:
        self.payload = None

    async def complete(self, payload):
        self.payload = payload
        return {
            "model": "deepseek-v4-flash",
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {
                        "content": json.dumps(
                            {
                                "answer": "分圈波动处于正常范围。",
                                "response_mode": "data_analysis",
                                "grounded_claims": [
                                    {
                                        "statement": "分圈波动处于正常范围",
                                        "kind": "observed_fact",
                                        "evidence_refs": ["training_anomaly"],
                                    }
                                ],
                                "evidence_refs": ["training_anomaly"],
                                "confidence": "high",
                                "missing_data": [],
                                "follow_up_suggestions": ["对比最近四周"],
                            },
                            ensure_ascii=False,
                        )
                    },
                }
            ],
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 30,
                "total_tokens": 130,
            },
        }


def test_deepseek_chat_policy_uses_json_contract_and_bounded_context(tmp_path: Path) -> None:
    database_path, _ = _database(tmp_path)
    service = ChatService(database_path=database_path)
    conversation = service.create_conversation(activity_id="target")
    offline = asyncio.run(
        service.send_message(conversation_id=conversation.id, content="先复盘一下")
    )
    review_record_db = Database(f"sqlite:///{database_path.as_posix()}")
    with review_record_db.session() as session:
        record = session.get(ChatConversationRecord, conversation.id)
        from runcrew.domain.training_review import TrainingReviewResult

        review = TrainingReviewResult.model_validate_json(record.review_snapshot_json)

    transport = _DeepSeekTransport()
    policy = DeepSeekGroundedChatPolicy(
        DeepSeekPolicyConfig(
            api_key=SecretStr("test-key"),
            max_api_retries=0,
        ),
        transport=transport,
    )
    answer, usage = asyncio.run(
        policy.answer(
            question="为什么？",
            activity_context={"id": "target", "distance_km": 10},
            review=review,
            history=offline.conversation.messages * 6,
        )
    )

    assert answer.evidence_refs == ["training_anomaly"]
    assert answer.grounded_claims[0].kind == "observed_fact"
    assert usage.total_tokens == 130
    assert transport.payload["response_format"] == {"type": "json_object"}
    assert "general_knowledge" in transport.payload["messages"][0]["content"]
    sent_context = json.loads(transport.payload["messages"][1]["content"])
    assert len(sent_context["conversation_history"]) == 8
    assert "secret-provider" not in transport.payload["messages"][1]["content"]
    with pytest.raises(ValidationError, match="医疗诊断"):
        ChatAnswer(
            answer="你诊断为某种伤病。",
            evidence_refs=[],
            confidence="low",
        )
    with pytest.raises(ValidationError, match="至少需要一条"):
        ChatAnswer(
            answer="没有任何个人数据依据，却声称在分析个人表现。",
            response_mode="data_analysis",
            confidence="high",
        )


class _InvalidDeepSeekTransport:
    async def complete(self, payload):
        del payload
        return {
            "model": "deepseek-v4-flash",
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {"content": '{"answer":"结构不完整"}'},
                }
            ],
            "usage": {
                "prompt_tokens": 80,
                "completion_tokens": 10,
                "total_tokens": 90,
            },
        }


def test_failed_deepseek_chat_response_still_records_usage(tmp_path: Path) -> None:
    database_path, _ = _database(tmp_path)
    service = ChatService(database_path=database_path)
    conversation = service.create_conversation(activity_id="target")
    offline = asyncio.run(
        service.send_message(conversation_id=conversation.id, content="先复盘一下")
    )
    database = Database(f"sqlite:///{database_path.as_posix()}")
    with database.session() as session:
        record = session.get(ChatConversationRecord, conversation.id)
        from runcrew.domain.training_review import TrainingReviewResult

        review = TrainingReviewResult.model_validate_json(record.review_snapshot_json)
    policy = DeepSeekGroundedChatPolicy(
        DeepSeekPolicyConfig(
            api_key=SecretStr("test-key"),
            max_api_retries=0,
        ),
        transport=_InvalidDeepSeekTransport(),
    )

    with pytest.raises(DeepSeekPolicyError):
        asyncio.run(
            policy.answer(
                question="继续",
                activity_context={"id": "target"},
                review=review,
                history=offline.conversation.messages,
            )
        )

    usage = policy.consume_last_usage()
    assert usage.total_tokens == 90
    assert usage.estimated_cost_usd > 0
