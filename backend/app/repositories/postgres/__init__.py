"""PostgreSQL-backed repository implementations.

Each class here satisfies the same `Protocol` as its counterpart in
`repositories.mock`, so swapping between them is a decision made once in
`app.dependencies` and nowhere else.

TRANSACTION OWNERSHIP
---------------------
No repository in this package calls `commit()`. The session dependency opens a
transaction per request and commits it once, so a handler that writes to two
tables either persists both or neither. A repository that committed on its own
would make that guarantee impossible to offer. Repositories `flush()` only when
they need a generated key before the transaction ends.
"""

from __future__ import annotations

from app.repositories.postgres.performance_repository import (
    PostgresPerformanceRepository,
)
from app.repositories.postgres.target_repository import PostgresTargetRepository

__all__ = ["PostgresPerformanceRepository", "PostgresTargetRepository"]
