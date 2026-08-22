"""Runtime settings for the RAG v1 pipeline."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def load_dotenv_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


@dataclass(frozen=True)
class Settings:
    project_root: Path
    manifest_path: Path
    raw_dir: Path
    processed_dir: Path
    chroma_persist_dir: Path
    chroma_collection: str
    embedding_model: str
    llm_model: str
    chunk_size: int
    chunk_overlap: int
    retrieval_top_k: int
    runtime_status_path: Path
    openai_api_key: str | None

    @classmethod
    def from_env(cls) -> "Settings":
        project_root = Path(os.getenv("PROJECT_ROOT", ".")).resolve()
        load_dotenv_file(project_root / ".env")
        return cls(
            project_root=project_root,
            manifest_path=project_root / "data" / "manifests" / "documents.csv",
            raw_dir=project_root / "data" / "raw",
            processed_dir=project_root / "data" / "processed",
            chroma_persist_dir=Path(
                os.getenv("CHROMA_PERSIST_DIR", str(project_root / "indexes" / "chroma"))
            ).resolve(),
            chroma_collection=os.getenv("CHROMA_COLLECTION", "cloudops_rag_v1"),
            embedding_model=os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
            llm_model=os.getenv("OPENAI_LLM_MODEL", "gpt-4o-mini"),
            chunk_size=int(os.getenv("CHUNK_SIZE", "512")),
            chunk_overlap=int(os.getenv("CHUNK_OVERLAP", "0")),
            retrieval_top_k=int(os.getenv("RETRIEVAL_TOP_K", "3")),
            runtime_status_path=Path(
                os.getenv("RUNTIME_STATUS_PATH", str(project_root / "data" / "runtime" / "document_status.json"))
            ).resolve(),
            openai_api_key=os.getenv("OPENAI_API_KEY"),
        )
