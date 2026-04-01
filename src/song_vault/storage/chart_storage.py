from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class ChartStorageError(Exception):
    """Raised when chart storage operations fail."""


@dataclass(slots=True, frozen=True)
class StoredChartObject:
    bucket: str
    key: str
    size_bytes: int
    content_type: str


@dataclass(slots=True, frozen=True)
class StoredChartBinary:
    content: bytes
    content_type: str


class ChartStorage(Protocol):
    async def ensure_ready(self) -> None: ...

    async def put_chart(
        self,
        *,
        object_key: str,
        content: bytes,
        content_type: str,
    ) -> StoredChartObject: ...

    async def get_chart(self, *, bucket: str, object_key: str) -> StoredChartBinary: ...

    async def delete_chart(self, *, bucket: str, object_key: str) -> None: ...
