"""SNTL provider — wraps :class:`SntlClient` behind the :class:`TaskProvider` interface."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from src.errors import SntlError
from src.models.provider_capabilities import ProviderCapabilities
from src.models.task import Task
from src.models.worklog import Worklog
from src.providers.base import BaseProvider
from src.sntl_client import SntlClient

_STATE_GROUPS = {"ni": "Not started", "ep": "In progress", "c": "Done"}
_DEFAULT_GROUPS = ("ni", "ep")
_LAST_SECOND = 86399


def _display_duration(seconds: int) -> str:
    if seconds <= 0:
        return "0m"
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    if hours and minutes:
        return f"{hours}h {minutes}m"
    if hours:
        return f"{hours}h"
    return f"{minutes}m"


def _clock(seconds: int) -> str:
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if secs:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{hours:02d}:{minutes:02d}"


def _seconds_of(value: str) -> int | None:
    parts = (value or "").strip().split(":")
    if len(parts) < 2 or not all(part.isdigit() for part in parts):
        return None
    hours, minutes = int(parts[0]), int(parts[1])
    secs = int(parts[2]) if len(parts) > 2 else 0
    return hours * 3600 + minutes * 60 + secs


def _started_datetime(value: str) -> datetime:
    raw = (value or "").strip()
    if not raw:
        return datetime.now()
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    raise SntlError("Invalid started value. Use 'YYYY-MM-DD' or 'YYYY-MM-DD HH:MM'.")


def _entry_seconds(item: dict[str, Any]) -> int:
    hours = item.get("hours")
    if isinstance(hours, (int, float)):
        return max(0, int(round(float(hours) * 3600)))
    start = _seconds_of(str(item.get("start") or ""))
    end = _seconds_of(str(item.get("end") or ""))
    if start is not None and end is not None and end > start:
        return end - start
    return 0


def _entry_started(item: dict[str, Any]) -> str:
    date = str(item.get("date") or "")[:10]
    start = str(item.get("start") or "")[:5]
    if date and start:
        return f"{date}T{start}:00"
    if date:
        return f"{date}T00:00:00"
    return ""


def _task_status(item: dict[str, Any]) -> str:
    state = item.get("state")
    if isinstance(state, dict) and state.get("name"):
        return str(state["name"])
    if isinstance(state, str) and state:
        return state
    return _STATE_GROUPS.get(str(item.get("grp") or ""), "")


def _to_task(item: dict[str, Any], provider: str) -> Task:
    labels = [
        str(value)
        for value in (item.get("project"), item.get("sprint"))
        if isinstance(value, str) and value
    ]
    title = str(item.get("title") or "")
    parent = item.get("parentTitle")
    details = [f"Parent: {parent}"] if parent else []
    if item.get("fixed"):
        details.append(f"Ceremony: {item['fixed']}")
    elif isinstance(item.get("estimate"), (int, float)):
        details.append(f"Estimate: {item['estimate']}h")
    elif "estimate" in item:
        details.append("No approved estimate")
    return Task(
        id=str(item.get("id", "")),
        provider=provider,
        summary=f"{title} ({parent})" if parent else title,
        status=_task_status(item),
        task_type="ceremony" if item.get("fixed") else "task",
        assignee=str(item.get("assignee") or ""),
        labels=labels,
        description=" · ".join(details),
        updated=str(item.get("updatedAt") or ""),
    )


def _parse_groups(native_query: str) -> tuple[str, ...]:
    tokens = [token.strip().lower() for token in (native_query or "").split(",") if token.strip()]
    if not tokens:
        return _DEFAULT_GROUPS
    if "all" in tokens:
        return tuple(_STATE_GROUPS)
    unknown = [token for token in tokens if token not in _STATE_GROUPS]
    if unknown:
        raise SntlError(
            f"Unknown state group(s): {', '.join(unknown)}. Use ni, ep, c, or all."
        )
    return tuple(tokens)


def _matches(item: dict[str, Any], query: str) -> bool:
    if not query:
        return True
    haystack = " ".join(
        str(item.get(key) or "")
        for key in ("title", "project", "parentTitle", "sprint")
    )
    haystack = f"#{item.get('id', '')} {haystack}".lower()
    return all(word in haystack for word in query.lower().split())


class SntlProvider(BaseProvider):
    def __init__(self, client: SntlClient) -> None:
        self._client = client
        self._profile: dict[str, Any] | None = None

    @classmethod
    def from_env(cls) -> "SntlProvider":
        return cls(SntlClient.from_env())

    @property
    def name(self) -> str:
        return "sntl"

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(supports_comments=False, supports_worklogs=True)

    def _me(self) -> dict[str, Any]:
        if self._profile is None:
            self._profile = self._client.me()
        return self._profile

    def _employee(self) -> dict[str, Any]:
        employee = self._me().get("employee")
        return employee if isinstance(employee, dict) else {}

    def whoami(self) -> dict[str, Any]:
        me = self._me()
        employee = self._employee()
        account_id = str(employee.get("id") or "")
        output: dict[str, Any] = {
            "provider": self.name,
            "ok": bool(account_id),
            "accountId": account_id,
            "displayName": employee.get("name") or me.get("name") or me.get("username") or "",
        }
        if me.get("today"):
            output["today"] = me["today"]
        if not account_id:
            output["note"] = "The SNTL user is not linked to an employee, so it cannot log hours."
        return output

    def current_account_id(self) -> str | None:
        account_id = self._employee().get("id")
        return str(account_id) if account_id is not None else None

    def search_tasks(
        self, query: str = "", max_results: int = 20, native_query: str = ""
    ) -> list[Task]:
        groups = _parse_groups(native_query)
        text = (query or "").strip()
        items = [
            item
            for item in self._client.my_tasks()
            if str(item.get("grp") or "") in groups and _matches(item, text)
        ]
        if max_results > 0:
            items = items[:max_results]
        return [_to_task(item, self.name) for item in items]

    def get_task(self, task_id: str) -> Task:
        item = self._client.get_task(task_id)
        if not item.get("title"):
            wanted = str(task_id).strip().lstrip("#")
            mine = next(
                (task for task in self._client.my_tasks() if str(task.get("id")) == wanted),
                None,
            )
            if mine:
                item = {**mine, **{key: value for key, value in item.items() if value}}
        if not item:
            raise SntlError(f"SNTL task #{task_id} not found.")
        return _to_task(item, self.name)

    def log_work(
        self,
        task_id: str,
        time_spent_seconds: int,
        started: str,
        comment: str = "",
    ) -> Worklog:
        if time_spent_seconds <= 0:
            raise SntlError("time_spent_seconds must be greater than zero.")
        moment = _started_datetime(started)
        start_seconds = moment.hour * 3600 + moment.minute * 60
        end_seconds = start_seconds + time_spent_seconds
        if end_seconds > _LAST_SECOND:
            raise SntlError("The entry must end by midnight. Split it, or start earlier.")
        date = moment.strftime("%Y-%m-%d")
        start_time = _clock(start_seconds)
        data = self._client.create_entry(
            task_id, date, start_time, _clock(end_seconds), comment
        )
        return Worklog(
            id=str(data.get("id") or ""),
            provider=self.name,
            task_id=str(task_id).strip().lstrip("#"),
            author="",
            time_spent_seconds=time_spent_seconds,
            time_spent_display=_display_duration(time_spent_seconds),
            started=f"{date}T{start_time}:00",
            comment=comment,
            status=str(data.get("status") or ""),
        )

    def get_worklogs(self, task_id: str) -> list[Worklog]:
        wanted = str(task_id).strip().lstrip("#")
        author = str(self._employee().get("name") or "")
        author_id = self.current_account_id() or ""
        worklogs: list[Worklog] = []
        for item in self._client.my_entries():
            if str(item.get("taskId")) != wanted:
                continue
            seconds = _entry_seconds(item)
            worklogs.append(
                Worklog(
                    id=str(item.get("id") or ""),
                    provider=self.name,
                    task_id=wanted,
                    author=author,
                    time_spent_seconds=seconds,
                    time_spent_display=_display_duration(seconds),
                    started=_entry_started(item),
                    comment=str(item.get("note") or ""),
                    author_id=author_id,
                    status=str(item.get("status") or ""),
                )
            )
        return worklogs
