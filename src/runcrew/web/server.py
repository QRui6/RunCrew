from __future__ import annotations

import asyncio
import json
import webbrowser
from dataclasses import dataclass
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
from typing import Mapping
from urllib.parse import parse_qs, urlparse

from pydantic import ValidationError

from runcrew.policies.deepseek import DeepSeekPolicyError
from runcrew.services.chat import ChatService, ChatServiceError
from runcrew.services.training_operations import (
    TrainingOperationsError,
    TrainingOperationsService,
)
from runcrew.domain.training_operations import (
    CheckInSubmission,
    CoachRunDecisionRequest,
    CoachRunSubmission,
    ExecutionDecisionSubmission,
    TrainingGoalSubmission,
    WeeklyPlanActivationRequest,
    WeeklyPlanDraftSubmission,
)
from runcrew.web.dashboard import DemoDashboardService


@dataclass(frozen=True, slots=True)
class DemoResponse:
    status: int
    content_type: str
    body: bytes
    headers: Mapping[str, str]


class DemoApplication:
    def __init__(
        self,
        service: DemoDashboardService,
        chat_service: ChatService | None = None,
        training_service: TrainingOperationsService | None = None,
    ) -> None:
        self.service = service
        self.chat_service = chat_service or ChatService(
            database_path=service.database_path
        )
        self.training_service = training_service or TrainingOperationsService(
            database_path=service.database_path
        )
        static_root = resources.files("runcrew.web").joinpath("static")
        self._static = {
            "/": ("text/html; charset=utf-8", static_root.joinpath("chat.html")),
            "/engineering": (
                "text/html; charset=utf-8",
                static_root.joinpath("index.html"),
            ),
            "/assets/chat.css": (
                "text/css; charset=utf-8",
                static_root.joinpath("chat.css"),
            ),
            "/assets/chat.js": (
                "text/javascript; charset=utf-8",
                static_root.joinpath("chat.js"),
            ),
            "/assets/styles.css": (
                "text/css; charset=utf-8",
                static_root.joinpath("styles.css"),
            ),
            "/assets/app.js": (
                "text/javascript; charset=utf-8",
                static_root.joinpath("app.js"),
            ),
        }

    def handle(self, method: str, target: str, body: bytes = b"") -> DemoResponse:
        parsed = urlparse(target)
        if method == "GET" and parsed.path in self._static:
            content_type, resource = self._static[parsed.path]
            return DemoResponse(
                status=HTTPStatus.OK,
                content_type=content_type,
                body=resource.read_bytes(),
                headers={"Cache-Control": "no-cache"},
            )
        if method == "GET" and parsed.path == "/api/dashboard":
            try:
                query = _parse_dashboard_query(parse_qs(parsed.query))
                snapshot = self.service.build_snapshot(**query)
            except (ValueError, ValidationError) as error:
                return self._json_response(
                    HTTPStatus.BAD_REQUEST,
                    {"error": str(error)},
                )
            except Exception:
                return self._json_response(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    {"error": "本地演示数据加载失败，请检查数据库和评测报告。"},
                )
            return self._json_response(
                HTTPStatus.OK,
                snapshot.model_dump(mode="json"),
            )
        if parsed.path == "/api/dashboard":
            return self._json_response(
                HTTPStatus.METHOD_NOT_ALLOWED,
                {"error": "工程观测接口只允许只读 GET 请求。"},
            )
        if method == "GET" and parsed.path == "/api/chat/bootstrap":
            return self._json_response(
                HTTPStatus.OK,
                self.chat_service.bootstrap().model_dump(mode="json"),
            )
        if method == "GET" and parsed.path == "/api/training/bootstrap":
            return self._json_response(
                HTTPStatus.OK,
                self.training_service.bootstrap().model_dump(mode="json"),
            )
        if method == "POST" and parsed.path == "/api/training/goals":
            try:
                submission = TrainingGoalSubmission.model_validate(self._decode_json(body))
                goal = self.training_service.create_goal(submission)
            except (TrainingOperationsError, ValidationError, ValueError) as error:
                return self._json_response(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            return self._json_response(HTTPStatus.CREATED, goal.model_dump(mode="json"))
        training_goal_id, training_goal_action = _training_goal_route(parsed.path)
        if method == "POST" and training_goal_id and training_goal_action == "plan-drafts":
            try:
                submission = WeeklyPlanDraftSubmission.model_validate(self._decode_json(body))
                result = self.training_service.draft_week_plan(
                    goal_id=training_goal_id, submission=submission
                )
            except (TrainingOperationsError, ValidationError, ValueError) as error:
                return self._json_response(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            return self._json_response(HTTPStatus.OK, result.model_dump(mode="json"))
        if method == "POST" and training_goal_id and training_goal_action == "plans/activate":
            try:
                request = WeeklyPlanActivationRequest.model_validate(self._decode_json(body))
                result = self.training_service.activate_week_plan(
                    goal_id=training_goal_id, request=request
                )
            except (TrainingOperationsError, ValidationError, ValueError) as error:
                return self._json_response(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            return self._json_response(HTTPStatus.CREATED, result.model_dump(mode="json"))
        if method == "GET" and training_goal_id and training_goal_action == "week":
            try:
                query = parse_qs(parsed.query)
                raw_as_of = _single(query, "as_of")
                as_of = (
                    datetime.fromisoformat(raw_as_of.replace("Z", "+00:00"))
                    if raw_as_of
                    else datetime.now().astimezone()
                )
                result = self.training_service.week_view(
                    goal_id=training_goal_id,
                    as_of=as_of,
                    provider=_single(query, "provider") or None,
                )
            except (TrainingOperationsError, ValidationError, ValueError) as error:
                return self._json_response(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            return self._json_response(HTTPStatus.OK, result.model_dump(mode="json"))
        training_plan_id = _training_execution_route(parsed.path)
        if method == "POST" and training_plan_id:
            try:
                submission = ExecutionDecisionSubmission.model_validate(
                    self._decode_json(body)
                )
                result = self.training_service.decide_execution(
                    plan_id=training_plan_id, submission=submission
                )
            except (TrainingOperationsError, ValidationError, ValueError) as error:
                return self._json_response(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            return self._json_response(HTTPStatus.OK, result.model_dump(mode="json"))
        goal_id = _training_check_in_route(parsed.path)
        if method == "POST" and goal_id:
            try:
                submission = CheckInSubmission.model_validate(self._decode_json(body))
                check_in = self.training_service.record_check_in(
                    goal_id=goal_id,
                    submission=submission,
                )
            except (TrainingOperationsError, ValidationError, ValueError) as error:
                return self._json_response(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            return self._json_response(
                HTTPStatus.CREATED,
                check_in.model_dump(mode="json"),
            )
        if method == "POST" and parsed.path == "/api/training/coach-runs":
            try:
                submission = CoachRunSubmission.model_validate(self._decode_json(body))
                result = asyncio.run(self.training_service.run_coach(submission))
            except (TrainingOperationsError, ValidationError, ValueError) as error:
                return self._json_response(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            return self._json_response(
                HTTPStatus.CREATED,
                result.model_dump(mode="json"),
            )
        coach_run_id, is_decision = _training_coach_run_route(parsed.path)
        if method == "GET" and coach_run_id and not is_decision:
            try:
                result = self.training_service.get_coach_run(coach_run_id)
            except TrainingOperationsError as error:
                return self._json_response(HTTPStatus.NOT_FOUND, {"error": str(error)})
            return self._json_response(HTTPStatus.OK, result.model_dump(mode="json"))
        if method == "POST" and coach_run_id and is_decision:
            try:
                decision = CoachRunDecisionRequest.model_validate(self._decode_json(body))
                result = asyncio.run(
                    self.training_service.decide_coach_run(
                        run_id=coach_run_id,
                        request=decision,
                    )
                )
            except (TrainingOperationsError, ValidationError, ValueError) as error:
                return self._json_response(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            return self._json_response(HTTPStatus.OK, result.model_dump(mode="json"))
        if method == "POST" and parsed.path == "/api/chat/conversations":
            try:
                payload = self._decode_json(body)
                conversation = self.chat_service.create_conversation(
                    activity_id=str(payload.get("activity_id", "")),
                    title=str(payload.get("title", "新的跑步对话")),
                    lookback_days=int(payload.get("lookback_days", 28)),
                )
            except (ChatServiceError, TypeError, ValueError) as error:
                return self._json_response(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            return self._json_response(
                HTTPStatus.CREATED,
                conversation.model_dump(mode="json"),
            )
        conversation_id, is_messages = _chat_conversation_route(parsed.path)
        if method == "GET" and conversation_id and not is_messages:
            try:
                conversation = self.chat_service.get_conversation(conversation_id)
            except ChatServiceError as error:
                return self._json_response(HTTPStatus.NOT_FOUND, {"error": str(error)})
            return self._json_response(
                HTTPStatus.OK,
                conversation.model_dump(mode="json"),
            )
        if method == "POST" and conversation_id and is_messages:
            try:
                payload = self._decode_json(body)
                result = asyncio.run(
                    self.chat_service.send_message(
                        conversation_id=conversation_id,
                        content=str(payload.get("content", "")),
                        use_deepseek=bool(payload.get("use_deepseek", False)),
                    )
                )
            except ChatServiceError as error:
                return self._json_response(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            except DeepSeekPolicyError as error:
                return self._json_response(HTTPStatus.BAD_GATEWAY, {"error": str(error)})
            except Exception:
                return self._json_response(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    {"error": "本轮对话执行失败，用户消息已安全保留。"},
                )
            return self._json_response(
                HTTPStatus.OK,
                result.model_dump(mode="json"),
            )
        if method not in {"GET", "POST"}:
            return self._json_response(
                HTTPStatus.METHOD_NOT_ALLOWED,
                {"error": "请求方法不受支持。"},
            )
        return self._json_response(HTTPStatus.NOT_FOUND, {"error": "页面不存在。"})

    @staticmethod
    def _decode_json(body: bytes) -> dict[str, object]:
        if not body:
            raise ValueError("请求正文不能为空。")
        if len(body) > 64 * 1024:
            raise ValueError("请求正文超过64 KB限制。")
        try:
            value = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("请求正文必须是合法 JSON。") from error
        if not isinstance(value, dict):
            raise ValueError("请求正文必须是 JSON 对象。")
        return value

    @staticmethod
    def _json_response(status: int, payload: object) -> DemoResponse:
        return DemoResponse(
            status=status,
            content_type="application/json; charset=utf-8",
            body=json.dumps(
                payload,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8"),
            headers={"Cache-Control": "no-store"},
        )


class _DemoHttpServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], application: DemoApplication) -> None:
        self.application = application
        super().__init__(address, _DemoRequestHandler)


class _DemoRequestHandler(BaseHTTPRequestHandler):
    server: _DemoHttpServer

    def do_GET(self) -> None:
        self._respond(self.server.application.handle("GET", self.path))

    def do_POST(self) -> None:
        raw_length = self.headers.get("Content-Length", "0")
        try:
            length = int(raw_length)
        except ValueError:
            length = 0
        if length < 0 or length > 64 * 1024:
            self._respond(
                DemoApplication._json_response(
                    HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                    {"error": "请求正文超过64 KB限制。"},
                )
            )
            return
        body = self.rfile.read(length)
        self._respond(self.server.application.handle("POST", self.path, body))

    def _respond(self, response: DemoResponse) -> None:
        self.send_response(response.status)
        self.send_header("Content-Type", response.content_type)
        self.send_header("Content-Length", str(len(response.body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", _CONTENT_SECURITY_POLICY)
        for name, value in response.headers.items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(response.body)

    def log_message(self, format: str, *args: object) -> None:
        return


_CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self'; "
    "img-src 'self' data:; "
    "connect-src 'self'; "
    "base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
)


def serve_demo(
    *,
    port: int = 8766,
    database_path: Path = Path("data/runcrew.db"),
    evaluation_directory: Path = Path("data/private/evals"),
    open_browser: bool = True,
) -> None:
    service = DemoDashboardService(
        database_path=database_path,
        evaluation_directory=evaluation_directory,
    )
    application = DemoApplication(
        service,
        ChatService(database_path=database_path),
        TrainingOperationsService(database_path=database_path),
    )
    server = _DemoHttpServer(("127.0.0.1", port), application)
    url = f"http://127.0.0.1:{server.server_port}"
    print(f"RunCrew 本地演示界面：{url}")
    print("跑步数据连续对话与工程观测台均只绑定本机；按 Ctrl+C 停止。")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def _parse_dashboard_query(query: dict[str, list[str]]) -> dict[str, object]:
    provider = _single(query, "provider")
    if provider == "all" or provider == "":
        provider = None
    if provider is not None and provider not in {
        "coros",
        "fixture",
        "fit",
        "keep",
        "manual",
    }:
        raise ValueError("provider 参数不受支持。")
    lookback_days = _bounded_int(query, "lookback_days", default=28, minimum=14, maximum=90)
    planned_distance_km = _positive_float(query, "planned_distance_km")
    planned_duration_minutes = _positive_float(query, "planned_duration_minutes")
    return {
        "provider": provider,
        "lookback_days": lookback_days,
        "planned_distance_km": planned_distance_km,
        "planned_duration_minutes": planned_duration_minutes,
    }


def _chat_conversation_route(path: str) -> tuple[str | None, bool]:
    parts = [part for part in path.split("/") if part]
    if len(parts) == 4 and parts[:3] == ["api", "chat", "conversations"]:
        return parts[3], False
    if (
        len(parts) == 5
        and parts[:3] == ["api", "chat", "conversations"]
        and parts[4] == "messages"
    ):
        return parts[3], True
    return None, False


def _training_check_in_route(path: str) -> str | None:
    parts = [part for part in path.split("/") if part]
    if len(parts) == 5 and parts[:3] == ["api", "training", "goals"] and parts[4] == "check-ins":
        return parts[3]
    return None


def _training_goal_route(path: str) -> tuple[str | None, str | None]:
    parts = [part for part in path.split("/") if part]
    if len(parts) == 5 and parts[:3] == ["api", "training", "goals"]:
        if parts[4] in {"plan-drafts", "week"}:
            return parts[3], parts[4]
    if (
        len(parts) == 6
        and parts[:3] == ["api", "training", "goals"]
        and parts[4:] == ["plans", "activate"]
    ):
        return parts[3], "plans/activate"
    return None, None


def _training_execution_route(path: str) -> str | None:
    parts = [part for part in path.split("/") if part]
    if (
        len(parts) == 5
        and parts[:3] == ["api", "training", "plans"]
        and parts[4] == "execution-decisions"
    ):
        return parts[3]
    return None


def _training_coach_run_route(path: str) -> tuple[str | None, bool]:
    parts = [part for part in path.split("/") if part]
    if len(parts) == 4 and parts[:3] == ["api", "training", "coach-runs"]:
        return parts[3], False
    if (
        len(parts) == 5
        and parts[:3] == ["api", "training", "coach-runs"]
        and parts[4] == "decision"
    ):
        return parts[3], True
    return None, False


def _single(query: dict[str, list[str]], name: str) -> str | None:
    values = query.get(name)
    return values[0].strip() if values else None


def _bounded_int(
    query: dict[str, list[str]],
    name: str,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    raw = _single(query, name)
    if raw is None or raw == "":
        return default
    try:
        value = int(raw)
    except ValueError as error:
        raise ValueError(f"{name} 必须是整数。") from error
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} 必须在 {minimum} 到 {maximum} 之间。")
    return value


def _positive_float(
    query: dict[str, list[str]],
    name: str,
) -> float | None:
    raw = _single(query, name)
    if raw is None or raw == "":
        return None
    try:
        value = float(raw)
    except ValueError as error:
        raise ValueError(f"{name} 必须是数字。") from error
    if value <= 0 or value > 100000:
        raise ValueError(f"{name} 必须大于0且处于合理范围。")
    return value
