"""Lokaler Cache (SQLite). Schont die API und macht Analysen reproduzierbar."""
from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from pathlib import Path

from ..models import Publication


class Store:
    def __init__(self, path: str | Path = "simap_cache.db") -> None:
        self.conn = sqlite3.connect(str(path))
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS publications ("
            "id TEXT PRIMARY KEY, date TEXT, canton TEXT, category TEXT, raw TEXT)"
        )
        self.conn.commit()

    def upsert(self, pubs: Iterable[Publication]) -> int:
        n = 0
        for p in pubs:
            if not p.id:
                continue
            self.conn.execute(
                "INSERT OR REPLACE INTO publications VALUES (?,?,?,?,?)",
                (p.id, p.date, p.canton, p.category, json.dumps(p.to_dict())),
            )
            n += 1
        self.conn.commit()
        return n

    def load(self) -> list[Publication]:
        rows = self.conn.execute("SELECT raw FROM publications").fetchall()
        return [Publication(**json.loads(r[0])) for r in rows]

    def close(self) -> None:
        self.conn.close()
