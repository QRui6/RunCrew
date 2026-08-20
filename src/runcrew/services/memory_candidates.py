from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone

from runcrew.domain.memory import (
    AthletePreferenceSubmission,
    MemoryCandidate,
    MemoryCandidateDecisionRequest,
    MemoryCandidateDecisionResult,
)
from runcrew.services.athlete_memory import confirm_athlete_preference
from runcrew.storage.repositories import (
    AthletePreferenceRepository,
    ChatRepository,
    MemoryCandidateRepository,
)


CANDIDATE_TTL = timedelta(days=7)
WEEKDAY_PATTERNS = {
    "mon": re.compile(r"(?:星期|周|礼拜)(?:一|1)"),
    "tue": re.compile(r"(?:星期|周|礼拜)(?:二|2)"),
    "wed": re.compile(r"(?:星期|周|礼拜)(?:三|3)"),
    "thu": re.compile(r"(?:星期|周|礼拜)(?:四|4)"),
    "fri": re.compile(r"(?:星期|周|礼拜)(?:五|5)"),
    "sat": re.compile(r"(?:星期|周|礼拜)(?:六|6)"),
    "sun": re.compile(r"(?:星期|周|礼拜)(?:日|天|七|7)"),
}
STABLE_MARKERS = (
    "以后",
    "今后",
    "长期",
    "平时",
    "通常",
    "一般",
    "固定",
    "默认",
    "习惯",
    "偏好",
    "更喜欢",
    "优先",
    "尽量",
    "总是",
    "希望",
)
HIGH_CONFIDENCE_MARKERS = (
    "固定",
    "默认",
    "习惯",
    "偏好",
    "更喜欢",
    "优先",
    "总是",
    "以后都",
)
TEMPORARY_MARKERS = ("这周", "本周", "下周", "这次", "今天", "明天", "后天")
NEGATION_MARKERS = ("不想", "不要", "不希望", "不再", "别在", "避免")


class MemoryCandidateError(ValueError):
    pass


def extract_memory_candidate(
    content: str,
    *,
    conversation_id: str,
    source_message_id: int,
    now: datetime | None = None,
) -> MemoryCandidate | None:
    """高精度提取 v1 支持的长期长跑星期候选；不写正式 Memory。"""

    created_at = now or datetime.now(timezone.utc)
    _require_timezone(created_at)
    text = re.sub(r"\s+", "", content.strip())
    if not text or not any(term in text for term in ("长跑", "长距离")):
        return None
    if any(marker in text for marker in TEMPORARY_MARKERS):
        return None
    if any(marker in text for marker in NEGATION_MARKERS):
        return None
    if not any(marker in text for marker in STABLE_MARKERS):
        return None
    weekdays = [key for key, pattern in WEEKDAY_PATTERNS.items() if pattern.search(text)]
    if len(weekdays) != 1:
        return None
    confidence = (
        "high"
        if any(marker in text for marker in HIGH_CONFIDENCE_MARKERS)
        else "medium"
    )
    candidate_id = _new_candidate_id()
    expires_at = created_at + CANDIDATE_TTL
    source_text_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    candidate_hash = _candidate_hash(
        candidate_id=candidate_id,
        conversation_id=conversation_id,
        source_message_id=source_message_id,
        source_text_hash=source_text_hash,
        proposed_value=weekdays[0],
        confidence=confidence,
        created_at=created_at,
        expires_at=expires_at,
    )
    return MemoryCandidate(
        id=candidate_id,
        conversation_id=conversation_id,
        source_message_id=source_message_id,
        source_text_hash=source_text_hash,
        key="preferred_long_run_weekday",
        proposed_value=weekdays[0],
        confidence=confidence,
        confidence_basis=(
            "explicit_stable_preference"
            if confidence == "high"
            else "stable_preference_language"
        ),
        candidate_hash=candidate_hash,
        created_at=created_at,
        expires_at=expires_at,
    )


def propose_chat_memory_candidate(
    content: str,
    *,
    conversation_id: str,
    source_message_id: int,
    candidates: MemoryCandidateRepository,
    now: datetime | None = None,
) -> MemoryCandidate | None:
    created_at = now or datetime.now(timezone.utc)
    extracted = extract_memory_candidate(
        content,
        conversation_id=conversation_id,
        source_message_id=source_message_id,
        now=created_at,
    )
    if extracted is None:
        return None
    existing_source = candidates.for_source_message(
        source_message_id, extracted.key
    )
    if existing_source is not None:
        return existing_source
    pending = candidates.pending_for_key(extracted.key)
    for item in pending:
        if created_at >= item.expires_at:
            candidates.save(
                item.model_copy(update={"status": "expired", "decided_at": created_at})
            )
    active_pending = [item for item in pending if created_at < item.expires_at]
    superseded_id = active_pending[0].id if active_pending else None
    for item in active_pending:
        candidates.save(
            item.model_copy(update={"status": "superseded", "decided_at": created_at})
        )
    extracted = extracted.model_copy(
        update={"supersedes_candidate_id": superseded_id}
    )
    candidates.save(extracted)
    return extracted


def decide_memory_candidate(
    candidate_id: str,
    request: MemoryCandidateDecisionRequest,
    *,
    candidates: MemoryCandidateRepository,
    preferences: AthletePreferenceRepository,
    chats: ChatRepository,
    now: datetime | None = None,
) -> MemoryCandidateDecisionResult:
    decided_at = now or datetime.now(timezone.utc)
    _require_timezone(decided_at)
    candidate = candidates.get(candidate_id)
    if candidate is None:
        raise MemoryCandidateError("记忆候选不存在。")
    integrity_hash = _candidate_hash(
        candidate_id=candidate.id,
        conversation_id=candidate.conversation_id,
        source_message_id=candidate.source_message_id,
        source_text_hash=candidate.source_text_hash,
        proposed_value=candidate.proposed_value,
        confidence=candidate.confidence,
        created_at=candidate.created_at,
        expires_at=candidate.expires_at,
    )
    if integrity_hash != candidate.candidate_hash:
        raise MemoryCandidateError("记忆候选完整性校验失败，不能写入正式记忆。")
    source_message = chats.get_message_record(candidate.source_message_id)
    if (
        source_message is None
        or source_message.conversation_id != candidate.conversation_id
        or source_message.role != "user"
        or hashlib.sha256(source_message.content.encode("utf-8")).hexdigest()
        != candidate.source_text_hash
    ):
        raise MemoryCandidateError("候选引用的原始用户消息已变化，不能写入正式记忆。")
    if candidate.candidate_hash != request.expected_candidate_hash:
        raise MemoryCandidateError("记忆候选已经变化，请刷新后重新确认。")
    if candidate.status == "confirmed" and request.decision == "confirm":
        preference = (
            preferences.get(candidate.preference_id)
            if candidate.preference_id is not None
            else None
        )
        if preference is None:
            raise MemoryCandidateError("已确认候选缺少正式偏好记录。")
        return MemoryCandidateDecisionResult(
            outcome="already_decided",
            candidate=candidate,
            preference=preference,
        )
    if candidate.status == "rejected" and request.decision == "reject":
        return MemoryCandidateDecisionResult(
            outcome="already_decided", candidate=candidate
        )
    if candidate.status != "pending":
        raise MemoryCandidateError("该记忆候选已经结束，不能再次修改决定。")
    if decided_at >= candidate.expires_at:
        expired = candidate.model_copy(
            update={"status": "expired", "decided_at": decided_at}
        )
        candidates.save(expired)
        raise MemoryCandidateError("记忆候选已经过期，请在新消息中重新表达偏好。")
    if request.decision == "reject":
        rejected = candidate.model_copy(
            update={"status": "rejected", "decided_at": decided_at}
        )
        candidates.save(rejected)
        return MemoryCandidateDecisionResult(outcome="rejected", candidate=rejected)
    preference = confirm_athlete_preference(
        AthletePreferenceSubmission(
            key=candidate.key,
            value=candidate.proposed_value,
            confirmed=True,
        ),
        preferences=preferences,
        source_ref=(
            f"chat-candidate:{candidate.id}:message:{candidate.source_message_id}"
        ),
        now=decided_at,
    )
    confirmed = candidate.model_copy(
        update={
            "status": "confirmed",
            "preference_id": preference.id,
            "decided_at": decided_at,
        }
    )
    candidates.save(confirmed)
    return MemoryCandidateDecisionResult(
        outcome="confirmed", candidate=confirmed, preference=preference
    )


def expire_pending_memory_candidates(
    *,
    candidates: MemoryCandidateRepository,
    now: datetime | None = None,
    conversation_id: str | None = None,
) -> int:
    checked_at = now or datetime.now(timezone.utc)
    _require_timezone(checked_at)
    expired_count = 0
    for candidate in candidates.list(
        conversation_id=conversation_id,
        include_resolved=False,
        limit=100,
    ):
        if checked_at >= candidate.expires_at:
            candidates.save(
                candidate.model_copy(
                    update={"status": "expired", "decided_at": checked_at}
                )
            )
            expired_count += 1
    return expired_count


def _candidate_hash(**values: object) -> str:
    payload = {
        "schema_version": "memory-candidate/1.0",
        "extraction_rule_version": "memory-candidate-rules/1.0",
        "key": "preferred_long_run_weekday",
        **{
            key: value.isoformat() if isinstance(value, datetime) else value
            for key, value in values.items()
        },
    }
    serialized = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _new_candidate_id() -> str:
    from uuid import uuid4

    return str(uuid4())


def _require_timezone(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise MemoryCandidateError("记忆候选时间必须包含时区。")
