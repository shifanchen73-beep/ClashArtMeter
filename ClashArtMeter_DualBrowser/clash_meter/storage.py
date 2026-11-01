"""User-local session history; supports migration of v1 databases."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

BUCKETS = ('edge', 'chrome', 'unknown')


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


class SessionStore:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute('''CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT NOT NULL,
            ended_at TEXT,
            mode TEXT NOT NULL,
            keywords TEXT NOT NULL,
            upload_bytes INTEGER NOT NULL DEFAULT 0,
            download_bytes INTEGER NOT NULL DEFAULT 0
        )''')
        existing = {row[1] for row in self.db.execute('PRAGMA table_info(sessions)')}
        for bucket in BUCKETS:
            for direction in ('up', 'down'):
                col = f'{bucket}_{direction}'
                if col not in existing:
                    self.db.execute(f'ALTER TABLE sessions ADD COLUMN {col} INTEGER NOT NULL DEFAULT 0')
        self.db.execute('UPDATE sessions SET ended_at = ? WHERE ended_at IS NULL', (utc_now(),))
        self.db.commit()

    def begin(self, mode: str, keywords: str) -> int:
        cur = self.db.execute('INSERT INTO sessions (started_at, mode, keywords) VALUES (?, ?, ?)',
                              (utc_now(), mode, keywords))
        self.db.commit()
        return int(cur.lastrowid)

    def add(self, session_id: int, up: int, down: int,
            breakdown: dict[str, tuple[int, int]] | None = None) -> None:
        if not up and not down:
            return
        breakdown = breakdown or {}
        vals = [int(max(0, v)) for pair in (breakdown.get(k, (0, 0)) for k in BUCKETS)
                for v in pair]
        self.db.execute('''UPDATE sessions SET
            upload_bytes=upload_bytes+?, download_bytes=download_bytes+?,
            edge_up=edge_up+?,edge_down=edge_down+?,
            chrome_up=chrome_up+?,chrome_down=chrome_down+?,
            unknown_up=unknown_up+?,unknown_down=unknown_down+?
            WHERE id=? AND ended_at IS NULL''', (up, down, *vals, session_id))
        self.db.commit()

    def finish(self, session_id: int) -> None:
        self.db.execute('UPDATE sessions SET ended_at = ? WHERE id = ? AND ended_at IS NULL',
                        (utc_now(), session_id))
        self.db.commit()

    def recent(self, limit: int = 150) -> list[tuple]:
        return self.db.execute('''SELECT started_at, ended_at, mode,
            upload_bytes, download_bytes, edge_up, edge_down, chrome_up, chrome_down,
            unknown_up, unknown_down FROM sessions ORDER BY id DESC LIMIT ?''', (limit,)).fetchall()

    def totals(self) -> tuple[int, int, int]:
        return self.db.execute('SELECT COUNT(*), COALESCE(SUM(upload_bytes), 0), '
                               'COALESCE(SUM(download_bytes), 0) FROM sessions').fetchone()

    def close(self) -> None:
        self.db.close()
