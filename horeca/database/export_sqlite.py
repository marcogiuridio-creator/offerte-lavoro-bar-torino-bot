#!/usr/bin/env python3
"""Esporta il database Railway SQLite in JSON verificabile, senza segreti."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path

TABLES = (
    "users", "posts", "banned_words", "stats_daily", "bot_settings",
    "candidate_profiles", "job_offers", "applications", "security_events",
    "payment_events",
)


def export_database(source: Path, destination: Path) -> dict:
    connection = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise RuntimeError(f"SQLite integrity_check: {integrity}")
        payload = {"format": 1, "tables": {}}
        counts = {}
        for table in TABLES:
            exists = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
            ).fetchone()
            rows = [] if not exists else [dict(row) for row in connection.execute(f'SELECT * FROM "{table}"')]
            payload["tables"][table] = rows
            counts[table] = len(rows)
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
        destination.write_bytes(encoded)
        return {"integrity": integrity, "counts": counts, "sha256": hashlib.sha256(encoded).hexdigest()}
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    report = export_database(args.source.resolve(), args.destination.resolve())
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

