from __future__ import annotations

import time
from typing import Callable, Literal

from halflist.client import HalflistClient
from halflist.models import CheckResult, SuiteResult


class CheckSuite:
    name: str = ""

    def __init__(
        self,
        client: HalflistClient,
        on_check: Callable[[CheckResult], None] | None = None,
    ) -> None:
        self.client = client
        self.results: list[CheckResult] = []
        self._on_check = on_check

    def record(
        self,
        name: str,
        status: Literal["PASS", "FAIL", "WARN", "SKIP"],
        message: str | None = None,
        duration_ms: float = 0.0,
    ) -> None:
        check = CheckResult(
            name=name,
            status=status,
            message=message,
            duration_ms=duration_ms,
            suite=self.name,
        )
        self.results.append(check)
        if self._on_check:
            self._on_check(check)

    async def run(self) -> SuiteResult:
        raise NotImplementedError

    def build_result(self, duration_ms: float) -> SuiteResult:
        return SuiteResult(
            name=self.name,
            checks=self.results,
            passed=sum(1 for c in self.results if c.status == "PASS"),
            failed=sum(1 for c in self.results if c.status == "FAIL"),
            warned=sum(1 for c in self.results if c.status == "WARN"),
            skipped=sum(1 for c in self.results if c.status == "SKIP"),
            duration_ms=duration_ms,
        )

    @staticmethod
    def measure() -> float:
        return time.monotonic()
