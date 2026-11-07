"""Google Drive storage for the section resources.

Resources are read by every student, so each uploaded file is put in the
MNHSREVIEWCENTER folder and then shared so that anyone with the link can view
it. The token is the google_credentials.json JSON file produced by
gdrive_authorize.py in this folder, unless MNHS_DRIVE_CREDENTIALS names
another one.
"""
import io
import os
import threading

FOLDER_NAME = "MNHSREVIEWCENTER"
SCOPES = ["https://www.googleapis.com/auth/drive.file"]

_local = threading.local()
_last_error = ""


HERE = os.path.dirname(os.path.abspath(__file__))
TOKEN_NAME = "google_credentials.json"


def credentials_path():
    """The token JSON written by gdrive_authorize.py.

    Looked for in the folder this file sits in first, then the gdrive/ folder
    and the mnhs folders in the user profile, so a token produced by either
    copy of the script is found.
    """
    for path in (os.environ.get("MNHS_DRIVE_CREDENTIALS"),
                 os.environ.get("WHOSWHO_DRIVE_CREDENTIALS"),
                 os.path.join(HERE, TOKEN_NAME),
                 os.path.join(HERE, "gdrive", TOKEN_NAME),
                 os.path.expanduser(os.path.join("~", ".mnhs", TOKEN_NAME)),
                 os.path.expanduser(os.path.join("~", "mnhs", TOKEN_NAME))):
        if path and os.path.exists(path):
            return os.path.expanduser(path)
    return os.path.join(HERE, TOKEN_NAME)


def configured():
    """True when the Drive libraries are installed and the key file is present."""
    try:
        import googleapiclient.discovery  # noqa: F401
    except Exception:
        return False
    return os.path.exists(credentials_path())


def error():
    return _last_error


def _note(exc):
    """Google's terse token errors turned into the one thing to do about them.

    An expired refresh token is the failure the school actually hits: Google
    kills one after a week while the consent screen is still in "testing", and
    the app cannot fix that by itself.
    """
    text = str(exc)
    if "invalid_grant" in text or "Token has been expired" in text:
        return text + " -- the saved Google sign-in has expired. Run " \
                       "'python gdrive_authorize.py' once in this folder to get a fresh one."
    return text


def _credentials():
    import json
    from google.oauth2.credentials import Credentials

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
        _last_error = ("Google Drive is not set up on this computer. Put the OAuth "
                       "JSON at %s or set MNHS_DRIVE_CREDENTIALS." % credentials_path())
        return None
    try:
        from googleapiclient.discovery import build

        svc = build("drive", "v3", credentials=_credentials(), cache_discovery=False)
        _local.svc = svc
        _last_error = ""
        return svc
    except Exception as exc:
        _last_error = "Drive sign-in failed: %s" % _note(exc)
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
        _last_error = "Could not open the %s folder: %s" % (FOLDER_NAME, _note(exc))
        return None


def open_to_viewers(svc, file_id):
    """Let any student open the file, even one with no Google account."""
    global _last_error
    try:
        svc.permissions().create(
            fileId=file_id, body={"type": "anyone", "role": "reader"},
            fields="id").execute()
        _last_error = ""
        return True
    except Exception as exc:
        _last_error = "Uploaded but could not be shared: %s" % _note(exc)
        return False


def upload(data, filename, mime):
    """Store one resource and return (file id, share link, message).

    An empty id means Drive could not take it, and the admin is told why
    instead of watching a silent failure.
    """
    global _last_error
    svc = service()
    if not svc:
        return "", "", _last_error
    try:
        from googleapiclient.http import MediaIoBaseUpload

        parent = folder_id(svc)
        body = {"name": filename,
                "parents": [parent] if parent else [],
                "description": "Section resource - MNHS Review Center"}
        media = MediaIoBaseUpload(io.BytesIO(data), mimetype=mime or "application/octet-stream",
                                  resumable=len(data) > 5_000_000)
        done = svc.files().create(body=body, media_body=media, fields="id").execute()
        file_id = done.get("id", "")
        if file_id:
            open_to_viewers(svc, file_id)
        _last_error = ""
        return file_id, share_link(file_id), _last_error
    except Exception as exc:
        _last_error = "Drive upload failed for %s: %s" % (filename, _note(exc))
        return "", "", _last_error


def delete(file_id):
    svc = service()
    if not svc or not file_id:
        return False
    try:
        svc.files().delete(fileId=file_id).execute()
        return True
    except Exception as exc:
        _last_error = "Drive delete failed for %s: %s" % (file_id, _note(exc))
        return False


def share_link(file_id):
    if not file_id:
        return ""
    return "https://drive.google.com/file/d/%s/view?usp=sharing" % file_id
