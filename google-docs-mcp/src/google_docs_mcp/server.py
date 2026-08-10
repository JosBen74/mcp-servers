#!/usr/bin/env python3
"""
Google Docs & Sheets MCP Server

MCP server for creating, reading, editing and listing Google Docs documents
and reading/appending Google Sheets, via the Google Docs/Sheets/Drive APIs.

Authentication: OAuth2 (InstalledAppFlow) — requires client_secret.json
placed in credentials/ directory. Token is cached to credentials/token.json.

Tools (Docs):
    create_document  — Create a new Google Doc with title and content
    read_document    — Read document content as plain text
    edit_document    — Replace or append content in a document
    list_documents   — List/search Google Docs in Drive

Tools (Sheets):
    get_sheet_info    — Get spreadsheet metadata (sheets, row/column counts)
    read_sheet        — Read data from a sheet as a formatted table
    append_sheet_row  — Append a single row to the end of a sheet
    list_sheets       — List/search Google Sheets in Drive

Version: 1.2.0
"""

import logging
from typing import Optional

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from mcp.server.fastmcp import FastMCP

from .auth import get_credentials

# Initialize MCP server
mcp = FastMCP("google_docs_mcp")

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Base URLs for Google links
DOCS_BASE_URL = "https://docs.google.com/document/d"
SHEETS_BASE_URL = "https://docs.google.com/spreadsheets/d"


def _get_docs_service():
    """Bygg och returnera autentiserad Google Docs API-klient."""
    creds = get_credentials()
    return build("docs", "v1", credentials=creds)


def _get_drive_service():
    """Bygg och returnera autentiserad Google Drive API-klient."""
    creds = get_credentials()
    return build("drive", "v3", credentials=creds)


def _get_sheets_service():
    """Bygg och returnera autentiserad Google Sheets API-klient."""
    creds = get_credentials()
    return build("sheets", "v4", credentials=creds)


def _extract_text(document: dict) -> str:
    """Extrahera ren text ur ett Google Docs API-dokument-objekt.

    Itererar body.content och samlar textRun.content-strängar.
    Strukturelement utan textRun (t.ex. tabeller) hoppas over.

    Args:
        document: Dokument-dict från Google Docs API.

    Returns:
        Dokumentets textinnehall som en sträng.
    """
    text_parts: list[str] = []
    content = document.get("body", {}).get("content", [])

    for element in content:
        paragraph = element.get("paragraph")
        if not paragraph:
            continue
        for para_element in paragraph.get("elements", []):
            text_run = para_element.get("textRun")
            if text_run:
                text_parts.append(text_run.get("content", ""))

    return "".join(text_parts)


def _get_end_index(document: dict) -> int:
    """Returnera sista teckenindex i dokumentet (for insertText-positionering).

    Google Docs API kräver att insertText sker minst ett steg före sista index
    (som reserveras for \n). Vi returnerar body.content[-1].endIndex - 1.

    Args:
        document: Dokument-dict från Google Docs API.

    Returns:
        Sista skrivbara index.
    """
    content = document.get("body", {}).get("content", [])
    if not content:
        return 1
    last_element = content[-1]
    end_index = last_element.get("endIndex", 2)
    # Subtract 1 to stay within writable range (last char is always \n)
    return max(1, end_index - 1)


# ============================================================================
# MCP TOOLS
# ============================================================================

@mcp.tool()
def create_document(title: str, content: str) -> str:
    """Skapa ett nytt Google Docs-dokument med titel och textinnehall.

    Args:
        title: Dokumentets titel.
        content: Textinnehall att infoga i dokumentet.

    Returns:
        Sträng med dokument-ID och URL till det skapade dokumentet.
    """
    try:
        docs_service = _get_docs_service()

        # Step 1: Create empty document with title
        doc = docs_service.documents().create(body={"title": title}).execute()
        document_id: str = doc["documentId"]
        logger.info("Skapade dokument: %s", document_id)

        # Step 2: Insert content at index 1 (beginning of body)
        if content:
            requests = [
                {
                    "insertText": {
                        "location": {"index": 1},
                        "text": content,
                    }
                }
            ]
            docs_service.documents().batchUpdate(
                documentId=document_id,
                body={"requests": requests},
            ).execute()

        doc_url = f"{DOCS_BASE_URL}/{document_id}/edit"
        return (
            f"Dokument skapat!\n"
            f"Titel: {title}\n"
            f"ID: {document_id}\n"
            f"URL: {doc_url}"
        )

    except HttpError as e:
        logger.error("Google API-fel vid skapande av dokument: %s", e)
        return f"Fel vid skapande av dokument: {e}"
    except FileNotFoundError as e:
        return f"Autentiseringsfel: {e}"
    except Exception as e:
        logger.error("Oväntat fel: %s", e)
        return f"Oväntat fel: {e}"


@mcp.tool()
def read_document(document_id: str) -> str:
    """Läs och returnera innehallet i ett Google Docs-dokument som klartext.

    Args:
        document_id: Google Docs dokument-ID (finns i URL:en efter /d/).

    Returns:
        Dokumentets titel och textinnehall som klartext.
    """
    try:
        docs_service = _get_docs_service()
        document = docs_service.documents().get(documentId=document_id).execute()

        title = document.get("title", "(ingen titel)")
        text = _extract_text(document)

        if not text.strip():
            return f"Titel: {title}\n\n(Dokumentet är tomt)"

        return f"Titel: {title}\n\n{text}"

    except HttpError as e:
        if e.resp.status == 404:
            return f"Dokumentet hittades inte: {document_id}"
        if e.resp.status == 403:
            return f"Ingen åtkomst till dokumentet: {document_id}"
        logger.error("Google API-fel vid läsning: %s", e)
        return f"Fel vid läsning av dokument: {e}"
    except FileNotFoundError as e:
        return f"Autentiseringsfel: {e}"
    except Exception as e:
        logger.error("Oväntat fel: %s", e)
        return f"Oväntat fel: {e}"


@mcp.tool()
def edit_document(
    document_id: str,
    content: str,
    append: bool = False,
) -> str:
    """Redigera ett Google Docs-dokument genom att ersätta eller lägga till innehall.

    Args:
        document_id: Google Docs dokument-ID.
        content: Nytt textinnehall att skriva.
        append: Om True läggs content till i slutet. Om False ersätts allt befintligt
                innehall (default: False).

    Returns:
        Bekräftelse med antalet tecken som skrevs.
    """
    try:
        docs_service = _get_docs_service()
        document = docs_service.documents().get(documentId=document_id).execute()
        title = document.get("title", document_id)
        requests: list[dict] = []

        if append:
            # Insert at end of document
            end_index = _get_end_index(document)
            requests.append(
                {
                    "insertText": {
                        "location": {"index": end_index},
                        "text": content,
                    }
                }
            )
        else:
            # Replace all content: delete existing, then insert new
            end_index = _get_end_index(document)
            if end_index > 1:
                requests.append(
                    {
                        "deleteContentRange": {
                            "range": {
                                "startIndex": 1,
                                "endIndex": end_index,
                            }
                        }
                    }
                )
            if content:
                requests.append(
                    {
                        "insertText": {
                            "location": {"index": 1},
                            "text": content,
                        }
                    }
                )

        if requests:
            docs_service.documents().batchUpdate(
                documentId=document_id,
                body={"requests": requests},
            ).execute()

        mode = "lagt till i slutet av" if append else "ersatt innehallet i"
        doc_url = f"{DOCS_BASE_URL}/{document_id}/edit"
        return (
            f"Klart! {len(content)} tecken har {mode} '{title}'.\n"
            f"URL: {doc_url}"
        )

    except HttpError as e:
        if e.resp.status == 404:
            return f"Dokumentet hittades inte: {document_id}"
        if e.resp.status == 403:
            return f"Ingen skrivåtkomst till dokumentet: {document_id}"
        logger.error("Google API-fel vid redigering: %s", e)
        return f"Fel vid redigering av dokument: {e}"
    except FileNotFoundError as e:
        return f"Autentiseringsfel: {e}"
    except Exception as e:
        logger.error("Oväntat fel: %s", e)
        return f"Oväntat fel: {e}"


@mcp.tool()
def list_documents(query: str = "", max_results: int = 10) -> str:
    """Lista och sök bland Google Docs-dokument i Drive.

    Args:
        query: Valfri söksträng for fritextsökning i dokumenttitlar/innehall.
               Lämna tomt for att lista de senaste dokumenten.
        max_results: Maximalt antal resultat att returnera (default: 10, max: 100).

    Returns:
        Formaterad lista med dokument-titlar, ID:n och URL:er.
    """
    try:
        drive_service = _get_drive_service()

        # Base filter: only Google Docs
        mime_filter = "mimeType='application/vnd.google-apps.document'"
        if query:
            # fullText search includes title and content
            drive_query = f"{mime_filter} and fullText contains '{query}'"
        else:
            drive_query = mime_filter

        max_results = min(max(1, max_results), 100)

        result = (
            drive_service.files()
            .list(
                q=drive_query,
                pageSize=max_results,
                fields="files(id, name, modifiedTime, webViewLink)",
                orderBy="modifiedTime desc",
            )
            .execute()
        )

        files = result.get("files", [])

        if not files:
            if query:
                return f"Inga dokument hittades for sokningen: '{query}'"
            return "Inga Google Docs-dokument hittades i Drive."

        header = f"Hittade {len(files)} dokument"
        if query:
            header += f" (sokning: '{query}')"
        header += ":\n\n"

        lines: list[str] = [header]
        for i, f in enumerate(files, start=1):
            name = f.get("name", "(ingen titel)")
            doc_id = f.get("id", "")
            modified = f.get("modifiedTime", "")[:10]  # YYYY-MM-DD
            url = f.get("webViewLink", f"{DOCS_BASE_URL}/{doc_id}/edit")
            lines.append(f"{i}. **{name}**")
            lines.append(f"   ID: {doc_id}")
            lines.append(f"   Ändrad: {modified}")
            lines.append(f"   URL: {url}\n")

        return "\n".join(lines)

    except HttpError as e:
        logger.error("Google API-fel vid listning: %s", e)
        return f"Fel vid listning av dokument: {e}"
    except FileNotFoundError as e:
        return f"Autentiseringsfel: {e}"
    except Exception as e:
        logger.error("Oväntat fel: %s", e)
        return f"Oväntat fel: {e}"


# ============================================================================
# SHEETS TOOLS
# ============================================================================

@mcp.tool()
def get_sheet_info(spreadsheet_id: str) -> str:
    """Hämta metadata om ett Google Sheets-kalkylblad.

    Returnerar titel, lista över blad (flikar) med antal rader och kolumner.

    Args:
        spreadsheet_id: Spreadsheet-ID (finns i URL:en efter /spreadsheets/d/).

    Returns:
        Formaterad sammanfattning med bladnamn och dimensioner.
    """
    try:
        sheets_service = _get_sheets_service()
        spreadsheet = (
            sheets_service.spreadsheets()
            .get(spreadsheetId=spreadsheet_id, includeGridData=False)
            .execute()
        )

        title = spreadsheet.get("properties", {}).get("title", "(ingen titel)")
        url = f"{SHEETS_BASE_URL}/{spreadsheet_id}/edit"
        sheets = spreadsheet.get("sheets", [])

        lines = [f"Titel: {title}", f"URL: {url}", f"Antal blad: {len(sheets)}\n"]

        for sheet in sheets:
            props = sheet.get("properties", {})
            name = props.get("title", "(namnlöst blad)")
            grid = props.get("gridProperties", {})
            rows = grid.get("rowCount", "?")
            cols = grid.get("columnCount", "?")
            lines.append(f"  Blad: '{name}'  —  {rows} rader × {cols} kolumner")

        return "\n".join(lines)

    except HttpError as e:
        if e.resp.status == 404:
            return f"Kalkylbladet hittades inte: {spreadsheet_id}"
        if e.resp.status == 403:
            return f"Ingen åtkomst till kalkylbladet: {spreadsheet_id}"
        logger.error("Google API-fel vid get_sheet_info: %s", e)
        return f"Fel vid hämtning av info: {e}"
    except FileNotFoundError as e:
        return f"Autentiseringsfel: {e}"
    except Exception as e:
        logger.error("Oväntat fel: %s", e)
        return f"Oväntat fel: {e}"


@mcp.tool()
def read_sheet(
    spreadsheet_id: str,
    sheet_name: str = "Sheet1",
    range_name: Optional[str] = None,
    max_rows: int = 200,
) -> str:
    """Läs data från ett Google Sheets-blad och returnera som formaterad tabell.

    Args:
        spreadsheet_id: Spreadsheet-ID (finns i URL:en efter /spreadsheets/d/).
        sheet_name: Namn på blad/flik att läsa (default: 'Sheet1').
        range_name: Valfritt cellintervall t.ex. 'A1:F100'. Lämna tomt för hela bladet.
        max_rows: Maximalt antal rader att returnera (default: 200).

    Returns:
        Tab-separerad tabell med bladets innehåll och radantal.
    """
    try:
        sheets_service = _get_sheets_service()

        # Build A1 notation range
        if range_name:
            a1_range = f"'{sheet_name}'!{range_name}"
        else:
            a1_range = f"'{sheet_name}'"

        result = (
            sheets_service.spreadsheets()
            .values()
            .get(spreadsheetId=spreadsheet_id, range=a1_range)
            .execute()
        )

        values = result.get("values", [])

        if not values:
            return f"Bladet '{sheet_name}' är tomt eller innehåller inga data."

        # Limit rows
        total_rows = len(values)
        display_rows = values[:max_rows]
        truncated = total_rows > max_rows

        # Format as tab-separated table
        lines = ["\t".join(str(cell) for cell in row) for row in display_rows]
        table = "\n".join(lines)

        summary = f"Blad: '{sheet_name}'  —  {total_rows} rader, {len(values[0])} kolumner"
        if truncated:
            summary += f" (visar {max_rows} av {total_rows})"

        return f"{summary}\n\n{table}"

    except HttpError as e:
        if e.resp.status == 404:
            return f"Kalkylbladet hittades inte: {spreadsheet_id}"
        if e.resp.status == 400:
            return f"Ogiltigt intervall eller bladnamn: '{sheet_name}'. Kontrollera att bladnamnet stämmer."
        if e.resp.status == 403:
            return f"Ingen åtkomst till kalkylbladet: {spreadsheet_id}"
        logger.error("Google API-fel vid read_sheet: %s", e)
        return f"Fel vid läsning av blad: {e}"
    except FileNotFoundError as e:
        return f"Autentiseringsfel: {e}"
    except Exception as e:
        logger.error("Oväntat fel: %s", e)
        return f"Oväntat fel: {e}"


@mcp.tool()
def append_sheet_row(
    spreadsheet_id: str,
    values: list[str],
    sheet_name: str = "Sheet1",
    raw: bool = False,
) -> str:
    """Lägg till en rad sist i ett Google Sheets-blad.

    Raden läggs efter sista befintliga raden med data. Inget skrivs över.

    Args:
        spreadsheet_id: Spreadsheet-ID (finns i URL:en efter /spreadsheets/d/).
        values: Cellvärden för raden, en sträng per kolumn från vänster.
        sheet_name: Namn på blad/flik att skriva till (default: 'Sheet1').
        raw: Om True sparas värden exakt som strängar. Om False (default) tolkar
             Sheets datum, tal och formler som om de skrevs in manuellt.

    Returns:
        Bekräftelse med vilket cellintervall som skrevs och URL till bladet.
    """
    try:
        if not values:
            return "Inget skrevs: 'values' är tom. Ange minst ett cellvärde."

        sheets_service = _get_sheets_service()

        # Escape single quotes in sheet name for A1 notation
        safe_name = sheet_name.replace("'", "''")
        a1_range = f"'{safe_name}'"

        result = (
            sheets_service.spreadsheets()
            .values()
            .append(
                spreadsheetId=spreadsheet_id,
                range=a1_range,
                valueInputOption="RAW" if raw else "USER_ENTERED",
                insertDataOption="INSERT_ROWS",
                body={"values": [[str(v) for v in values]]},
            )
            .execute()
        )

        updates = result.get("updates", {})
        updated_range = updates.get("updatedRange", a1_range)
        updated_cells = updates.get("updatedCells", len(values))
        url = f"{SHEETS_BASE_URL}/{spreadsheet_id}/edit"

        return (
            f"Rad tillagd i '{sheet_name}'.\n"
            f"Intervall: {updated_range}  ({updated_cells} celler)\n"
            f"URL: {url}"
        )

    except HttpError as e:
        if e.resp.status == 404:
            return f"Kalkylbladet hittades inte: {spreadsheet_id}"
        if e.resp.status == 400:
            return (
                f"Ogiltigt bladnamn: '{sheet_name}'. Kontrollera att fliken finns "
                f"— kör get_sheet_info för att lista blad."
            )
        if e.resp.status == 403:
            return f"Ingen skrivåtkomst till kalkylbladet: {spreadsheet_id}"
        logger.error("Google API-fel vid append_sheet_row: %s", e)
        return f"Fel vid tillägg av rad: {e}"
    except FileNotFoundError as e:
        return f"Autentiseringsfel: {e}"
    except Exception as e:
        logger.error("Oväntat fel: %s", e)
        return f"Oväntat fel: {e}"


@mcp.tool()
def list_sheets(query: str = "", max_results: int = 10) -> str:
    """Lista och sök bland Google Sheets-kalkylblad i Drive.

    Args:
        query: Valfri söksträng för fritextsökning i titlar/innehåll.
               Lämna tomt för att lista de senaste kalkylbladen.
        max_results: Maximalt antal resultat (default: 10, max: 100).

    Returns:
        Formaterad lista med kalkylbladstitlar, ID:n och URL:er.
    """
    try:
        drive_service = _get_drive_service()

        mime_filter = "mimeType='application/vnd.google-apps.spreadsheet'"
        if query:
            drive_query = f"{mime_filter} and fullText contains '{query}'"
        else:
            drive_query = mime_filter

        max_results = min(max(1, max_results), 100)

        result = (
            drive_service.files()
            .list(
                q=drive_query,
                pageSize=max_results,
                fields="files(id, name, modifiedTime, webViewLink)",
                orderBy="modifiedTime desc",
            )
            .execute()
        )

        files = result.get("files", [])

        if not files:
            if query:
                return f"Inga kalkylblad hittades för sökningen: '{query}'"
            return "Inga Google Sheets-kalkylblad hittades i Drive."

        header = f"Hittade {len(files)} kalkylblad"
        if query:
            header += f" (sökning: '{query}')"
        header += ":\n\n"

        lines: list[str] = [header]
        for i, f in enumerate(files, start=1):
            name = f.get("name", "(ingen titel)")
            sheet_id = f.get("id", "")
            modified = f.get("modifiedTime", "")[:10]
            url = f.get("webViewLink", f"{SHEETS_BASE_URL}/{sheet_id}/edit")
            lines.append(f"{i}. **{name}**")
            lines.append(f"   ID: {sheet_id}")
            lines.append(f"   Ändrad: {modified}")
            lines.append(f"   URL: {url}\n")

        return "\n".join(lines)

    except HttpError as e:
        logger.error("Google API-fel vid list_sheets: %s", e)
        return f"Fel vid listning av kalkylblad: {e}"
    except FileNotFoundError as e:
        return f"Autentiseringsfel: {e}"
    except Exception as e:
        logger.error("Oväntat fel: %s", e)
        return f"Oväntat fel: {e}"


# ============================================================================
# ENTRY POINT
# ============================================================================

def main() -> None:
    """Starta Google Docs MCP-server via stdio."""
    logger.info("Startar Google Docs MCP-server...")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
