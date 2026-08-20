from __future__ import annotations

from datetime import datetime, timezone

from runcrew.domain.memory import (
    AthletePreference,
    AthletePreferenceSubmission,
)
from runcrew.storage.repositories import AthletePreferenceRepository


class AthleteMemoryError(ValueError):
    pass


def confirm_athlete_preference(
    submission: AthletePreferenceSubmission,
    *,
    preferences: AthletePreferenceRepository,
    source_ref: str,
    now: datetime | None = None,
) -> AthletePreference:
    """显式确认后替换同 key 偏好；相同值与时效重复提交保持幂等。"""

    confirmed_at = now or datetime.now(timezone.utc)
    if confirmed_at.tzinfo is None or confirmed_at.utcoffset() is None:
        raise AthleteMemoryError("确认时间必须包含时区")
    if submission.valid_until is not None and submission.valid_until <= confirmed_at:
        raise AthleteMemoryError("偏好失效时间必须晚于确认时间")
    current = preferences.current_for_key(submission.key)
    if (
        current is not None
        and current.is_effective_at(confirmed_at)
        and current.value == submission.value
        and current.valid_until == submission.valid_until
    ):
        return current
    if current is not None:
        current.status = "superseded"
        current.updated_at = confirmed_at
        preferences.save(current)
    preference = AthletePreference(
        key=submission.key,
        value=submission.value,
        source_ref=source_ref,
        confirmed_at=confirmed_at,
        valid_from=confirmed_at,
        valid_until=submission.valid_until,
        supersedes_id=current.id if current is not None else None,
        created_at=confirmed_at,
        updated_at=confirmed_at,
    )
    preferences.save(preference)
    return preference


def archive_athlete_preference(
    preference_id: str,
    *,
    preferences: AthletePreferenceRepository,
    now: datetime | None = None,
) -> AthletePreference:
    archived_at = now or datetime.now(timezone.utc)
    preference = preferences.get(preference_id)
    if preference is None:
        raise AthleteMemoryError("训练偏好不存在")
    if preference.status != "active":
        raise AthleteMemoryError("只有当前生效的训练偏好可以停用")
    preference.status = "archived"
    preference.updated_at = archived_at
    preferences.save(preference)
    return preference


def preferences_for_display(
    preferences: AthletePreferenceRepository,
    *,
    as_of: datetime | None = None,
) -> list[AthletePreference]:
    now = as_of or datetime.now(timezone.utc)
    result: list[AthletePreference] = []
    for item in preferences.list():
        if (
            item.status == "active"
            and item.valid_until is not None
            and item.valid_until <= now
        ):
            result.append(item.model_copy(update={"status": "expired"}))
        else:
            result.append(item)
    return result

