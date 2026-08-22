"""Load and validate the official document manifest."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


REQUIRED_COLUMNS = [
    "doc_id",
    "title",
    "provider",
    "category",
    "source_url",
    "status",
    "local_path",
]


@dataclass(frozen=True)
class ManifestDocument:
    doc_id: str
    title: str
    provider: str
    category: str
    source_url: str
    status: str
    local_path: str

    @property
    def metadata(self) -> dict[str, str]:
        return {
            "doc_id": self.doc_id,
            "title": self.title,
            "provider": self.provider,
            "category": self.category,
            "source_url": self.source_url,
        }


def load_manifest(path: Path) -> list[ManifestDocument]:
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != REQUIRED_COLUMNS:
            raise ValueError(f"Unexpected manifest schema: {reader.fieldnames}")

        rows = []
        for row in reader:
            missing = [column for column in REQUIRED_COLUMNS if row.get(column) is None]
            if missing:
                raise ValueError(f"Manifest row has missing columns: {missing}")
            rows.append(
                ManifestDocument(
                    doc_id=row["doc_id"].strip(),
                    title=row["title"].strip(),
                    provider=row["provider"].strip(),
                    category=row["category"].strip(),
                    source_url=row["source_url"].strip(),
                    status=row["status"].strip(),
                    local_path=row["local_path"].strip(),
                )
            )

    doc_ids = [row.doc_id for row in rows]
    if len(doc_ids) != len(set(doc_ids)):
        raise ValueError("Manifest contains duplicate doc_id values")
    return rows

