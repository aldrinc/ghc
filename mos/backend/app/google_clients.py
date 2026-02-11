from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaInMemoryUpload
from google.auth.transport.requests import Request
from google.oauth2 import credentials as oauth2_credentials
from google.oauth2.service_account import Credentials as ServiceAccountCredentials
import google.auth

SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/documents",
]


def _load_service_account_from_file(path: Path) -> Optional[ServiceAccountCredentials]:
    if not path.exists():
        return None
    info = json.loads(path.read_text(encoding="utf-8"))
    if "client_email" in info and "private_key" in info:
        return ServiceAccountCredentials.from_service_account_info(info, scopes=SCOPES)
    return None


def _load_service_account_from_env() -> Optional[ServiceAccountCredentials]:
    email = os.getenv("GOOGLE_CLIENT_EMAIL")
    key = os.getenv("GOOGLE_PRIVATE_KEY")
    if email and key:
        info = {"client_email": email, "private_key": key.replace("\\n", "\n")}
        return ServiceAccountCredentials.from_service_account_info(info, scopes=SCOPES)
    return None


def _load_oauth_credentials() -> Optional[oauth2_credentials.Credentials]:
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    refresh_token = os.getenv("GOOGLE_REFRESH_TOKEN")
    if client_id and client_secret and refresh_token:
        creds = oauth2_credentials.Credentials(
            token=None,
            refresh_token=refresh_token,
            client_id=client_id,
            client_secret=client_secret,
            token_uri="https://oauth2.googleapis.com/token",
            scopes=SCOPES,
        )
        creds.refresh(Request())
        return creds
    return None


def get_google_credentials():
    key_file = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if key_file:
        creds = _load_service_account_from_file(Path(key_file))
        if creds:
            return creds

    creds = _load_service_account_from_env()
    if creds:
        return creds

    creds = _load_oauth_credentials()
    if creds:
        return creds

    # Fall back to Application Default Credentials (e.g., gcloud auth application-default login)
    try:
        creds, _ = google.auth.default(scopes=SCOPES)
        return creds
    except Exception as exc:
        raise RuntimeError(
            "Google auth not configured. Set GOOGLE_APPLICATION_CREDENTIALS or service account envs "
            "(GOOGLE_CLIENT_EMAIL/GOOGLE_PRIVATE_KEY) or OAuth envs "
            "(GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET/GOOGLE_REFRESH_TOKEN), "
            "or configure Application Default Credentials."
        ) from exc


def get_drive_client():
    creds = get_google_credentials()
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def create_folder(name: str, parent_folder_id: Optional[str] = None) -> dict:
    drive = get_drive_client()
    body = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
    if parent_folder_id:
        body["parents"] = [parent_folder_id]
    try:
        file = (
            drive.files()
            .create(
                body=body,
                fields="id,webViewLink,webContentLink",
                supportsAllDrives=True,
            )
            .execute()
        )
    except HttpError as exc:
        raise RuntimeError(f"Failed to create folder in Drive: {exc}") from exc
    file_id = file.get("id")
    if not file_id:
        raise RuntimeError("Failed to create folder in Drive: missing file id")
    return {
        "id": file_id,
        "webViewLink": file.get("webViewLink"),
        "webContentLink": file.get("webContentLink"),
    }


def upload_text_file(
    *, name: str, content: str, parent_folder_id: Optional[str] = None
) -> dict:
    drive = get_drive_client()
    media = MediaInMemoryUpload(content.encode("utf-8"), mimetype="text/plain")
    body = {"name": name}
    if parent_folder_id:
        body["parents"] = [parent_folder_id]

    try:
        file = (
            drive.files()
            .create(
                body=body,
                media_body=media,
                fields="id,webViewLink,webContentLink",
                supportsAllDrives=True,
            )
            .execute()
        )
    except HttpError as exc:
        raise RuntimeError(f"Failed to upload file to Drive: {exc}") from exc

    file_id = file.get("id")
    if not file_id:
        raise RuntimeError("Failed to upload file to Drive: missing file id")

    return {
        "id": file_id,
        "webViewLink": file.get("webViewLink"),
        "webContentLink": file.get("webContentLink"),
    }


def download_drive_text_file(*, file_id: str, encoding: str = "utf-8") -> str:
    """
    Download a Drive file as text.

    Notes:
    - For regular files, Drive "media" download is used.
    - For Google-native files (Docs, Sheets, etc.), Drive export is used.
    """
    drive = get_drive_client()
    try:
        meta = (
            drive.files()
            .get(fileId=file_id, fields="mimeType", supportsAllDrives=True)
            .execute()
        )
        mime_type = meta.get("mimeType") if isinstance(meta, dict) else None

        if isinstance(mime_type, str) and mime_type.startswith("application/vnd.google-apps."):
            data = drive.files().export_media(fileId=file_id, mimeType="text/plain").execute()
        else:
            data = drive.files().get_media(fileId=file_id, supportsAllDrives=True).execute()
    except HttpError as exc:
        raise RuntimeError(f"Failed to download file from Drive (file_id={file_id}): {exc}") from exc

    if not isinstance(data, (bytes, bytearray)):
        raise RuntimeError("Drive download did not return bytes.")

    try:
        return bytes(data).decode(encoding)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Failed to decode Drive file content as {encoding}: {exc}") from exc
