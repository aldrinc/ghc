import re
from typing import Optional


def sanitize_folder_name(name: Optional[str]) -> str:
    if not name:
        return "idea"
    cleaned = re.sub(r"[\\/:*?\"<>|]+", " ", name).strip()
    return cleaned[:250] if cleaned else "idea"


def build_file_name(*, title: str, workflow_id: str | None, step_key: str) -> str:
    file_name_parts = [title]
    if workflow_id:
        file_name_parts.append(f"workflow-{workflow_id}")
    file_name_parts.append(f"step-{step_key}")
    return " - ".join(file_name_parts)
