from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection: sqlite3.Connection | None = None

    @property
    def connection(self) -> sqlite3.Connection:
        if self._connection is None:
            self._connection = sqlite3.connect(self.path, check_same_thread=False)
            self._connection.row_factory = sqlite3.Row
        return self._connection

    def execute(self, sql: str, parameters: Iterable[object] = ()) -> sqlite3.Cursor:
        cursor = self.connection.execute(sql, tuple(parameters))
        self.connection.commit()
        return cursor

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None
