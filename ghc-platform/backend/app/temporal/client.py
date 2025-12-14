from temporalio.client import Client

from app.config import settings

_client: Client | None = None


async def get_temporal_client() -> Client:
    global _client
    if _client is None:
        _client = await Client.connect("localhost:7234", namespace=settings.TEMPORAL_NAMESPACE)
    return _client
