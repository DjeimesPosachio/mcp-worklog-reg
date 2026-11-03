"""HTTP client for the SNTL REST API. This module does not know about MCP.

Read/append only by design: it can read the current user, the user's tasks and
time entries, read one task, and create time entries. It exposes no method that
edits or deletes tasks or time entries.
"""

from __future__ import annotations

import atexit
import os
import time
from typing import Any
from urllib.parse import urlparse

import httpx

from src.errors import SntlError

_DEFAULT_API = "https://back-end.viptech.com.br"

_TOKEN_KEYS = ("access_token", "accessToken", "token", "jwt")

_http_client: httpx.Client | None = None


def _get_http_client() -> httpx.Client:
    global _http_client
    if _http_client is None:
        _http_client = httpx.Client(
            timeout=httpx.Timeout(30.0),
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        )
    return _http_client


@atexit.register
def _close_http_client() -> None:
    global _http_client
    if _http_client is not None:
        _http_client.close()
        _http_client = None


class SntlClient:
    def __init__(
        self,
        username: str,
        password: str,
        base_url: str = _DEFAULT_API,
        timeout: float = 30.0,
    ):
        if not (username and password):
            raise SntlError("Set SNTL_USERNAME and SNTL_PASSWORD.")
        self.base_url = _validate_base_url(base_url or _DEFAULT_API)
        self._username = username
        self._password = password
        self._timeout = timeout
        self._token: str | None = None

    @classmethod
    def from_env(cls) -> "SntlClient":
        return cls(
            username=os.getenv("SNTL_USERNAME", ""),
            password=os.getenv("SNTL_PASSWORD", ""),
            base_url=os.getenv("SNTL_API_URL", _DEFAULT_API) or _DEFAULT_API,
        )

    def me(self) -> dict[str, Any]:
        return self._request("GET", "/pm/me") or {}

    def my_tasks(self) -> list[dict[str, Any]]:
        return _as_list(self._request("GET", "/pm/me/tasks"))

    def my_entries(self) -> list[dict[str, Any]]:
        return _as_list(self._request("GET", "/pm/me/entries"))

    def get_task(self, task_id: str) -> dict[str, Any]:
        return self._request("GET", f"/pm/tasks/{_numeric_id(task_id)}") or {}

    def create_entry(
        self,
        task_id: str,
        date: str,
        start_time: str,
        end_time: str,
        note: str = "",
    ) -> dict[str, Any]:
        body = {
            "taskId": _numeric_id(task_id),
            "date": date,
            "startTime": start_time,
            "endTime": end_time,
            "note": note,
        }
        return self._request("POST", "/pm/entries", body) or {}

    def _request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        *,
        retries: int = 3,
    ) -> Any:
        if self._token is None:
            self._authenticate()
        backoffs = (0.5, 1.0, 2.0)
        attempt = 0
        reauthed = False
        while True:
            try:
                response = _get_http_client().request(
                    method,
                    f"{self.base_url}{path}",
                    headers=self._headers(),
                    json=body,
                    timeout=self._timeout,
                )
            except httpx.HTTPError as exc:
                if method == "GET" and attempt < retries:
                    time.sleep(backoffs[min(attempt, len(backoffs) - 1)])
                    attempt += 1
                    continue
                raise SntlError("Network failure while accessing SNTL.", detail=str(exc))

            if response.status_code == 401 and not reauthed:
                self._authenticate()
                reauthed = True
                continue

            if method == "GET" and (
                response.status_code == 429 or response.status_code >= 500
            ):
                if attempt < retries:
                    time.sleep(backoffs[min(attempt, len(backoffs) - 1)])
                    attempt += 1
                    continue

            if response.status_code >= 400:
                raise self._map_error(response)

            return self._decode(response)

    def _authenticate(self) -> None:
        try:
            response = _get_http_client().post(
                f"{self.base_url}/auth/login",
                headers={"Accept": "application/json", "Content-Type": "application/json"},
                json={
                    "username": self._username,
                    "password": self._password,
                    "rememberMe": True,
                },
                timeout=self._timeout,
            )
        except httpx.HTTPError as exc:
            raise SntlError("Network failure while accessing SNTL.", detail=str(exc))
        if response.status_code in (400, 401, 403):
            raise SntlError(
                "SNTL login failed. Check SNTL_USERNAME and SNTL_PASSWORD.",
                status=response.status_code,
                detail=_message(response),
            )
        if response.status_code >= 400:
            raise self._map_error(response)
        token = _find_token(self._decode(response))
        if not token:
            raise SntlError("SNTL login did not return a token.")
        self._token = token

    def _headers(self) -> dict[str, str]:
        if not self._token:
            raise SntlError("SNTL authentication failed.")
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._token}",
        }

    @staticmethod
    def _decode(response: httpx.Response) -> Any:
        if not response.content:
            return None
        try:
            return response.json()
        except Exception as exc:
            raise SntlError(
                "SNTL returned an invalid JSON response.",
                status=response.status_code,
                detail=str(exc),
            )

    @staticmethod
    def _map_error(response: httpx.Response) -> SntlError:
        status = response.status_code
        detail = _message(response)
        if status == 400:
            message = detail or "Invalid SNTL request. Check the task id, date, and times."
        elif status == 401:
            message = "Invalid or expired SNTL token. Check SNTL_USERNAME and SNTL_PASSWORD."
        elif status == 403:
            message = detail or "Missing permission for this SNTL action."
        elif status == 404:
            message = "SNTL resource not found, or the user cannot access it."
        elif status == 429:
            message = "SNTL rate limit reached (HTTP 429). Wait and try again."
        elif status >= 500:
            message = f"SNTL service error (HTTP {status}). Try again shortly."
        else:
            message = detail or f"SNTL returned HTTP {status}."
        return SntlError(message, status=status, detail=detail)


def _message(response: httpx.Response) -> str:
    try:
        body = response.json()
    except Exception:
        return response.text[:300]
    if isinstance(body, dict):
        message = body.get("message")
        if isinstance(message, list):
            return " ".join(str(item) for item in message)
        if message:
            return str(message)
    return response.text[:300]


def _find_token(body: Any) -> str | None:
    if isinstance(body, dict):
        for key in _TOKEN_KEYS:
            value = body.get(key)
            if isinstance(value, str) and value:
                return value
        for value in body.values():
            if isinstance(value, dict):
                token = _find_token(value)
                if token:
                    return token
    return None


def _as_list(body: Any) -> list[dict[str, Any]]:
    if isinstance(body, list):
        return [item for item in body if isinstance(item, dict)]
    if isinstance(body, dict):
        for key in ("items", "data", "results", "entries", "tasks"):
            value = body.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def _numeric_id(task_id: str | int) -> int:
    value = str(task_id).strip().lstrip("#")
    if not value.isdigit():
        raise SntlError(f"Invalid SNTL task id: '{task_id}'. Use the numeric #id.")
    return int(value)


def _validate_base_url(base_url: str) -> str:
    parsed = urlparse(base_url)
    if parsed.scheme not in ("http", "https"):
        raise SntlError(
            "SNTL_API_URL must use HTTP or HTTPS. Example: https://back-end.viptech.com.br"
        )
    if not parsed.hostname:
        raise SntlError(
            "SNTL_API_URL must include a host. Example: https://back-end.viptech.com.br"
        )
    return base_url.rstrip("/")
