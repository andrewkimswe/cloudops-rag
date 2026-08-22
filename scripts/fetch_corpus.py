#!/usr/bin/env python3
"""Fetch and clean the official corpus without embedding or indexing."""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from cloudops_rag.config.settings import Settings
from cloudops_rag.ingestion.fetch import fetch_documents
from cloudops_rag.ingestion.manifest import load_manifest


def main() -> int:
    settings = Settings.from_env()
    documents = load_manifest(settings.manifest_path)
    successes, failures = fetch_documents(documents, settings.raw_dir, settings.processed_dir)
    print(f"Fetched documents: {len(successes)}/{len(documents)}")
    if failures:
        print(json.dumps(failures, indent=2, ensure_ascii=False))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

