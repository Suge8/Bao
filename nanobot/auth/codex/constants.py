"""Codex OAuth constants."""

CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
AUTHORIZE_URL = "https://auth.openai.com/oauth/authorize"
TOKEN_URL = "https://auth.openai.com/oauth/token"
REDIRECT_URI = "http://localhost:1455/auth/callback"
SCOPE = "openid profile email offline_access"
JWT_CLAIM_PATH = "https://api.openai.com/auth"

DEFAULT_ORIGINATOR = "nanobot"
TOKEN_FILENAME = "codex.json"
MANUAL_PROMPT_DELAY_SEC = 3
SUCCESS_HTML = (
    "<!doctype html>"
    "<html lang=\"en\">"
    "<head>"
    "<meta charset=\"utf-8\" />"
    "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />"
    "<title>Authentication successful</title>"
    "</head>"
    "<body>"
    "<p>Authentication successful. Return to your terminal to continue.</p>"
    "</body>"
    "</html>"
)
