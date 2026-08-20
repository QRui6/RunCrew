from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from runcrew.domain.activity import ActivitySummary, SourceProvider, SourceRef, SportType
from runcrew.domain.chat import ChatConversation, ChatTurnResult
from runcrew.domain.memory import (
    MemoryCandidate,
    MemoryCandidateDecisionRequest,
    MemoryCandidateDecisionResult,
)
from runcrew.services.chat import ChatService, ChatServiceError
from runcrew.services.memory_candidates import extract_memory_candidate
from runcrew.storage.database import Database
from runcrew.storage.models import ChatMessageRecord, MemoryCandidateRecord
from runcrew.storage.repositories import ActivityRepository, AthletePreferenceRepository
from runcrew.web import DemoApplication, DemoDashboardService


NOW = datetime(2026, 8, 20, 8, tzinfo=timezone.utc)


def _database(tmp_path: Path) -> tuple[Path, Database]:
    path = tmp_path / "memory-candidate.db"
    database = Database(f"sqlite:///{path.as_posix()}")
    database.create_schema()
    with database.session() as session:
        ActivityRepository(session).upsert(
            ActivitySummary(
                id="activity-1",
                source_ref=SourceRef(
                    provider=SourceProvider.FIXTURE,
                    external_id="private-external-id",
                    fetched_at=NOW,
                    raw_payload_hash="fixture-hash",
                ),
                sport_type=SportType.RUN,
                started_at=NOW - timedelta(days=1),
                duration_seconds=2400,
                distance_meters=6000,
                average_pace_seconds_per_km=400,
                title="合成轻松跑",
            )
        )
        session.commit()
    return path, database


@pytest.mark.parametrize(
    ("content", "weekday", "confidence"),
    [
        ("以后长跑优先安排在周日", "sun", "high"),
        ("我平时希望星期六跑长距离", "sat", "medium"),
        ("我的长跑习惯固定在礼拜三", "wed", "high"),
    ],
)
def test_extractor_accepts_only_supported_stable_preference(
    content: str, weekday: str, confidence: str
) -> None:
    candidate = extract_memory_candidate(
        content,
        conversation_id="conversation-1",
        source_message_id=1,
        now=NOW,
    )

    assert candidate is not None
    assert candidate.proposed_value == weekday
    assert candidate.confidence == confidence
    assert candidate.status == "pending"
    assert candidate.requires_user_confirmation is True


@pytest.mark.parametrize(
    "content",
    [
        "这周日跑一次长距离",
        "下周六安排长跑",
        "我不想周日长跑",
        "周日适合长跑吗？",
        "以后周六或周日长跑都行",
        "以后周日做力量训练",
    ],
)
def test_extractor_rejects_temporary_negative_ambiguous_or_unsupported_text(
    content: str,
) -> None:
    assert (
        extract_memory_candidate(
            content,
            conversation_id="conversation-1",
            source_message_id=1,
            now=NOW,
        )
        is None
    )


def test_chat_candidate_is_pending_and_does_not_write_formal_memory(
    tmp_path: Path,
) -> None:
    path, database = _database(tmp_path)
    service = ChatService(database_path=path, clock=lambda: NOW)
    conversation = service.create_conversation(activity_id="activity-1")

    result = asyncio.run(
        service.send_message(
            conversation_id=conversation.id,
            content="以后长跑优先安排在周日",
        )
    )

    assert len(result.new_memory_candidates) == 1
    candidate = result.new_memory_candidates[0]
    assert candidate.source_message_id == result.conversation.messages[0].id
    assert result.conversation.memory_candidates == [candidate]
    with database.session() as session:
        assert AthletePreferenceRepository(session).list() == []
        record = session.get(MemoryCandidateRecord, candidate.id)
        assert record is not None
        assert "以后长跑" not in record.canonical_json
        assert "private-external-id" not in record.canonical_json


def test_confirm_candidate_replays_server_value_and_is_idempotent(tmp_path: Path) -> None:
    path, database = _database(tmp_path)
    service = ChatService(database_path=path, clock=lambda: NOW)
    conversation = service.create_conversation(activity_id="activity-1")
    turn = asyncio.run(
        service.send_message(
            conversation_id=conversation.id,
            content="今后长跑固定在星期六",
        )
    )
    candidate = turn.new_memory_candidates[0]
    request = MemoryCandidateDecisionRequest(
        decision="confirm",
        expected_candidate_hash=candidate.candidate_hash,
    )

    confirmed = service.decide_memory_candidate(candidate.id, request)
    repeated = service.decide_memory_candidate(candidate.id, request)

    assert confirmed.outcome == "confirmed"
    assert confirmed.candidate.status == "confirmed"
    assert confirmed.preference is not None
    assert confirmed.preference.value == "sat"
    assert confirmed.preference.source_ref == (
        f"chat-candidate:{candidate.id}:message:{candidate.source_message_id}"
    )
    assert repeated.outcome == "already_decided"
    assert repeated.preference == confirmed.preference
    with database.session() as session:
        assert len(AthletePreferenceRepository(session).list()) == 1


def test_reject_stale_hash_and_expired_candidate_never_write_memory(
    tmp_path: Path,
) -> None:
    path, database = _database(tmp_path)
    current = NOW
    service = ChatService(database_path=path, clock=lambda: current)
    conversation = service.create_conversation(activity_id="activity-1")
    first = asyncio.run(
        service.send_message(
            conversation_id=conversation.id,
            content="平时希望周四进行长跑",
        )
    ).new_memory_candidates[0]
    with pytest.raises(ChatServiceError, match="已经变化"):
        service.decide_memory_candidate(
            first.id,
            MemoryCandidateDecisionRequest(
                decision="confirm", expected_candidate_hash="0" * 64
            ),
        )
    rejected = service.decide_memory_candidate(
        first.id,
        MemoryCandidateDecisionRequest(
            decision="reject", expected_candidate_hash=first.candidate_hash
        ),
    )
    assert rejected.outcome == "rejected"

    second = asyncio.run(
        service.send_message(
            conversation_id=conversation.id,
            content="以后长跑优先安排在周二",
        )
    ).new_memory_candidates[0]
    current = NOW + timedelta(days=8)
    with pytest.raises(ChatServiceError, match="已经结束"):
        service.decide_memory_candidate(
            second.id,
            MemoryCandidateDecisionRequest(
                decision="confirm", expected_candidate_hash=second.candidate_hash
            ),
        )
    conversation_after = service.get_conversation(conversation.id)
    statuses = {item.id: item.status for item in conversation_after.memory_candidates}
    assert statuses[first.id] == "rejected"
    assert statuses[second.id] == "expired"
    with database.session() as session:
        assert AthletePreferenceRepository(session).list() == []


def test_new_candidate_supersedes_pending_candidate_for_same_key(tmp_path: Path) -> None:
    path, _ = _database(tmp_path)
    service = ChatService(database_path=path, clock=lambda: NOW)
    conversation = service.create_conversation(activity_id="activity-1")
    first = asyncio.run(
        service.send_message(
            conversation_id=conversation.id,
            content="以后长跑优先安排在周日",
        )
    ).new_memory_candidates[0]
    second = asyncio.run(
        service.send_message(
            conversation_id=conversation.id,
            content="今后长跑固定在周六",
        )
    ).new_memory_candidates[0]

    refreshed = service.get_conversation(conversation.id)
    values = {item.id: item for item in refreshed.memory_candidates}
    assert values[first.id].status == "superseded"
    assert values[second.id].status == "pending"
    assert values[second.id].supersedes_candidate_id == first.id


def test_confirmation_rechecks_candidate_and_source_message_integrity(
    tmp_path: Path,
) -> None:
    path, database = _database(tmp_path)
    service = ChatService(database_path=path, clock=lambda: NOW)
    conversation = service.create_conversation(activity_id="activity-1")
    first = asyncio.run(
        service.send_message(
            conversation_id=conversation.id,
            content="以后长跑优先安排在周日",
        )
    ).new_memory_candidates[0]
    with database.session() as session:
        record = session.get(MemoryCandidateRecord, first.id)
        record.canonical_json = first.model_copy(
            update={"proposed_value": "mon"}
        ).model_dump_json()
        session.commit()
    with pytest.raises(ChatServiceError, match="完整性校验失败"):
        service.decide_memory_candidate(
            first.id,
            MemoryCandidateDecisionRequest(
                decision="confirm", expected_candidate_hash=first.candidate_hash
            ),
        )

    second_conversation = service.create_conversation(activity_id="activity-1")
    second = asyncio.run(
        service.send_message(
            conversation_id=second_conversation.id,
            content="今后长跑固定在周六",
        )
    ).new_memory_candidates[0]
    with database.session() as session:
        source = session.get(ChatMessageRecord, second.source_message_id)
        source.content = "原始消息被修改"
        session.commit()
    with pytest.raises(ChatServiceError, match="原始用户消息已变化"):
        service.decide_memory_candidate(
            second.id,
            MemoryCandidateDecisionRequest(
                decision="confirm", expected_candidate_hash=second.candidate_hash
            ),
        )
    with database.session() as session:
        assert AthletePreferenceRepository(session).list() == []


def test_memory_candidate_api_and_static_ui(tmp_path: Path) -> None:
    path, _ = _database(tmp_path)
    chat = ChatService(database_path=path, clock=lambda: NOW)
    application = DemoApplication(
        DemoDashboardService(database_path=path, evaluation_directory=tmp_path / "evals"),
        chat_service=chat,
    )
    conversation = chat.create_conversation(activity_id="activity-1")
    turn = asyncio.run(
        chat.send_message(
            conversation_id=conversation.id,
            content="以后长跑优先安排在周日",
        )
    )
    candidate = turn.new_memory_candidates[0]
    tampered = application.handle(
        "POST",
        f"/api/chat/memory-candidates/{candidate.id}/decision",
        json.dumps(
            {
                "decision": "confirm",
                "expected_candidate_hash": candidate.candidate_hash,
                "proposed_value": "mon",
            }
        ).encode(),
    )
    response = application.handle(
        "POST",
        f"/api/chat/memory-candidates/{candidate.id}/decision",
        json.dumps(
            {
                "decision": "confirm",
                "expected_candidate_hash": candidate.candidate_hash,
            }
        ).encode(),
    )

    payload = MemoryCandidateDecisionResult.model_validate_json(response.body)
    html = application.handle("GET", "/").body.decode("utf-8")
    script = application.handle("GET", "/assets/chat.js").body.decode("utf-8")
    assert tampered.status == 400
    assert response.status == 200
    assert payload.outcome == "confirmed"
    assert "聊天可以提出待确认候选" in html
    assert "/api/chat/memory-candidates/" in script
    assert "expected_candidate_hash" in script
    assert "确认记住" in script
    assert "innerHTML" not in script
    schema_dir = Path("schemas/memory-candidate")
    expected = {
        "candidate.schema.json": MemoryCandidate,
        "decision-input.schema.json": MemoryCandidateDecisionRequest,
        "decision-output.schema.json": MemoryCandidateDecisionResult,
        "chat-conversation.schema.json": ChatConversation,
        "chat-turn.schema.json": ChatTurnResult,
    }
    for name, model in expected.items():
        assert json.loads((schema_dir / name).read_text("utf-8")) == (
            model.model_json_schema()
        )
