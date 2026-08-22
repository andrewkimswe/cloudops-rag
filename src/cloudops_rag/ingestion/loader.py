"""Load processed corpus documents with metadata."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CorpusDocument:
    page_content: str
    metadata: dict[str, str]


def load_processed_documents(processed_dir: Path) -> list[CorpusDocument]:
    metadata_files = sorted(processed_dir.glob("*/*.json"))
    documents: list[CorpusDocument] = []
    for metadata_path in metadata_files:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        processed_path = Path(metadata["processed_path"])
        if not processed_path.exists():
            raise FileNotFoundError(f"Processed text not found: {processed_path}")
        documents.append(
            CorpusDocument(
                page_content=processed_path.read_text(encoding="utf-8"),
                metadata={
                    "doc_id": metadata["doc_id"],
                    "title": metadata["title"],
                    "provider": metadata["provider"],
                    "category": metadata["category"],
                    "source_url": metadata["source_url"],
                },
            )
        )
    return documents

