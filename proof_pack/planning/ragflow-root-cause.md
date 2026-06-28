Working root cause:
- Retrieval infrastructure and model choice are coupled to vendor products instead of separated behind a RAG service layer.

System diagnosis:
- This is a design flaw, not a model problem.
- The current machine optimizes for fast use inside each vendor UI/API, but not for portable retrieval across DeepSeek, Gemini, Claude, and self-hosted models.
- A model swap alone will not solve it. The system needs a canonical corpus, ingestion contract, retrieval API, and evaluation harness.
