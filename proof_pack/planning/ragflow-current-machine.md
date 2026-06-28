Current machine:
- Documents are uploaded into Gemini File Search and Claude Projects.
- Each product performs its own indexing and retrieval.
- Tasks are answered inside the product or API that owns the document context.
- DeepSeek or open-source models do not have first-class access to the same retrieval layer.
- Quality comparison is difficult because model, retriever, chunking, and prompt format change together.
