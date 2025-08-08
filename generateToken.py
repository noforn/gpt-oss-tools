from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
import json

SCOPES = ["https://www.googleapis.com/auth/calendar"]

# download credentials.json from google cloud console: https://console.cloud.google.com/auth/clients

CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE = "token.json"

def main():
    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
    creds = flow.run_local_server(port=0) 
    with open(TOKEN_FILE, "w") as f:
        f.write(creds.to_json())
    print(f"Saved token to {TOKEN_FILE}")

if __name__ == "__main__":
    main()
