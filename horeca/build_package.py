#!/usr/bin/env python3
"""Crea un pacchetto Aruba isolato, senza configurazioni o dati personali."""

from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path


def build(repository: Path, destination: Path) -> None:
    source = repository / "horeca"
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    for name in ("api", "src", "config", "database"):
        shutil.copytree(
            source / name,
            destination / name,
            ignore=shutil.ignore_patterns("local.php", "*.json", "*.db", "*.sqlite"),
        )
    shutil.copy2(source / ".htaccess", destination / ".htaccess")
    webapp = destination / "webapp"
    shutil.copytree(repository / "webapp", webapp)
    for html in webapp.glob("*.html"):
        text = html.read_text(encoding="utf-8")
        text = text.replace("fetch('/api/", "fetch('/horeca/api/")
        text = text.replace("fetch(`/api/", "fetch(`/horeca/api/")
        text = re.sub(
            r"const API_BASE_URL = window\.location\.hostname\.includes\('github\.io'\)\s*\?[^;]+;",
            "const API_BASE_URL = '/horeca';",
            text,
            flags=re.DOTALL,
        )
        html.write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    build(Path(__file__).resolve().parents[1], args.destination.resolve())


if __name__ == "__main__":
    main()
