#!/usr/bin/env python3
"""Converte l'export JSON verificato in INSERT MySQL idempotenti."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

TABLE_ORDER = (
    "users", "posts", "banned_words", "stats_daily", "bot_settings",
    "candidate_profiles", "job_offers", "applications", "security_events",
    "payment_events",
)
DATETIME_FIELDS = {
    "joined_at", "last_post", "created_at", "updated_at", "featured_until",
    "premium_until", "promotion_ended_at",
}


def literal(value, column: str) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if column in DATETIME_FIELDS:
        text = text.replace("T", " ")[:19]
    if text == "":
        return "''"
    return "CONVERT(0x" + text.encode("utf-8").hex() + " USING utf8mb4)"


def convert(source: Path, destination: Path, database: str | None = None) -> dict[str, int]:
    payload = json.loads(source.read_text(encoding="utf-8"))
    if payload.get("format") != 1 or not isinstance(payload.get("tables"), dict):
        raise ValueError("Formato export non valido")
    lines = []
    if database:
        if not re.fullmatch(r"[A-Za-z0-9_]+", database):
            raise ValueError("Nome database non valido")
        lines.append(f"USE `{database}`;")
    lines.extend(["SET NAMES utf8mb4;", "SET FOREIGN_KEY_CHECKS=0;", "START TRANSACTION;"])
    counts = {}
    for table in TABLE_ORDER:
        rows = payload["tables"].get(table, [])
        counts[table] = len(rows)
        for row in rows:
            columns = list(row)
            names = ",".join(f"`{name}`" for name in columns)
            values = ",".join(literal(row[name], name) for name in columns)
            updates = ",".join(f"`{name}`=VALUES(`{name}`)" for name in columns)
            lines.append(f"INSERT INTO `{table}` ({names}) VALUES ({values}) ON DUPLICATE KEY UPDATE {updates};")
    lines.extend(["COMMIT;", "SET FOREIGN_KEY_CHECKS=1;"])
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return counts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--database")
    args = parser.parse_args()
    print(json.dumps(convert(args.source, args.destination, args.database), indent=2))


if __name__ == "__main__":
    main()
