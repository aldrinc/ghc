Designed machine:
- Source documents are kept in a canonical storage layer with metadata, ACLs, versioning, and provenance.
- A controlled ingestion pipeline sends approved document sets into RAGFlow datasets.
- RAGFlow handles parsing, chunking, indexing, retrieval, citation context, and dataset management.
- An internal RAG adapter exposes a stable API to applications and agents.
- The adapter can call DeepSeek for generation while using RAGFlow for retrieval.
- Gemini File Search and Claude Projects remain comparison baselines until RAGFlow passes evaluation.
