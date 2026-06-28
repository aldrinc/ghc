# RAGFlow BGE-M3 Parallel Retrieval Plan

Goal: add a parallel RAGFlow retrieval path so MOS can query RAGFlow-indexed documents with local/open-source embeddings and rerankers, then generate grounded answers with an approved DeepSeek model.

- Add backend configuration for an explicit RAGFlow path, including enablement, base URL, API key, default dataset IDs, optional rerank ID, retrieval tuning, and generation model.
- Add a RAGFlow retrieval service that calls `POST /api/v1/retrieval`, validates configuration, normalizes chunks/citations, and fails loudly when required config or datasets are missing.
- Add `/ragflow/retrieve` and `/ragflow/chat/stream` endpoints that mirror existing Gemini/Claude assistant surfaces without falling back to vendor retrieval.
- Add backend tests for config validation, RAGFlow request payloads, response normalization, and router behavior.
- Update operator-facing env documentation so local BGE-M3 embedding and rerank setup is discoverable without changing existing Gemini/Claude paths.
- Produce proof artifacts: source manifest, lane proof, command logs, plan contract verification, and proof dashboard.

Parallelism:
- parallelizable: yes, but native sub-agents are blocked by active tool policy.
- parallelization map: local parallel reads/source capture; main thread owns implementation and verification.
- expected speed gain: local parallel tools reduce read/source-capture time without risking overlapping writes.
- token spend justification: no native sub-agents used.
- write ownership: main thread only for backend service/router/config/tests/docs.
- fan-in plan: main thread integrates and verifies.
- validation owner: main thread.
- meta-tooling opportunity: if more RAG providers are added, extract a shared retrieval-provider interface after this first path is proven.
