from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from openai import InvalidWebhookSignatureError

from app.config import settings
from app.services.deep_research import DeepResearchJobService, build_openai_client

router = APIRouter(prefix="/openai", tags=["openai"])


@router.post("/webhook")
async def openai_webhook(request: Request, background_tasks: BackgroundTasks):
    webhook_secret = settings.OPENAI_WEBHOOK_SECRET
    if not webhook_secret:
        raise HTTPException(status_code=500, detail="OPENAI_WEBHOOK_SECRET not configured")

    raw_body = await request.body()
    headers = dict(request.headers)

    client = build_openai_client(require_api_key=False)
    try:
        event = client.webhooks.unwrap(raw_body, headers, secret=webhook_secret)
    except InvalidWebhookSignatureError:
        raise HTTPException(status_code=400, detail="Invalid webhook signature")
    except Exception as exc:  # pragma: no cover - defensive runtime guard
        raise HTTPException(status_code=400, detail=str(exc))

    webhook_id = headers.get("webhook-id")
    background_tasks.add_task(_process_event_async, event, webhook_id)
    return {"ok": True}


def _process_event_async(event, webhook_id: str | None) -> None:
    service = DeepResearchJobService()
    try:
        service.process_webhook_event(event=event, webhook_id=webhook_id)
    finally:
        try:
            service.session.close()
        except Exception:
            pass
