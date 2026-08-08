from datetime import date
from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from runcrew.domain.activity import ActivityDetail, ActivitySummary


@dataclass(frozen=True, slots=True)
class ProviderActivity:
    activity: ActivitySummary | ActivityDetail
    raw_payload: Mapping[str, Any]


class ActivityProvider(Protocol):
    @property
    def name(self) -> str: ...

    async def list_activities(
        self, start_date: date, end_date: date
    ) -> list[ProviderActivity]: ...

    async def get_activity(self, external_id: str) -> ProviderActivity: ...
