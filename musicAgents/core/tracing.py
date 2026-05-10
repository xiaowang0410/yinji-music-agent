from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable


EventCallback = Callable[[dict[str, Any]], None] | None


@dataclass
class AgentRunTracker:
    event_cb: EventCallback = None
    started_at: float = field(default_factory=time.perf_counter)
    _marks: dict[str, float] = field(default_factory=dict)

    def emit(self, event: str, **payload: Any) -> None:
        if self.event_cb is None:
            return
        try:
            self.event_cb({"event": event, **payload})
        except Exception:
            pass

    def mark(self, name: str) -> None:
        self._marks[name] = time.perf_counter()

    def elapsed_ms(self) -> int:
        return int((time.perf_counter() - self.started_at) * 1000)

    def stage_done(self, stage: str, *, label: str | None = None, **payload: Any) -> None:
        elapsed = self.elapsed_ms()
        self.emit(
            "stage_timing",
            stage=stage,
            label=label or stage,
            elapsed_ms=elapsed,
            **payload,
        )

    def thought(self, text: str, *, kind: str = "thought", **payload: Any) -> None:
        message = str(text or "").strip()
        if not message:
            return
        self.emit("thought", kind=kind, text=message, elapsed_ms=self.elapsed_ms(), **payload)
