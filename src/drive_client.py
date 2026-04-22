"""
Google Drive client.
Uploads .docx files to a configured folder and returns a shareable link.

Requires the same service account credentials as sheets_client.py.
The service account must have Editor access to the target Drive folder.
"""

import io
import logging
import os

from .config import (
    DRIVE_FOLDER_ID,
    GOOGLE_SERVICE_ACCOUNT_FILE,
    GOOGLE_SERVICE_ACCOUNT_JSON,
)

logger = logging.getLogger(__name__)


def _get_drive_service():
    import json as _json
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build

    scopes = ["https://www.googleapis.com/auth/drive"]

    if GOOGLE_SERVICE_ACCOUNT_JSON:
        info = _json.loads(GOOGLE_SERVICE_ACCOUNT_JSON)
        creds = Credentials.from_service_account_info(info, scopes=scopes)
    elif GOOGLE_SERVICE_ACCOUNT_FILE and os.path.exists(GOOGLE_SERVICE_ACCOUNT_FILE):
        creds = Credentials.from_service_account_file(GOOGLE_SERVICE_ACCOUNT_FILE, scopes=scopes)
    else:
        raise EnvironmentError(
            "Google service account not configured. "
            "Set GOOGLE_SERVICE_ACCOUNT_FILE or GOOGLE_SERVICE_ACCOUNT_JSON in .env"
        )

    return build("drive", "v3", credentials=creds, cache_discovery=False)


def upload_docx(file_path: str, filename: str) -> str:
    """
    Upload a .docx file to Google Drive.
    Returns the shareable web-view URL (anyone with link can view).
    """
    from googleapiclient.http import MediaFileUpload

    service = _get_drive_service()

    file_metadata = {"name": filename, "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
    if DRIVE_FOLDER_ID:
        file_metadata["parents"] = [DRIVE_FOLDER_ID]

    media = MediaFileUpload(
        file_path,
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        resumable=False,
    )

    uploaded = service.files().create(
        body=file_metadata,
        media_body=media,
        fields="id, webViewLink",
    ).execute()

    file_id = uploaded["id"]
    url = _make_public_and_get_url(service, file_id, uploaded)
    logger.info("Uploaded '%s' to Drive → %s", filename, url)
    return url


def upload_docx_bytes(content: bytes, filename: str) -> str:
    """
    Upload a .docx from an in-memory bytes object.
    Returns the shareable web-view URL.
    """
    from googleapiclient.http import MediaIoBaseUpload

    service = _get_drive_service()

    file_metadata = {"name": filename, "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
    if DRIVE_FOLDER_ID:
        file_metadata["parents"] = [DRIVE_FOLDER_ID]

    fh = io.BytesIO(content)
    media = MediaIoBaseUpload(
        fh,
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        resumable=False,
    )

    uploaded = service.files().create(
        body=file_metadata,
        media_body=media,
        fields="id, webViewLink",
    ).execute()

    file_id = uploaded["id"]
    url = _make_public_and_get_url(service, file_id, uploaded)
    logger.info("Uploaded '%s' to Drive → %s", filename, url)
    return url


def _make_public_and_get_url(service, file_id: str, uploaded: dict) -> str:
    """
    Set 'anyone with link can view' permission and return the shareable URL.
    Retries permission creation once on failure.
    Always returns a valid URL even if the API response is missing webViewLink.
    """
    for attempt in range(2):
        try:
            service.permissions().create(
                fileId=file_id,
                body={"type": "anyone", "role": "reader"},
            ).execute()
            break
        except Exception as e:
            if attempt == 0:
                logger.warning("Permission creation attempt 1 failed, retrying: %s", e)
            else:
                logger.error("Permission creation failed for file %s: %s — link may require Google login", file_id, e)

    # Use webViewLink from API response; fall back to canonical URL if empty/missing
    url = uploaded.get("webViewLink") or f"https://drive.google.com/file/d/{file_id}/view?usp=sharing"
    return url
