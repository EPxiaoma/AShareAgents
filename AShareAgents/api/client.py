"""供 Streamlit 前端使用的同步 HTTP 客户端。"""

from __future__ import annotations

import os
from typing import Any

import requests


class APIError(RuntimeError):
    """后端无法完成前端请求时抛出。"""


class AShareAgentsAPIClient:
    def __init__(self, base_url: str | None = None, timeout: float = 15.0) -> None:
        configured = base_url or os.getenv(
            "ASHAREAGENTS_API_URL", "http://127.0.0.1:8000/api/v1"
        )
        self.base_url = configured.rstrip("/")
        self.timeout = timeout

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> Any:
        try:
            response = requests.request(
                method,
                f"{self.base_url}{path}",
                json=json,
                timeout=timeout or self.timeout,
            )
        except requests.RequestException as exc:
            raise APIError(f"Cannot connect to API at {self.base_url}: {exc}") from exc

        if response.ok:
            return response.json()
        try:
            detail = response.json().get("detail", response.text)
        except ValueError:
            detail = response.text
        raise APIError(f"API request failed ({response.status_code}): {detail}")

    def resolve_ticker(self, query: str) -> str:
        data = self._request("POST", "/tickers/resolve", json={"query": query})
        return str(data["ticker"])

    def start_analysis(
        self,
        ticker: str,
        trade_date: str,
        config: dict[str, Any],
    ) -> str:
        data = self._request(
            "POST",
            "/analyses",
            json={"ticker": ticker, "trade_date": trade_date, "config": config},
        )
        return str(data["task_id"])

    def get_analysis(self, task_id: str) -> dict[str, Any]:
        return self._request("GET", f"/analyses/{task_id}")

    def get_analysis_result(self, task_id: str) -> dict[str, Any]:
        return self._request("GET", f"/analyses/{task_id}/result")

    def get_history(self) -> list[dict[str, str]]:
        entries = self._request("GET", "/history")
        return [{**entry, "path": entry["id"]} for entry in entries]

    def get_history_result(self, history_id: str) -> dict[str, Any]:
        return self._request("GET", f"/history/{history_id}")


def get_api_client() -> AShareAgentsAPIClient:
    return AShareAgentsAPIClient()
