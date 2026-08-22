from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from cloudops_rag.chunking.chunker import chunk_documents
from cloudops_rag.chunking.chunker import DocumentChunk
from cloudops_rag.generation.rag_service import deduplicate_sources
from cloudops_rag.ingestion.html_cleaner import html_to_text
from cloudops_rag.ingestion.loader import CorpusDocument
from cloudops_rag.ingestion.manifest import load_manifest
from cloudops_rag.retrieval.schemas import RetrievedChunk


def test_manifest_loading():
    documents = load_manifest(Path("data/manifests/documents.csv"))
    assert len(documents) == 20
    assert documents[0].doc_id == "k8s_debug_pods"
    assert documents[0].metadata["source_url"].startswith("https://")


def test_html_cleaner_removes_navigation_and_keeps_content():
    html = """
    <html><body>
      <nav>Navigation noise</nav>
      <main><h1>Debug Pods</h1><p>Use kubectl describe pod to inspect events.</p></main>
      <footer>Footer noise</footer>
    </body></html>
    """
    text = html_to_text(html, "Debug Pods")
    assert "Navigation noise" not in text
    assert "Footer noise" not in text
    assert "# Debug Pods" in text
    assert "kubectl describe pod" in text


def test_chunking_preserves_doc_id_metadata():
    document = CorpusDocument(
        page_content="A" * 1200,
        metadata={
            "doc_id": "k8s_debug_pods",
            "title": "Debug Pods",
            "provider": "kubernetes",
            "category": "pod_troubleshooting",
            "source_url": "https://kubernetes.io/example",
        },
    )
    chunks = chunk_documents([document], chunk_size=512, chunk_overlap=0)
    assert len(chunks) == 3
    assert chunks[0].metadata["doc_id"] == "k8s_debug_pods"
    assert chunks[0].metadata["chunk_unit"] == "character"


def test_source_mapping_deduplicates_by_doc_id():
    chunks = [
        RetrievedChunk(1, "doc-a", "Doc A", "https://a", "aws", "cat", "doc-a::0000", "a", 0.1),
        RetrievedChunk(2, "doc-a", "Doc A", "https://a", "aws", "cat", "doc-a::0001", "b", 0.2),
        RetrievedChunk(3, "doc-b", "Doc B", "https://b", "aws", "cat", "doc-b::0000", "c", 0.3),
    ]
    sources = deduplicate_sources(chunks)
    assert [source.doc_id for source in sources] == ["doc-a", "doc-b"]
    assert sources[0].rank == 1


def test_chroma_indexing_and_retrieval_with_fake_embedder():
    pytest.importorskip("chromadb")
    from cloudops_rag.retrieval.chroma_store import ChromaVectorStore

    class FakeEmbedder:
        def _embed(self, text):
            lowered = text.lower()
            return [
                float(lowered.count("pod")),
                float(lowered.count("service")),
                float(lowered.count("autoscaling")),
                1.0,
            ]

        def embed_documents(self, texts):
            return [self._embed(text) for text in texts]

        def embed_query(self, text):
            return self._embed(text)

    chunks = [
        DocumentChunk(
            "k8s_debug_pods::0000",
            "pod pending scheduling describe events",
            {
                "doc_id": "k8s_debug_pods",
                "title": "Debug Pods",
                "provider": "kubernetes",
                "category": "pod_troubleshooting",
                "source_url": "https://kubernetes.io/docs/tasks/debug/debug-application/debug-pods/",
                "chunk_id": "k8s_debug_pods::0000",
                "chunk_index": 0,
            },
        ),
        DocumentChunk(
            "k8s_debug_services::0000",
            "service endpoints selector traffic",
            {
                "doc_id": "k8s_debug_services",
                "title": "Debug Services",
                "provider": "kubernetes",
                "category": "service_troubleshooting",
                "source_url": "https://kubernetes.io/docs/tasks/debug/debug-application/debug-service/",
                "chunk_id": "k8s_debug_services::0000",
                "chunk_index": 0,
            },
        ),
    ]

    with TemporaryDirectory() as tmp:
        store = ChromaVectorStore(Path(tmp), "phase5_test")
        indexed = store.index_chunks(chunks, FakeEmbedder(), reset=True)
        results = store.retrieve("pod is pending", FakeEmbedder(), top_k=1)

    assert indexed == 2
    assert len(results) == 1
    assert results[0].rank == 1
    assert results[0].doc_id == "k8s_debug_pods"
