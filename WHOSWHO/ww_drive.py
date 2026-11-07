"""Google Drive storage for the Who's Who pictures.

Drive is the copy of record: every photo the admin uploads is put into a folder
named MNHSREVIEWCENTER, created on the first upload. The app also keeps a local
copy, so a classroom that loses the internet still sees the picture, and a
picture that is only on Drive is pulled back on demand.

The credentials are never stored in this project. They are read from the file
named by the WHOSWHO_DRIVE_CREDENTIALS environment variable, which on this
computer is C:\\Users\\ADMIN\\.mnhs\\google_credentials.json - a folder that is
not uploaded with the app.
"""
import io
import os
import threading

FOLDER_NAME = "MNHSREVIEWCENTER"
SCOPES = ["https://www.googleapis.com/auth/drive.file"]

_local = threading.local()
_last_error = ""


def credentials_path():
    return os.path.expanduser(
        os.environ.get("WHOSWHO_DRIVE_CREDENTIALS")
        or os.path.join(os.path.expanduser("~"), ".mnhs", "google_credentials.json"))


def configured():
    """True when the Drive libraries are installed and the key file is present."""
    try:
        import googleapiclient.discovery  # noqa: F401
    except Exception:
        return False
    return os.path.exists(credentials_path())


def error():
    return _last_error


def _credentials():
    from google.oauth2.credentials import Credentials
    import json

    with open(credentials_path(), encoding="utf-8") as f:
        raw = json.load(f)
    return Credentials(
        token=raw.get("token"),
        refresh_token=raw.get("refresh_token"),
        token_uri=raw.get("token_uri") or "https://oauth2.googleapis.com/token",
        client_id=raw.get("client_id"),
        client_secret=raw.get("client_secret"),
        scopes=raw.get("scopes") or SCOPES)


def service():
    """One Drive client per thread; the token refreshes itself."""
    global _last_error
    svc = getattr(_local, "svc", None)
    if svc:
        return svc
    if not configured():
        _last_error = ("Google Drive is not set up on this computer. "
                       "Put the OAuth JSON at %s or set WHOSWHO_DRIVE_CREDENTIALS."
                       % credentials_path())
        return None
    try:
        from googleapiclient.discovery import build

        svc = build("drive", "v3", credentials=_credentials(), cache_discovery=False)
        _local.svc = svc
        _last_error = ""
        return svc
    except Exception as exc:
        _last_error = "Drive sign-in failed: %s" % exc
        return None


def folder_id(svc):
    """The MNHSREVIEWCENTER folder, made on first use."""
    global _last_error
    try:
        found = svc.files().list(
            q="mimeType='application/vnd.google-apps.folder' and name='%s' "
              "and trashed=false" % FOLDER_NAME,
            fields="files(id,name)", pageSize=1).execute()
        rows = found.get("files") or []
        if rows:
            return rows[0]["id"]
        meta = {"name": FOLDER_NAME, "mimeType": "application/vnd.google-apps.folder"}
        made = svc.files().create(body=meta, fields="id").execute()
        return made["id"]
    except Exception as exc:
        _last_error = "Could not open the %s folder: %s" % (FOLDER_NAME, exc)
        return None


def upload(data, filename, mime):
    """Put one picture in Drive and return its file id ('' when it fails)."""
    global _last_error
    svc = service()
    if not svc:
        return ""
    try:
        from googleapiclient.http import MediaIoBaseUpload

        parent = folder_id(svc)
        body = {"name": filename,
                "parents": [parent] if parent else [],
                "description": "Who's Who picture - MNHS Review Center"}
        media = MediaIoBaseUpload(io.BytesIO(data), mimetype=mime or "image/jpeg",
                                  resumable=len(data) > 5_000_000)
        done = svc.files().create(body=body, media_body=media, fields="id").execute()
        _last_error = ""
        return done.get("id", "")
    except Exception as exc:
        _last_error = "Drive upload failed for %s: %s" % (filename, exc)
        return ""


def download(file_id):
    """Bytes of a Drive picture, or None. Used when the local copy is missing."""
    svc = service()
    if not svc or not file_id:
        return None
    try:
        return svc.files().get_media(fileId=file_id).download()
    except Exception as exc:
        _last_error = "Drive download failed for %s: %s" % (file_id, exc)
        return None


def share_link(file_id):
    if not file_id:
        return ""
    return "https://drive.google.com/file/d/%s/view" % file_id
