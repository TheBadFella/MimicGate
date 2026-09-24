"""
Runtime telemetry and request activity logging for MimicGate Gateway.

Maintains rolling request activity logs and latency metrics for the
Live Multi-Tab Preview Dashboard.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(slots=True)
class RequestLogEntry:
    id: str
    timestamp: float
    time_str: str
    method: str
    path: str
    model: str
    status_code: int
    duration_ms: float
    client_ip: str
    prompt_preview: str = ""
    response_preview: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TelemetryTracker:
    """In-memory rolling telemetry store for gateway requests."""

    def __init__(self, maxlen: int = 50) -> None:
        self._history: deque[RequestLogEntry] = deque(maxlen=maxlen)
        self._total_requests: int = 0
        self._successful_requests: int = 0
        self._failed_requests: int = 0
        self._total_duration_ms: float = 0.0
        self._in_flight: int = 0

    def request_started(self) -> None:
        self._in_flight += 1

    def request_finished(self) -> None:
        if self._in_flight > 0:
            self._in_flight -= 1

    def record_request(
        self,
        method: str,
        path: str,
        model: str,
        status_code: int,
        duration_ms: float,
        client_ip: str = "127.0.0.1",
        prompt_preview: str = "",
        response_preview: str = "",
    ) -> RequestLogEntry:
        self._total_requests += 1
        if 200 <= status_code < 400:
            self._successful_requests += 1
        else:
            self._failed_requests += 1
        self._total_duration_ms += duration_ms

        entry_id = f"req-{self._total_requests:04d}"
        now = time.time()
        time_str = time.strftime("%H:%M:%S", time.localtime(now))

        entry = RequestLogEntry(
            id=entry_id,
            timestamp=now,
            time_str=time_str,
            method=method.upper(),
            path=path,
            model=model or "default",
            status_code=status_code,
            duration_ms=round(duration_ms, 1),
            client_ip=client_ip,
            prompt_preview=prompt_preview[:120] if prompt_preview else "",
            response_preview=response_preview[:120] if response_preview else "",
        )
        self._history.appendleft(entry)
        return entry

    def get_summary(self) -> dict[str, Any]:
        avg_latency = (
            round(self._total_duration_ms / self._total_requests, 1)
            if self._total_requests > 0
            else 0.0
        )
        success_rate = (
            round((self._successful_requests / self._total_requests) * 100, 1)
            if self._total_requests > 0
            else 100.0
        )
        return {
            "total_requests": self._total_requests,
            "successful_requests": self._successful_requests,
            "failed_requests": self._failed_requests,
            "success_rate_percent": success_rate,
            "avg_latency_ms": avg_latency,
            "in_flight": self._in_flight,
        }

    def get_recent_requests(self, limit: int = 30) -> list[dict[str, Any]]:
        entries = list(self._history)[:limit]
        return [e.to_dict() for e in entries]


# Global telemetry singleton
telemetry = TelemetryTracker(maxlen=50)
