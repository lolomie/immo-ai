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

    # Make the file viewable by anyone with the link
    service.permissions().create(
        fileId=file_id,
        body={"type": "anyone", "role": "reader"},
    ).execute()

    url = uploaded.get("webViewLink", f"https://drive.google.com/file/d/{file_id}/view")
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
    service.permissions().create(
        fileId=file_id,
        body={"type": "anyone", "role": "reader"},
    ).execute()

    url = uploaded.get("webViewLink", f"https://drive.google.com/file/d/{file_id}/view")
    logger.info("Uploaded '%s' to Drive → %s", filename, url)
    return url
