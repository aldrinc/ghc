from typing import List, Optional
from pydantic import BaseModel


class PlaybookSection(BaseModel):
    title: str
    content: str
    tags: List[str] = []


class Playbook(BaseModel):
    orgId: str
    clientId: Optional[str] = None
    sections: List[PlaybookSection] = []
    version: int = 1
