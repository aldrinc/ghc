RAGFlow retrieval verification summary:

- `cd mos/backend && .venv/bin/pytest tests/test_ragflow_retrieval.py`: passed, 6 tests.
- `cd mos/backend && .venv/bin/pytest tests/test_api.py`: passed, 20 tests.
- `cd mos/backend && .venv/bin/python -m compileall app/services/ragflow_retrieval.py app/routers/ragflow.py app/config.py app/main.py`: passed.
- `cd mos/backend && .venv/bin/ruff check app/services/ragflow_retrieval.py app/routers/ragflow.py tests/test_ragflow_retrieval.py`: passed with existing pyproject deprecation warning.
- `cd mos/backend && .venv/bin/pytest tests/test_config_env_precedence.py tests/test_api.py tests/test_llm_openai_client.py`: blocked by pre-existing unrelated config expectation mismatch on `STRATEGY_V2_FOUNDATIONAL_STEP04_PROVIDER`.
- Live DeepSeek `/models` smoke: passed; the supplied key can access `deepseek-v4-flash` and `deepseek-v4-pro`.
- Live MOS `LLMClient` smoke with `deepseek:deepseek-v4-pro`: passed for non-streaming and streaming generation with `max_tokens=128`.
- Live `/ragflow/chat/stream` smoke with a local fake RAGFlow retrieval server and real DeepSeek generation: passed; events were retrieval, start, text chunks, and done with no error event.
- Local Ollama BGE-M3: running in Docker on `127.0.0.1:11434`; embedding smoke returned a 1024-dimension vector.
- Local RAGFlow: running in Docker on `127.0.0.1:9380` with Infinity, MySQL, Redis, and MinIO healthy.
- Local RAGFlow auth block: fixed by seeding a valid local `access_token` for the default admin user; dataset/document APIs then accepted the local API token.
- True local RAGFlow indexed retrieval: passed. Created a dataset using `bge-m3@Ollama`, uploaded `ragflow-local-smoke-doc.txt`, parsed it, and retrieved the sentinel chunk. Proof: `ragflow-local-smoke-result.json`.
- Live MOS backend + RAGFlow + DeepSeek smoke: passed. `retrieve_chunks` returned the local RAGFlow chunk, and `deepseek:deepseek-v4-pro` streamed an answer containing the retrieved sentinel. Proof: `mos-backend-ragflow-deepseek-smoke-result.json`.
