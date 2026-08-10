"""
Google OAuth2 authentication helper for Google Docs MCP server.

Handles token loading, refreshing, and — only when explicitly permitted — the
browser-based authorization flow (InstalledAppFlow). Token is persisted to disk
so the user only needs to authenticate once.

VIKTIGT OM INLOGGNINGSFLODET (2026-08-10)
-----------------------------------------
En MCP-server kor utan terminal och utan nagon som kan slutfora en
browserinloggning. Tidigare foll get_credentials() tillbaka pa
InstalledAppFlow.run_local_server() nar refresh misslyckades. Den funktionen
BLOCKERAR tills nagon oppnar callback-URL:en — vilket aldrig sker i det laget.
Foljden blev att verktygsanropet hangde i stallet for att felа: 2026-08-10
hangde get_sheet_info i 2 021 sekunder innan klienten gav upp, utan ett enda
felmeddelande om vad som var trasigt.

En hangning ar strikt samre an ett fel. Darfor kors inloggningsflodet numera
BARA nar GOOGLE_DOCS_MCP_ALLOW_INTERACTIVE=1 ar satt, vilket reauth.py gor.
I alla andra lagen kastas ett tydligt fel som talar om exakt vad som ska koras.
"""

import logging
import os
from pathlib import Path
from typing import Optional

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

logger = logging.getLogger(__name__)

# OAuth2 scopes required by this server
SCOPES = [
    "https://www.googleapis.com/auth/documents",    # Read + write Docs
    "https://www.googleapis.com/auth/spreadsheets", # Read + write Sheets
    "https://www.googleapis.com/auth/drive",        # List + search Drive
]

# Paths relative to this file's parent package directory
_PACKAGE_DIR = Path(__file__).parent.parent.parent  # repo root
CREDENTIALS_DIR = _PACKAGE_DIR / "credentials"
CLIENT_SECRET_PATH = CREDENTIALS_DIR / "client_secret.json"
TOKEN_PATH = CREDENTIALS_DIR / "token.json"

# Satts av reauth.py. Utan den startar servern aldrig ett browserflode.
INTERACTIVE_ENV_VAR = "GOOGLE_DOCS_MCP_ALLOW_INTERACTIVE"

# Sekunder att vanta pa att inloggningen slutfors innan vi ger upp. Aven det
# uttryckligen interaktiva flodet ska ha ett tak — annars star reauth.py och
# hanger om anvandaren stanger browserfliken.
INTERACTIVE_TIMEOUT_SECONDS = 300

_REAUTH_INSTRUKTION = (
    "Kor ominloggning i ETT EGET terminalfonster (inte via Claude Code, som saknar "
    "stdin och browser):\n"
    "    cd C:\\Users\\josef\\mcp-servers\\google-docs-mcp\n"
    "    uv run python reauth.py\n"
    "Starta darefter om Claude Code sa att servern laser den nya tokenen.\n"
    "Aterkommer felet inom nagra dygn: kontrollera att OAuth-samtyckesskarmen ar "
    "PUBLICERAD (Google Auth Platform -> Audience -> Publish app). I Publishing "
    "status 'Testing' gallrar Google refresh-tokens efter 7 dygn."
)


def interactive_allowed() -> bool:
    """True om browserinloggning uttryckligen tillatits av anroparen."""
    return os.environ.get(INTERACTIVE_ENV_VAR, "") == "1"


def token_status() -> dict:
    """Beskriv tokenens tillstand utan att refresha, logga in eller skriva nagot.

    Returns:
        Dict med nycklarna finns, giltig, utgangen, har_refresh_token, expiry.
    """
    if not TOKEN_PATH.exists():
        return {"finns": False, "giltig": False, "utgangen": None,
                "har_refresh_token": False, "expiry": None}
    creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    return {
        "finns": True,
        "giltig": bool(creds.valid),
        "utgangen": bool(creds.expired),
        "har_refresh_token": bool(creds.refresh_token),
        "expiry": creds.expiry.isoformat() if creds.expiry else None,
    }


def get_credentials() -> Credentials:
    """Returnera giltiga OAuth2-credentials; refresha vid behov.

    Browserinloggning sker BARA om GOOGLE_DOCS_MCP_ALLOW_INTERACTIVE=1. I annat
    fall kastas RuntimeError med instruktion — en MCP-server ska aldrig hanga pa
    ett inloggningsflode som ingen kan slutfora.

    Returns:
        Giltiga Google OAuth2 Credentials.

    Raises:
        FileNotFoundError: Om client_secret.json saknas.
        RuntimeError: Om inloggning kravs men inte ar tillaten, eller om
            inloggningsflodet misslyckas.
    """
    if not CLIENT_SECRET_PATH.exists():
        raise FileNotFoundError(
            f"client_secret.json saknas: {CLIENT_SECRET_PATH}\n"
            "1. Ga till Google Cloud Console\n"
            "2. Aktivera Google Docs API och Google Drive API\n"
            "3. Skapa OAuth2-credentials (Desktop Application)\n"
            f"4. Ladda ner och spara som: {CLIENT_SECRET_PATH}"
        )

    creds: Optional[Credentials] = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
        logger.debug("Laddade befintliga credentials fran %s", TOKEN_PATH)

    if creds and creds.valid:
        return creds

    refresh_fel: Optional[str] = None
    if creds and creds.expired and creds.refresh_token:
        logger.info("Refreshar OAuth2-token...")
        try:
            creds.refresh(Request())
            CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)
            TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
            logger.info("Token refreshad och sparad till %s", TOKEN_PATH)
            return creds
        except RefreshError as exc:
            refresh_fel = str(exc)
            # Warning, inte debug: en tyst fallback doljer att tokenen ar dod.
            logger.warning("Refresh misslyckades: %s", exc)

    if not interactive_allowed():
        orsak = (
            f"OAuth-token kunde inte fornyas ({refresh_fel})."
            if refresh_fel
            else "Ingen giltig OAuth-token finns."
        )
        if refresh_fel and "invalid_grant" in refresh_fel:
            orsak += (
                " invalid_grant betyder att Google har aterkallat refresh-token —"
                " den lakar inte av sig sjalv och maste ersattas med en ny inloggning."
            )
        raise RuntimeError(
            f"{orsak}\n\n{_REAUTH_INSTRUKTION}\n\n"
            "(Servern startar avsiktligt INTE ett browserflode har. Det skulle blockera"
            " verktygsanropet tills klienten ger upp, i stallet for att visa det har"
            " felet.)"
        )

    logger.info("Startar OAuth2-inloggningsflode i browser (uttryckligen tillatet)...")
    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET_PATH), SCOPES)
    try:
        creds = flow.run_local_server(port=0, timeout_seconds=INTERACTIVE_TIMEOUT_SECONDS)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            f"Inloggningsflodet misslyckades eller tog for lang tid: {exc}\n\n"
            f"{_REAUTH_INSTRUKTION}"
        ) from exc
    if creds is None:
        raise RuntimeError(
            f"Inloggningen slutfordes inte inom {INTERACTIVE_TIMEOUT_SECONDS} s.\n\n"
            f"{_REAUTH_INSTRUKTION}"
        )

    CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
    logger.info("Token sparad till %s", TOKEN_PATH)
    return creds
