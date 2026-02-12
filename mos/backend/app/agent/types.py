from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session


class ToolResult(BaseModel):
    """
    Every tool must return:
    - llm_output: compact content intended to go back into the model context
    - ui_details: structured UI-friendly payload (no reverse parsing of text)
    - attachments: optional provider-native attachments (e.g., image urls, doc handles)
    """

    model_config = ConfigDict(extra="forbid")

    llm_output: Any | None = None
    ui_details: dict[str, Any] = Field(default_factory=dict)
    attachments: list[dict[str, Any]] = Field(default_factory=list)


@dataclass(frozen=True)
class ToolContext:
    session: Session
    org_id: str
    user_id: str
    run_id: str
    client_id: Optional[str] = None
    funnel_id: Optional[str] = None
    page_id: Optional[str] = None

