"""Run ONCE in this folder to connect the app to your Google Drive.

1. Download the OAuth client (type "Desktop app") from Google Cloud -> APIs &
   Services -> Credentials and save it as client_secret.json in this folder
   (the old ~/.mnhs/client_secret.json still works).
2. python gdrive_authorize.py  -> a browser opens; sign in with the Google
   account that owns the Drive.
3. The token is written as JSON to google_credentials.json in this same folder,
   the one file both the section materials and the Who's Who pictures read.

Never commit or share this folder with the token in it: it holds a refresh
token that opens the whole MNHSREVIEWCENTER folder.

Google expires a refresh token after 7 days while the OAuth consent screen is
still in "testing", which is why Drive starts failing a week after it works.
Publish the consent screen (or add the admin as a test user again) and re-run
this script; the app cannot refresh a token Google has already killed.
"""
import os

from google_auth_oauthlib.flow import InstalledAppFlow

HERE = os.path.dirname(os.path.abspath(__file__))
TOKEN = os.path.join(HERE, "google_credentials.json")
SCOPES = ["https://www.googleapis.com/auth/drive.file"]

candidates = [os.path.join(HERE, "client_secret.json"),
              os.path.expanduser(os.path.join("~", ".mnhs", "client_secret.json")),
              os.path.expanduser(os.path.join("~", "mnhs", "client_secret.json"))]
SECRETS = next((p for p in candidates if os.path.exists(p)), candidates[0])

if not os.path.exists(SECRETS):
    raise SystemExit(
        "Put the OAuth client secret at %s first." % SECRETS)

flow = InstalledAppFlow.from_client_secrets_file(SECRETS, SCOPES)
creds = flow.run_local_server(port=0)

with open(TOKEN, "w", encoding="utf-8") as f:
    f.write(creds.to_json())
try:
    os.chmod(TOKEN, 0o600)
except OSError:
    pass

print("Saved %s - the app reads Drive with this one file." % TOKEN)
