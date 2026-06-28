Goal: define a vendor-neutral RAG architecture that lets the system run retrieval-backed tasks with DeepSeek and future open-source models, while preserving the useful parts of Gemini File Search and Claude Projects during migration.

Key results:
- One canonical document ingestion path can feed RAGFlow datasets.
- One app-facing RAG API can route answer generation to DeepSeek or another approved model without changing application workflows.
- Evaluation compares Gemini File Search, Claude Projects, and RAGFlow on the same task set before migration decisions.

Timeframe: planning outline now; technical spike over 1-2 weeks after credentials, corpus sample, and acceptance tasks are selected.
