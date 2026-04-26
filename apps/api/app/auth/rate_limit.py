from collections import deque
from collections.abc import Callable
from datetime import UTC, datetime, timedelta


class InMemoryRateLimiter:
    def __init__(
        self,
        *,
        max_attempts: int,
        window_seconds: int,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.max_attempts = max_attempts
        self.window = timedelta(seconds=window_seconds)
        self.clock = clock or (lambda: datetime.now(UTC))
        self.attempts: dict[str, deque[datetime]] = {}

    def allow(self, key: str) -> bool:
        now = self.clock()
        window_start = now - self.window
        bucket = self.attempts.setdefault(key, deque())
        while bucket and bucket[0] <= window_start:
            bucket.popleft()
        if len(bucket) >= self.max_attempts:
            return False
        bucket.append(now)
        return True
