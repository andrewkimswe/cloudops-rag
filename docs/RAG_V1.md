# RAG v1

Phase 5 implements the first minimal end-to-end RAG flow:

```text
Official document URL
  -> fetch HTML
  -> clean markdown-like text
  -> load processed documents with metadata
  -> character chunking
  -> OpenAI embeddings
  -> Chroma collection
  -> top-k retrieval
  -> OpenAI answer generation
  -> answer with sources
```

## Corpus Ingestion

The ingestion scripts use only URLs listed in `data/manifests/documents.csv`.

Raw HTML is written under `data/raw/{provider}/`.

Processed markdown-like text and metadata JSON are written under `data/processed/{provider}/`.

The cleaner removes common navigation and page chrome elements such as `nav`, `footer`, `header`, `aside`, `script`, `style`, and table-of-contents-like elements. It preserves headings, paragraphs, list items, code text, and row text in a simple markdown-like format.

## Baseline Chunking

Baseline settings:

- `chunk_size=512`
- `chunk_overlap=0`
- unit: character

Chunk metadata preserves:

- `doc_id`
- `title`
- `provider`
- `category`
- `source_url`
- internal `chunk_id`
- internal `chunk_index`

Retrieval evaluation ground truth remains `doc_id`, not `chunk_id`.

## Baseline Embedding

RAG v1 uses OpenAI `text-embedding-3-small`.

The API key is read only from `OPENAI_API_KEY`.

## Chroma

Default collection:

```text
cloudops_rag_v1
```

Default persist directory:

```text
./indexes/chroma
```

The ingestion script resets the collection before indexing so repeated ingestion does not accumulate duplicate chunks.

## Retrieval

Baseline retrieval:

- `top_k=3`

Retrieval returns explicit result objects containing:

- query-side rank
- retrieved `doc_id`
- `chunk_id`
- title
- source URL
- provider
- category
- chunk text
- Chroma distance score when available

## Generation

RAG v1 uses OpenAI `gpt-4o-mini`.

The prompt instructs the model to answer only from retrieved official documentation context and to say when the context is insufficient. Similarity threshold fallback is not implemented in Phase 5.

