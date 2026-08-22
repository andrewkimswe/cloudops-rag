"""Fetch and clean official corpus documents."""

from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlparse

from cloudops_rag.ingestion.html_cleaner import html_to_text
from cloudops_rag.ingestion.manifest import ManifestDocument


USER_AGENT = "cloudops-rag-assistant/0.1 (+portfolio project)"


@dataclass(frozen=True)
class FetchResult:
    source_url: str
    final_url: str
    content_type: str
    body: str


def fetch_url(url: str, timeout: int = 30) -> str:
    return fetch_html(url, timeout=timeout).body


def fetch_html(url: str, timeout: int = 30) -> FetchResult:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("source_url must be an absolute http(s) URL")
    try:
        import certifi

        context = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        context = ssl.create_default_context()
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
        final_url = response.geturl()
        final_scheme = urlparse(final_url).scheme
        if final_scheme not in {"http", "https"}:
            raise ValueError("redirected URL uses an unsupported scheme")
        content_type = response.headers.get_content_type()
        if content_type not in {"text/html", "application/xhtml+xml"}:
            raise ValueError(f"unsupported content type: {content_type}")
        charset = response.headers.get_content_charset() or "utf-8"
        body = response.read().decode(charset, errors="replace")
        return FetchResult(source_url=url, final_url=final_url, content_type=content_type, body=body)


def write_document_files(
    document: ManifestDocument,
    raw_dir: Path,
    processed_dir: Path,
    timeout: int = 30,
) -> dict[str, str]:
    provider_raw_dir = raw_dir / document.provider
    provider_processed_dir = processed_dir / document.provider
    provider_raw_dir.mkdir(parents=True, exist_ok=True)
    provider_processed_dir.mkdir(parents=True, exist_ok=True)

    raw_path = provider_raw_dir / f"{document.doc_id}.html"
    processed_path = provider_processed_dir / f"{document.doc_id}.md"

    html = fetch_url(document.source_url, timeout=timeout)
    raw_path.write_text(html, encoding="utf-8")

    cleaned = html_to_text(html, document.title)
    processed_path.write_text(cleaned, encoding="utf-8")

    metadata_path = provider_processed_dir / f"{document.doc_id}.json"
    metadata_path.write_text(
        json.dumps(
            {
                **asdict(document),
                "raw_path": str(raw_path),
                "processed_path": str(processed_path),
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    return {
        "doc_id": document.doc_id,
        "raw_path": str(raw_path),
        "processed_path": str(processed_path),
        "metadata_path": str(metadata_path),
    }


def fetch_documents(
    documents: list[ManifestDocument],
    raw_dir: Path,
    processed_dir: Path,
    timeout: int = 30,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    successes: list[dict[str, str]] = []
    failures: list[dict[str, str]] = []
    for document in documents:
        try:
            successes.append(write_document_files(document, raw_dir, processed_dir, timeout))
        except (urllib.error.URLError, TimeoutError, OSError, UnicodeError) as exc:
            failures.append(
                {
                    "doc_id": document.doc_id,
                    "source_url": document.source_url,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
    return successes, failures
