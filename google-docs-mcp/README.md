# Google Docs MCP Server

MCP server som integrerar Claude Code med Google Docs API.
Möjliggör skapande, läsning, redigering och sökning av Google Docs-dokument.

## Verktyg

| Verktyg | Beskrivning |
|---------|-------------|
| `create_document` | Skapa nytt dokument med titel och innehåll |
| `read_document` | Läs dokumentinnehåll som klartext |
| `edit_document` | Ersätt eller lägg till innehåll i ett dokument |
| `list_documents` | Lista/sök dokument i Drive |

## Förutsättningar

### 1. Google Cloud Console

1. Gå till [Google Cloud Console](https://console.cloud.google.com/)
2. Skapa ett nytt projekt (eller välj befintligt)
3. Aktivera **Google Docs API**
4. Aktivera **Google Drive API**
5. Gå till *APIs & Services → Credentials*
6. Klicka *Create Credentials → OAuth client ID*
7. Välj **Desktop Application** som applikationstyp
8. Ladda ner JSON-filen

### 2. Placera credentials

```
credentials/client_secret.json   ← ladda ner från Google Cloud Console
credentials/token.json           ← skapas automatiskt vid första inloggning
```

> **OBS:** Lägg aldrig till `credentials/client_secret.json` eller
> `credentials/token.json` i git. De är redan exkluderade via `.gitignore`.

## Installation

```bash
cd C:/Users/josef/mcp-servers/google-docs-mcp
uv sync
```

## Köra servern manuellt (för test)

```bash
uv run google-docs-mcp
```

Servern startar och väntar på stdio-kommandon.
Vid första körning öppnas en browser för OAuth2-inloggning.

## MCP-konfiguration

### Claude Code (`.mcp.json`)

```json
"google-docs": {
  "command": "uv",
  "args": ["--directory", "C:/Users/josef/mcp-servers/google-docs-mcp", "run", "google-docs-mcp"],
  "type": "stdio"
}
```

### Claude Desktop (`claude_desktop_config.json`)

```json
"google-docs": {
  "command": "uv",
  "args": ["--directory", "C:/Users/josef/mcp-servers/google-docs-mcp", "run", "google-docs-mcp"]
}
```

## Autentisering

- **Flöde:** OAuth2 InstalledAppFlow (browser-baserat, engångsinloggning)
- **Scopes:**
  - `https://www.googleapis.com/auth/documents` — läsa + skriva docs
  - `https://www.googleapis.com/auth/drive` — lista + söka i Drive
- **Token:** sparas i `credentials/token.json`, auto-refresh vid utgång

## Exempel

```
Skapa ett Google Docs-dokument med titeln "Mötesprotokoll 2026-03-01"
och texten "Deltagare: Josef, Anna\n\nÄrenden:\n1. Budget"
```

```
Läs dokumentet med ID 1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms
```

```
Lista mina senaste Google Docs-dokument
```

```
Sök bland mina Google Docs efter "totalförsvar"
```

## Beroenden

- `google-api-python-client>=2.100.0`
- `google-auth-oauthlib>=1.0.0`
- `google-auth-httplib2>=0.2.0`
- `mcp>=1.0.0`
- `fastmcp>=0.1.0`
- `pydantic>=2.0.0`

## Kontakt

Länsstyrelsen Västra Götaland — Josef

## Felsökning: OAuth-token

Servern startar **aldrig** ett browserflöde själv. Om token är död returnerar varje
verktygsanrop i stället ett fel inom en sekund, med instruktionen nedan.

Bakgrund (2026-08-10): tidigare föll `get_credentials()` tillbaka på
`InstalledAppFlow.run_local_server()` när refresh misslyckades. Den funktionen blockerar
tills någon öppnar callback-URL:en — vilket aldrig sker i en MCP-server utan terminal.
Resultatet blev en hängning på 2 021 sekunder utan felmeddelande i stället för ett fel.
En hängning är strikt sämre än ett fel.

### Ominloggning

Kräver browser och stdin och måste därför köras i ett **eget terminalfönster**, aldrig via
Claude Code:

```powershell
cd C:\Users\josef\mcp-servers\google-docs-mcp
uv run python reauth.py
```

Starta om Claude Code efteråt så att servern läser den nya tokenen.

### Om felet återkommer inom några dygn

Kontrollera att OAuth-samtyckesskärmen är **publicerad**: Google Auth Platform → Audience →
*Publish app* (`console.cloud.google.com/auth/audience`). I Publishing status `Testing`
gallrar Google refresh-tokens efter 7 dygn, även för en app med en enda användare. Ingen
Google-verifiering krävs för en intern app.

Andra orsaker till `invalid_grant`: lösenordsbyte eller annan säkerhetshändelse på kontot,
återkallad åtkomst på `myaccount.google.com/permissions`, eller att fler än 50 refresh-tokens
utfärdats för samma klient (äldst gallras först — kör inte `reauth.py` i onödan).

### Kontrollera tokenstatus utan nätverk

```python
from google_docs_mcp.auth import token_status
print(token_status())   # finns / giltig / utgangen / har_refresh_token / expiry
```
