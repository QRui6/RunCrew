import asyncio
import json
from datetime import date

from runcrew.domain.activity import ActivityDetail
from runcrew.providers.coros.provider import CorosActivityProvider


class FakeMcpClient:
    initialized = False

    async def initialize(self):
        self.initialized = True
        return {"result": {"protocolVersion": "2025-06-18"}}

    async def call_tool(self, name, arguments):
        if name == "querySportRecords":
            payload = {
                "records": [
                    {
                        "labelId": "coros-live-shape-1",
                        "sportType": 100,
                        "startTimestamp": 1786065000,
                        "workoutTime": 2718,
                        "distance": "8.02 km",
                        "avgPace": "5:39/km",
                        "avgHr": 151,
                    }
                ]
            }
        else:
            assert arguments == {"labelId": "coros-live-shape-1", "sportType": 100}
            payload = {
                "data": {
                    "averageCadence": 176,
                    "maxHeartRate": 166,
                    "laps": [
                        {
                            "lap": 1,
                            "lapTime": 337,
                            "distance": "1 km",
                            "avgPace": "5:37/km",
                        }
                    ],
                }
            }
        return {
            "result": {
                "content": [
                    {"type": "text", "text": json.dumps(json.dumps(payload))}
                ]
            }
        }

    async def aclose(self):
        return None


def test_coros_provider_list_and_detail_pipeline() -> None:
    client = FakeMcpClient()
    provider = CorosActivityProvider(mcp_client=client)

    asyncio.run(provider.connect())
    activities = asyncio.run(
        provider.list_activities(date(2026, 8, 1), date(2026, 8, 8))
    )
    detail = asyncio.run(
        provider.get_activity(activities[0].activity.source_ref.external_id)
    )

    assert client.initialized is True
    assert len(activities) == 1
    assert isinstance(detail.activity, ActivityDetail)
    assert detail.activity.average_cadence == 176

