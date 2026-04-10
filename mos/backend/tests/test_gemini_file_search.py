from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

from app.services import gemini_file_search as gemini_service


class _FakeType:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs


class _FakeRepo:
    ready_calls: list[dict[str, object]] = []
    failed_calls: list[dict[str, object]] = []

    def __init__(self, _session) -> None:
        pass

    def get_by_doc_key_hash(self, **_kwargs):
        return None

    def upsert_ready(self, **kwargs):
        self.ready_calls.append(kwargs)
        return SimpleNamespace(**kwargs)

    def upsert_failed(self, **kwargs):
        self.failed_calls.append(kwargs)
        return SimpleNamespace(**kwargs)


class _FakeHttpError(RuntimeError):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code


def test_ensure_uploaded_to_gemini_file_search_polls_document_state_from_upload_operation_name(
    monkeypatch,
) -> None:
    expected_document_name = "fileSearchStores/store-1/documents/doc-1"
    poll_paths: list[str] = []
    _FakeRepo.ready_calls = []
    _FakeRepo.failed_calls = []

    class _FakeApiClient:
        def __init__(self) -> None:
            self.document_poll_count = 0

        def request(self, method: str, path: str, _request_dict, _http_options):
            assert method == "get"
            poll_paths.append(path)
            if path != expected_document_name:
                raise AssertionError(f"Unexpected path polled: {path}")
            self.document_poll_count += 1
            if self.document_poll_count == 1:
                raise _FakeHttpError(404, "document not found yet")
            if self.document_poll_count == 2:
                return SimpleNamespace(
                    body=(
                        '{"name":"fileSearchStores/store-1/documents/doc-1",'
                        '"state":"STATE_PENDING","sizeBytes":"0"}'
                    )
                )
            return SimpleNamespace(
                body=(
                    '{"name":"fileSearchStores/store-1/documents/doc-1",'
                    '"state":"STATE_ACTIVE","sizeBytes":"27156"}'
                )
            )

    fake_api_client = _FakeApiClient()

    class _FakeFileSearchStores:
        def __init__(self) -> None:
            self.documents = SimpleNamespace()

        def create(self, *, config):
            assert config is not None
            return SimpleNamespace(name="fileSearchStores/store-1")

        def upload_to_file_search_store(self, *, file_search_store_name, file, config):
            assert file_search_store_name == "fileSearchStores/store-1"
            assert getattr(file, "name", "") == "context.txt"
            assert config is not None
            return SimpleNamespace(
                name="fileSearchStores/store-1/upload/operations/doc-1",
                response=None,
            )

    fake_client = SimpleNamespace(
        _api_client=fake_api_client,
        file_search_stores=_FakeFileSearchStores(),
        operations=SimpleNamespace(
            get=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("upload operation polling should not be used")
            )
        ),
    )

    @contextmanager
    def _fake_session_scope():
        yield object()

    @contextmanager
    def _fake_generation(**_kwargs):
        yield SimpleNamespace(update=lambda **__kwargs: None)

    monkeypatch.setattr(gemini_service, "_require_client", lambda: fake_client)
    monkeypatch.setattr(gemini_service, "GeminiContextFilesRepository", _FakeRepo)
    monkeypatch.setattr(gemini_service, "session_scope", _fake_session_scope)
    monkeypatch.setattr(gemini_service, "start_langfuse_generation", _fake_generation)
    monkeypatch.setattr(gemini_service, "time", SimpleNamespace(time=lambda: 0.0, sleep=lambda _seconds: None))
    monkeypatch.setattr(
        gemini_service,
        "genai_types",
        SimpleNamespace(
            CreateFileSearchStoreConfig=_FakeType,
            UploadToFileSearchStoreConfig=_FakeType,
            CustomMetadata=_FakeType,
        ),
    )

    result = gemini_service.ensure_uploaded_to_gemini_file_search(
        org_id="org-1",
        idea_workspace_id="workspace-1",
        client_id="client-1",
        product_id="product-1",
        campaign_id="campaign-1",
        doc_key="doc-key-1",
        doc_title="Doc Title",
        source_kind="source-kind",
        step_key="step-key",
        filename="context.txt",
        mime_type="text/plain",
        content_bytes=b"hello world",
        drive_doc_id=None,
        drive_url=None,
    )

    assert result == expected_document_name
    assert poll_paths == [expected_document_name, expected_document_name, expected_document_name]
    assert _FakeRepo.failed_calls == []
    assert len(_FakeRepo.ready_calls) == 1
    assert _FakeRepo.ready_calls[0]["gemini_document_name"] == expected_document_name
    assert _FakeRepo.ready_calls[0]["size_bytes"] == 27156

