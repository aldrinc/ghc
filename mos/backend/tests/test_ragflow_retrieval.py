from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.services import ragflow_retrieval as ragflow_service


class _FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise ragflow_service.httpx.HTTPStatusError(
                "bad status",
                request=ragflow_service.httpx.Request("POST", "http://ragflow/api/v1/retrieval"),
                response=ragflow_service.httpx.Response(self.status_code),
            )

    def json(self) -> dict:
        return self._payload


class _FakeClient:
    instances: list[_FakeClient] = []

    def __init__(self, *, timeout: float) -> None:
        self.timeout = timeout
        self.calls: list[dict] = []
        _FakeClient.instances.append(self)

    def __enter__(self) -> _FakeClient:
        return self

    def __exit__(self, *_args) -> None:
        return None

    def post(self, url: str, *, headers: dict, json: dict) -> _FakeResponse:
        self.calls.append({"url": url, "headers": headers, "json": json})
        return _FakeResponse(
            {
                "code": 0,
                "data": {
                    "chunks": [
                        {
                            "id": "chunk-1",
                            "content": "RAGFlow context text",
                            "kb_id": "dataset-1",
                            "document_id": "doc-1",
                            "document_keyword": "doc.txt",
                            "similarity": 0.91,
                            "vector_similarity": 0.88,
                            "term_similarity": 0.95,
                        }
                    ],
                    "doc_aggs": [{"doc_id": "doc-1", "doc_name": "doc.txt", "count": 1}],
                    "total": 1,
                },
            }
        )


def test_build_retrieval_payload_uses_bge_rerank_config() -> None:
    config = ragflow_service.RagflowRetrievalConfig(
        enabled=True,
        base_url="http://127.0.0.1:9380",
        api_key="secret",
        default_dataset_ids=("dataset-1",),
        default_rerank_id="bge-reranker-local",
    )

    payload = ragflow_service.build_retrieval_payload(
        question=" What does this say? ",
        config=config,
    )

    assert payload["question"] == "What does this say?"
    assert payload["dataset_ids"] == ["dataset-1"]
    assert payload["rerank_id"] == "bge-reranker-local"
    assert payload["top_k"] == 1024
    assert payload["page_size"] == 8


def test_build_retrieval_payload_requires_dataset_or_document_ids() -> None:
    config = ragflow_service.RagflowRetrievalConfig(
        enabled=True,
        base_url="http://127.0.0.1:9380",
        api_key="secret",
    )

    with pytest.raises(ragflow_service.RagflowRetrievalConfigError, match="dataset IDs"):
        ragflow_service.build_retrieval_payload(question="hello", config=config)


def test_retrieve_chunks_posts_to_ragflow_and_normalizes_response(monkeypatch) -> None:
    _FakeClient.instances = []
    monkeypatch.setattr(ragflow_service.httpx, "Client", _FakeClient)
    config = ragflow_service.RagflowRetrievalConfig(
        enabled=True,
        base_url="http://ragflow.local:9380",
        api_key="ragflow-key",
        default_dataset_ids=("dataset-1",),
        default_rerank_id="bge-reranker-local",
    )

    result = ragflow_service.retrieve_chunks(question="find context", config=config)

    assert result.total == 1
    assert result.chunks[0].content == "RAGFlow context text"
    assert result.chunks[0].dataset_id == "dataset-1"
    assert result.citations()[0]["chunk_id"] == "chunk-1"
    call = _FakeClient.instances[0].calls[0]
    assert call["url"] == "http://ragflow.local:9380/api/v1/retrieval"
    assert call["headers"]["Authorization"] == "Bearer ragflow-key"
    assert call["json"]["rerank_id"] == "bge-reranker-local"


def test_ragflow_retrieve_endpoint_returns_chunks(monkeypatch, api_client) -> None:
    from app.routers import ragflow as ragflow_router

    monkeypatch.setattr(
        ragflow_router,
        "retrieve_chunks",
        lambda **_kwargs: SimpleNamespace(
            chunks=[
                ragflow_service.RagflowChunk(
                    id="chunk-1",
                    content="context",
                    dataset_id="dataset-1",
                    document_id="doc-1",
                    document_name="doc.txt",
                    similarity=0.9,
                )
            ],
            doc_aggs=[],
            total=1,
            request={"question": "hello"},
            citations=lambda: [{"index": 1, "chunk_id": "chunk-1"}],
        ),
    )

    response = api_client.post(
        "/ragflow/retrieve",
        json={"prompt": "hello", "datasetIds": ["dataset-1"]},
    )

    assert response.status_code == 200
    assert response.json()["chunks"][0]["id"] == "chunk-1"
    assert response.json()["citations"][0]["chunk_id"] == "chunk-1"


def test_ragflow_chat_stream_yields_retrieval_then_text(monkeypatch, api_client) -> None:
    from app.routers import ragflow as ragflow_router

    result = ragflow_service.RagflowRetrieveResult(
        chunks=[
            ragflow_service.RagflowChunk(
                id="chunk-1",
                content="retrieved context",
                dataset_id="dataset-1",
                document_name="doc.txt",
            )
        ],
        doc_aggs=[],
        total=1,
        request={"question": "hello"},
    )
    monkeypatch.setattr(
        ragflow_router,
        "get_ragflow_config",
        lambda: SimpleNamespace(generation_model="deepseek:test"),
    )
    monkeypatch.setattr(ragflow_router, "_retrieve", lambda _request: result)
    monkeypatch.setattr(
        ragflow_router.LLMClient,
        "stream_text",
        lambda self, prompt, params=None: iter(["answer"]),
    )

    response = api_client.post(
        "/ragflow/chat/stream",
        json={"prompt": "hello", "datasetIds": ["dataset-1"], "model": "deepseek:test"},
    )

    assert response.status_code == 200
    body = response.text
    assert '"type":"retrieval"' in body
    assert '"type":"text","text":"answer"' in body
    assert '"type":"done"' in body


def test_ragflow_config_endpoint_hides_api_key(monkeypatch, api_client) -> None:
    from app.routers import ragflow as ragflow_router

    monkeypatch.setattr(ragflow_router, "is_ragflow_retrieval_enabled", lambda: True)
    monkeypatch.setattr(
        ragflow_router,
        "get_ragflow_config",
        lambda: SimpleNamespace(
            base_url="http://127.0.0.1:9380",
            api_key="secret",
            default_dataset_ids=("dataset-1",),
            default_document_ids=(),
            default_rerank_id="bge-reranker-local",
            page_size=8,
            top_k=1024,
            similarity_threshold=0.2,
            vector_similarity_weight=0.3,
            keyword_enabled=False,
            highlight_enabled=False,
            generation_model="deepseek:deepseek-v4-pro",
        ),
    )

    response = api_client.get("/ragflow/config")

    assert response.status_code == 200
    payload = response.json()
    assert payload["api_key_configured"] is True
    assert "secret" not in json.dumps(payload)
