Worst-day test:
- A bad PDF parse, stale index, missing ACL, or weak chunking choice should fail visibly, not silently produce confident wrong answers.
- If DeepSeek output quality drops, the system should identify whether the failure came from retrieval, prompt assembly, model behavior, or missing source data.
- If RAGFlow is unavailable, high-value workflows should either degrade to an approved existing provider or fail cleanly with a clear operator message, depending on task criticality.
