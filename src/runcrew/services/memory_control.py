from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from runcrew.domain.memory import MemoryContextBuildRequest
from runcrew.domain.memory_control import (
    AthletePreferenceControlItem,
    MemoryCandidateControlItem,
    MemoryControlCounts,
    MemoryControlOverview,
    MemoryGoalContextAudit,
    WeeklyMemoryControlItem,
)
from runcrew.services.athlete_memory import preferences_for_display
from runcrew.services.memory_candidates import expire_pending_memory_candidates
from runcrew.services.memory_context import load_agent_memory_context
from runcrew.storage.database import Database
from runcrew.storage.repositories import (
    AthletePreferenceRepository,
    ChatRepository,
    MemoryCandidateRepository,
    TrainingGoalRepository,
    WeeklyTrainingMemoryRepository,
)


class MemoryControlError(RuntimeError):
    pass


class MemoryControlService:
    """只读聚合记忆来源、生命周期和职责可见性；写操作复用原服务。"""

    def __init__(
        self,
        *,
        database_path: Path = Path("data/runcrew.db"),
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.database_path = database_path
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self.database = Database(f"sqlite:///{database_path.resolve().as_posix()}")
        self.database.create_schema()

    def _now(self) -> datetime:
        current = self._clock()
        if current.tzinfo is None or current.utcoffset() is None:
            raise MemoryControlError("clock 必须返回包含时区的时间。")
        return current

    def overview(self) -> MemoryControlOverview:
        now = self._now()
        current_week = now.astimezone().date()
        current_week -= timedelta(days=current_week.weekday())
        next_week = current_week + timedelta(days=7)

        with self.database.session() as session:
            candidates_repository = MemoryCandidateRepository(session)
            expire_pending_memory_candidates(
                candidates=candidates_repository,
                now=now,
            )
            candidates = candidates_repository.list(include_resolved=True, limit=100)
            chats = ChatRepository(session)
            candidate_items = []
            for candidate in candidates:
                conversation = chats.get_record(candidate.conversation_id)
                source = chats.get_message_record(candidate.source_message_id)
                candidate_items.append(
                    MemoryCandidateControlItem(
                        candidate=candidate,
                        conversation_title=(
                            conversation.title if conversation is not None else "来源对话不可用"
                        ),
                        source_excerpt=(
                            _excerpt(source.content) if source is not None else None
                        ),
                        source_available=source is not None,
                    )
                )

            preference_repository = AthletePreferenceRepository(session)
            preferences = preferences_for_display(preference_repository, as_of=now)
            preference_items = [
                AthletePreferenceControlItem(
                    preference=item,
                    effective_now=item.is_effective_at(now),
                )
                for item in preferences
            ]

            goals = TrainingGoalRepository(session).list(limit=50)
            weekly_repository = WeeklyTrainingMemoryRepository(session)
            weekly_items = []
            goal_contexts = []
            for goal in goals:
                weekly_items.extend(
                    WeeklyMemoryControlItem(memory=item, goal_name=goal.name)
                    for item in weekly_repository.list_for_goal(
                        goal.id,
                        include_inactive=True,
                        limit=50,
                    )
                )
                if goal.status != "active":
                    continue
                contexts = [
                    load_agent_memory_context(
                        MemoryContextBuildRequest(
                            role=role,
                            goal_id=goal.id,
                            as_of=now,
                            target_week_start=(next_week if role == "plan" else None),
                        ),
                        preferences=preference_repository,
                        weekly_memories=weekly_repository,
                    )
                    for role in ("execution", "recovery", "plan")
                ]
                goal_contexts.append(
                    MemoryGoalContextAudit(
                        goal_id=goal.id,
                        goal_name=goal.name,
                        target_week_start=next_week,
                        contexts=contexts,
                    )
                )
            session.commit()

        weekly_items.sort(
            key=lambda item: (item.memory.week_start, item.memory.version),
            reverse=True,
        )
        return MemoryControlOverview(
            generated_at=now,
            counts=MemoryControlCounts(
                pending_candidates=sum(
                    item.candidate.status == "pending" for item in candidate_items
                ),
                active_preferences=sum(item.effective_now for item in preference_items),
                active_weekly_memories=sum(
                    item.memory.status == "active" for item in weekly_items
                ),
                total_records=(
                    len(candidate_items) + len(preference_items) + len(weekly_items)
                ),
            ),
            candidates=candidate_items,
            preferences=preference_items,
            weekly_memories=weekly_items,
            goal_contexts=goal_contexts,
        )


def _excerpt(value: str, *, limit: int = 240) -> str:
    compact = re.sub(r"\s+", " ", value).strip()
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 1].rstrip()}…"
