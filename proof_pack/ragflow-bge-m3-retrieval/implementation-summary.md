RAGFlow retrieval implementation summary:

- Added `mos/backend/app/services/ragflow_retrieval.py` for explicit RAGFlow config validation, retrieval payload construction, HTTP retrieval, chunk normalization, citation serialization, and grounded prompt assembly.
- Added `mos/backend/app/routers/ragflow.py` with `/ragflow/config`, `/ragflow/retrieve`, and `/ragflow/chat/stream`.
- Registered the router in the FastAPI app.
- Added RAGFlow env knobs in backend settings and `.env.example`.
- Added focused tests for payload construction, config failure, request shape, response normalization, endpoint behavior, stream behavior, and secret hiding.
- Adjusted `/ragflow/chat/stream` so DeepSeek generation runs in a worker thread and feeds SSE events through a queue; this preserves real-time text chunks while keeping observability context cleanup out of the StreamingResponse yield context.
- Started local RAGFlow and local Ollama BGE-M3 for the open-source retrieval path; RAGFlow uses `bge-m3@Ollama` for the smoke dataset.
- Fixed the local RAGFlow auth block by seeding a valid admin `access_token`, which allowed API-token authenticated dataset/document calls to pass.
