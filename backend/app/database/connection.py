from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from threading import RLock
from typing import Iterable


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection: sqlite3.Connection | None = None
        self._lock = RLock()

    @property
    def connection(self) -> sqlite3.Connection:
        if self._connection is None:
            self._connection = sqlite3.connect(self.path, check_same_thread=False)
            self._connection.row_factory = sqlite3.Row
            self._connection.execute("PRAGMA foreign_keys = ON")
        return self._connection

    @contextmanager
    def transaction(self):
        with self._lock:
            connection = self.connection
            try:
                connection.execute("BEGIN IMMEDIATE")
                yield connection
            except Exception:
                connection.rollback()
                raise
            else:
                connection.commit()

    def execute(self, sql: str, parameters: Iterable[object] = ()) -> sqlite3.Cursor:
        with self._lock:
            cursor = self.connection.execute(sql, tuple(parameters))
            self.connection.commit()
            return cursor

    def fetchone(self, sql: str, parameters: Iterable[object] = ()) -> sqlite3.Row | None:
        with self._lock:
            return self.connection.execute(sql, tuple(parameters)).fetchone()

    def fetchall(self, sql: str, parameters: Iterable[object] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self.connection.execute(sql, tuple(parameters)).fetchall()

    def close(self) -> None:
        with self._lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None
