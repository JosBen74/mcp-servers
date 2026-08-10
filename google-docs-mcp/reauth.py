"""Tvinga ny OAuth2-inloggning for google-docs-mcp.

Kor detta nar MCP-verktygen svarar 'invalid_grant: Bad Request', dvs nar
Google har ogiltigforklarat refresh-token. Skriptet tar bort den gamla
token.json, oppnar en browser for inloggning och sparar en ny token.

Anvandning (i ett eget PowerShell-fonster, INTE via Claude Code):

    cd C:\\Users\\josef\\mcp-servers\\google-docs-mcp
    uv run python reauth.py

Efter lyckad inloggning: starta om Claude Code sa att MCP-servern
laser den nya tokenen.
"""

import os
import sys
from datetime import datetime, timezone

from google_auth_oauthlib.flow import InstalledAppFlow

from google_docs_mcp.auth import (
    CLIENT_SECRET_PATH,
    INTERACTIVE_ENV_VAR,
    INTERACTIVE_TIMEOUT_SECONDS,
    SCOPES,
    TOKEN_PATH,
)

sys.stdout.reconfigure(encoding="utf-8")

# Det har skriptet ar den ENDA sanktionerade vagen till ett browserflode.
# Servern sjalv vagrar starta ett — se auth.py.
os.environ[INTERACTIVE_ENV_VAR] = "1"


def main() -> int:
    """Kor om OAuth2-flodet och spara ny token.

    Returns:
        0 vid lyckad inloggning, 1 vid fel.
    """
    if not CLIENT_SECRET_PATH.exists():
        print(f"FEL: client_secret.json saknas: {CLIENT_SECRET_PATH}")
        return 1

    if TOKEN_PATH.exists():
        backup = TOKEN_PATH.with_suffix(".json.gammal")
        TOKEN_PATH.replace(backup)
        print(f"Gammal token flyttad till: {backup}")

    print("Scopes som begars:")
    for scope in SCOPES:
        print(f"  - {scope}")
    print("\nOppnar browser for inloggning...")
    print("Logga in med det Google-konto som ager kalkylbladen.\n")

    try:
        flow = InstalledAppFlow.from_client_secrets_file(
            str(CLIENT_SECRET_PATH), SCOPES
        )
        # Tak aven har: utan timeout star skriptet och vantar for evigt om
        # browserfliken stangs innan inloggningen slutforts.
        creds = flow.run_local_server(
            port=0, timeout_seconds=INTERACTIVE_TIMEOUT_SECONDS
        )
    except Exception as exc:  # noqa: BLE001
        print(f"FEL vid inloggning: {exc}")
        print("Gamla token ligger kvar som token.json.gammal om du vill aterstalla.")
        return 1
    if creds is None:
        print(f"FEL: inloggningen slutfordes inte inom {INTERACTIVE_TIMEOUT_SECONDS} s.")
        print("Gamla token ligger kvar som token.json.gammal om du vill aterstalla.")
        return 1

    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")

    print(f"\nKLART. Ny token sparad: {TOKEN_PATH}")
    if creds.expiry:
        exp = creds.expiry
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        minutes = (exp - datetime.now(timezone.utc)).total_seconds() / 60
        print(f"Access-token giltig till: {exp.isoformat()} (~{minutes:.0f} min)")
    print(f"Refresh-token: {'finns' if creds.refresh_token else 'SAKNAS — se nedan'}")
    if not creds.refresh_token:
        print(
            "\nVARNING: ingen refresh-token utfardad. Aterkalla appens atkomst pa\n"
            "https://myaccount.google.com/permissions och kor skriptet igen."
        )
    print("\nStarta om Claude Code sa att MCP-servern laser den nya tokenen.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
