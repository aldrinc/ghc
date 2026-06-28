RAGFlow retrieval lane repo inspection:

- Existing assistant surfaces live in `mos/backend/app/routers/gemini.py` and `mos/backend/app/routers/claude.py`.
- Existing provider-specific retrieval logic is isolated in services, especially `mos/backend/app/services/gemini_file_search.py`.
- Route registration is centralized in `mos/backend/app/main.py` and `mos/backend/app/routers/__init__.py`.
- Focused tests belong under `mos/backend/tests`.
- Main implementation should mirror the existing assistant pattern while keeping RAGFlow retrieval separate from Gemini and Claude.
