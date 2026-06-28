Observable problems:
- Current RAG context is split across Gemini File Search and Claude Projects, which makes retrieval behavior tool-specific.
- DeepSeek cannot use Claude Projects directly, and Gemini File Search is tied to Gemini workflows.
- Document ingestion, chunking, citation behavior, permissions, and evaluation are not centralized behind one service boundary.
- Switching models risks changing both retrieval and generation at once, making quality regressions hard to diagnose.
