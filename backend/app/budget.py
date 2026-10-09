from __future__ import annotations

import time

from app.config import Settings
from app.models import BudgetSnapshot


class BudgetTracker:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._start = time.monotonic()
        self.llm_rounds = 0
        self.tool_calls = 0

    def snapshot(self) -> BudgetSnapshot:
        elapsed = time.monotonic() - self._start
        exceeded = False
        reason: str | None = None
        if self.llm_rounds >= self._settings.max_llm_rounds:
            exceeded, reason = True, "max_llm_rounds"
        elif self.tool_calls >= self._settings.max_tool_calls:
            exceeded, reason = True, "max_tool_calls"
        elif elapsed >= self._settings.max_wall_seconds:
            exceeded, reason = True, "max_wall_seconds"
        return BudgetSnapshot(
            llm_rounds=self.llm_rounds,
            tool_calls=self.tool_calls,
            elapsed_seconds=round(elapsed, 2),
            exceeded=exceeded,
            reason=reason,
        )

    def check_or_raise(self) -> BudgetSnapshot:
        snap = self.snapshot()
        if snap.exceeded:
            raise BudgetExceeded(snap)
        return snap

    def inc_llm(self) -> None:
        self.llm_rounds += 1

    def inc_tool(self) -> None:
        self.tool_calls += 1


class BudgetExceeded(Exception):
    def __init__(self, snapshot: BudgetSnapshot) -> None:
        self.snapshot = snapshot
        super().__init__(snapshot.reason or "budget_exceeded")
