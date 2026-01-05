"""
SHARK MCP Server - Kustvattendata från SMHI
Uppdaterad med verifierade API-endpoints från testning 2025-12-15

Version: 2.1.0
Författare: Länsstyrelsen Västra Götaland
Datum: 2025-12-15

Ändringar från v2.0.0:
- Korrigerad response-struktur ("headers" istället för "columns")
- Korrigerad request-struktur (params + query istället för flat)
- Lokal filtrering på stationer (API-filter fungerar inte)
- Stöd för pagination (> 200 rader)
"""

from mcp.server.fastmcp import FastMCP
import httpx
from typing import Dict, List, Optional, Any
import json
from datetime import datetime
import logging

# Konfigurera logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initiera FastMCP
mcp = FastMCP("shark-mcp")

# SHARK API bas-URL
SHARK_BASE_URL = "https://shark.smhi.se"

# HTTP-klient med timeout
client = httpx.Client(timeout=60.0)


@mcp.tool()
def list_datasets(limit: int = 100) -> Dict[str, Any]:
    """
    Lista alla tillgängliga SHARK dataset

    Args:
        limit: Max antal dataset att returnera (standard: 100)

    Returns:
        Dict med dataset-lista
    """
    try:
        url = f"{SHARK_BASE_URL}/api/dataset/table.json"
        response = client.get(url)
        response.raise_for_status()
        data = response.json()

        # OBS: Använder "header" (singular) för detta endpoint
        header = data.get('header', [])
        rows = data.get('rows', [])

        # Konvertera till lista av dicts
        datasets = []
        for row in rows[:limit]:
            dataset = dict(zip(header, row))
            datasets.append(dataset)

        return {
            "success": True,
            "count": len(datasets),
            "header": header,
            "datasets": datasets
        }

    except Exception as e:
        logger.error(f"Fel vid hämtning av dataset-lista: {e}")
        return {
            "success": False,
            "error": str(e),
            "message": "Kunde inte hämta dataset från SHARK"
        }


@mcp.tool()
def search_coastal_data(
    from_year: int,
    to_year: int,
    sea_basins: List[str],
    table_view: str = "sharkdata_physicalchemical",
    filter_stations: List[str] = None,
    data_types: List[str] = None,
    row_offset: int = 0,
    max_rows: int = 200
) -> Dict[str, Any]:
    """
    Sök kustvattendata med specifika filter

    Args:
        from_year: Startår (OBLIGATORISK)
        to_year: Slutår (OBLIGATORISK)
        sea_basins: Havsområden (OBLIGATORISK) - ["17 - Skagerrak"], ["16 - Kattegatt"]
        table_view: Datatyp - sharkdata_physicalchemical (default), phytoplankton, etc.
        filter_stations: Filtrera på stationsnamn EFTER API-anrop (lokal filtrering)
        data_types: Datatyper - ["Physical and Chemical"] (default om None)
        row_offset: Offset för pagination (default: 0)
        max_rows: Max antal rader (max 200 per request från API)

    Returns:
        Dict med sökresultat

    OBS: Stations-filter i API:et fungerar inte! Använd filter_stations för lokal filtrering.
    """
    try:
        url = f"{SHARK_BASE_URL}/api/sample/table"

        # Default dataTypes
        if data_types is None:
            data_types = ["Physical and Chemical"]

        # Bygg request body med tvånivå-struktur
        payload = {
            "params": {
                "tableView": table_view
            },
            "query": {
                "fromYear": from_year,
                "toYear": to_year,
                "dataTypes": data_types,
                "seaBasins": sea_basins,
                "rowOffset": row_offset
            }
        }

        # POST request
        response = client.post(
            url,
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        response.raise_for_status()
        data = response.json()

        # OBS: Använder "headers" (plural) för detta endpoint
        headers = data.get('headers', [])
        rows = data.get('rows', [])
        row_limit = data.get('rowLimit', 200)

        # Lokal filtrering på stationer om specificerat
        if filter_stations and 'Stationsnamn' in headers:
            station_idx = headers.index('Stationsnamn')
            original_count = len(rows)

            rows = [
                row for row in rows
                if station_idx < len(row) and row[station_idx] in filter_stations
            ]

            logger.info(f"Filtrerade {original_count} → {len(rows)} rader på stationer: {filter_stations}")

        # Begränsa antal rader
        rows = rows[:max_rows]

        return {
            "success": True,
            "from_year": from_year,
            "to_year": to_year,
            "sea_basins": sea_basins,
            "table_view": table_view,
            "headers": headers,
            "row_count": len(rows),
            "row_limit": row_limit,
            "row_offset": row_offset,
            "rows": rows,
            "truncated": len(rows) >= row_limit,
            "note": "Max 200 rader per request. Använd row_offset för pagination."
        }

    except Exception as e:
        logger.error(f"Fel vid sökning av kustdata: {e}")
        return {
            "success": False,
            "error": str(e),
            "message": "Kunde inte hämta data från SHARK"
        }


@mcp.tool()
def search_coastal_data_paginated(
    from_year: int,
    to_year: int,
    sea_basins: List[str],
    table_view: str = "sharkdata_physicalchemical",
    filter_stations: List[str] = None,
    max_total_rows: int = 1000
) -> Dict[str, Any]:
    """
    Hämta kustvattendata med automatisk pagination för >200 rader

    Args:
        from_year: Startår
        to_year: Slutår
        sea_basins: Havsområden
        table_view: Datatyp
        filter_stations: Filtrera på stationer (lokal filtrering)
        max_total_rows: Max totalt antal rader att hämta (default: 1000)

    Returns:
        Dict med all data från alla sidor
    """
    try:
        all_rows = []
        offset = 0
        headers = []

        while len(all_rows) < max_total_rows:
            result = search_coastal_data(
                from_year=from_year,
                to_year=to_year,
                sea_basins=sea_basins,
                table_view=table_view,
                filter_stations=filter_stations,
                row_offset=offset,
                max_rows=200
            )

            if not result.get('success'):
                break

            headers = result.get('headers', headers)
            rows = result.get('rows', [])

            if not rows:
                break

            all_rows.extend(rows)
            offset += len(rows)

            # Om mindre än 200 rader, sista batchen
            if len(rows) < 200:
                break

        return {
            "success": True,
            "from_year": from_year,
            "to_year": to_year,
            "sea_basins": sea_basins,
            "headers": headers,
            "row_count": len(all_rows),
            "rows": all_rows[:max_total_rows],
            "pages_fetched": (offset // 200) + 1
        }

    except Exception as e:
        logger.error(f"Fel vid paginerad sökning: {e}")
        return {
            "success": False,
            "error": str(e),
            "message": "Kunde inte hämta paginerad data"
        }


@mcp.tool()
def get_filter_options() -> Dict[str, Any]:
    """
    Hämta alla tillgängliga filtervärden (stationer, områden, parametrar)

    Returns:
        Dict med alla tillgängliga filteralternativ
    """
    try:
        url = f"{SHARK_BASE_URL}/api/options"
        response = client.get(url)
        response.raise_for_status()
        options = response.json()

        # Summera info
        summary = {}
        if 'stations' in options:
            summary['stations_count'] = len(options['stations'])
            # Hitta Gullmarn-stationer
            gullmarn = [s for s in options['stations'] if 'GULLM' in s.upper()]
            if gullmarn:
                summary['gullmarn_stations'] = gullmarn

        if 'seaBasins' in options:
            summary['sea_basins'] = options['seaBasins']

        if 'parameters' in options:
            summary['parameters_count'] = len(options['parameters'])

        return {
            "success": True,
            "options": options,
            "summary": summary,
            "note": "Använd dessa värden för att filtrera i search_coastal_data"
        }

    except Exception as e:
        logger.error(f"Fel vid hämtning av filteralternativ: {e}")
        return {
            "success": False,
            "error": str(e),
            "message": "Kunde inte hämta filteralternativ från SHARK"
        }


@mcp.tool()
def get_coastal_chemistry(
    area: str,
    year_start: int = 2018,
    year_end: int = 2024,
    station_filter: List[str] = None
) -> Dict[str, Any]:
    """
    Hämta vattenkemidata för kustvatten (för statusklassning)

    Args:
        area: Havsområde - välj mellan:
            - "17 - Skagerrak"
            - "16 - Kattegatt"
            - "13 - Egentliga Östersjön"
            - "14 - Bottenhavet"
            - "15 - Bottenviken"
        year_start: Startår (standard: 2018)
        year_end: Slutår (standard: 2024)
        station_filter: Filtrera på specifika stationer (t.ex. ["GULLMARN 1"])

    Returns:
        Dict med aggregerad vattenkemidata för statusklassning
    """
    try:
        # Hämta data med pagination
        result = search_coastal_data_paginated(
            from_year=year_start,
            to_year=year_end,
            sea_basins=[area],
            table_view="sharkdata_physicalchemical",
            filter_stations=station_filter,
            max_total_rows=2000
        )

        if not result.get('success'):
            return result

        # Formatera för statusklassning
        rows = result.get('rows', [])
        headers = result.get('headers', [])

        # Analysera parametrar
        parameters_summary = {}
        if 'Parameter' in headers and 'Stationsnamn' in headers:
            param_idx = headers.index('Parameter')
            station_idx = headers.index('Stationsnamn')

            # Räkna parametrar per station
            for row in rows:
                if param_idx < len(row) and station_idx < len(row):
                    param = row[param_idx]
                    station = row[station_idx]

                    if param not in parameters_summary:
                        parameters_summary[param] = {'count': 0, 'stations': set()}

                    parameters_summary[param]['count'] += 1
                    parameters_summary[param]['stations'].add(station)

        return {
            "success": True,
            "area": area,
            "year_range": f"{year_start}-{year_end}",
            "headers": headers,
            "row_count": len(rows),
            "rows": rows,
            "parameters_summary": {
                k: {'count': v['count'], 'stations': list(v['stations'])}
                for k, v in parameters_summary.items()
            },
            "human_readable": format_coastal_chemistry_summary(rows, headers, area, station_filter)
        }

    except Exception as e:
        logger.error(f"Fel vid hämtning av kustvattendata: {e}")
        return {
            "success": False,
            "error": str(e),
            "area": area,
            "message": f"Kunde inte hämta kustvattendata för {area}"
        }


@mcp.tool()
def list_available_areas() -> Dict[str, Any]:
    """
    Lista tillgängliga havsområden i SHARK

    Returns:
        Dict med områden och beskrivningar
    """
    areas = {
        "17 - Skagerrak": {
            "description": "Västkusten, norr om Kattegatt",
            "coordinates": "Lat: 57.5-59.5, Lon: 10-12",
            "typical_stations": ["GULLMARN 1-8", "BYFJORDEN", "KOSTERFJORDEN"]
        },
        "16 - Kattegatt": {
            "description": "Mellan Sverige och Danmark",
            "coordinates": "Lat: 55.5-57.5, Lon: 11-13",
            "typical_stations": ["ANHOLT E", "FLADEN"]
        },
        "13 - Egentliga Östersjön": {
            "description": "Centrala Östersjön",
            "typical_stations": ["BY31", "BORNHOLM BASIN"]
        },
        "14 - Bottenhavet": {
            "description": "Mellersta Östersjön"
        },
        "15 - Bottenviken": {
            "description": "Norra Östersjön"
        }
    }

    return {
        "success": True,
        "areas": areas,
        "count": len(areas),
        "note": "Använd dessa namn exakt som de är i get_coastal_chemistry eller search_coastal_data"
    }


def format_coastal_chemistry_summary(
    rows: List,
    headers: List,
    area: str,
    station_filter: List[str] = None
) -> str:
    """
    Formatera kustvattendata till läsbar text

    Args:
        rows: Datarader
        headers: Kolumnnamn
        area: Geografiskt område
        station_filter: Stationsfilter

    Returns:
        Läsbar sammanfattning
    """
    if not rows:
        return f"Ingen data hittades för {area}"

    summary = f"=== Kustvattendata för {area} ===\n\n"
    summary += f"Antal mätningar: {len(rows)}\n"

    if station_filter:
        summary += f"Stationer: {', '.join(station_filter)}\n"

    # Hitta unika stationer
    if 'Stationsnamn' in headers:
        station_idx = headers.index('Stationsnamn')
        stations = set(row[station_idx] for row in rows if station_idx < len(row))
        summary += f"Unika stationer: {len(stations)}\n"

    # Hitta parametrar
    if 'Parameter' in headers:
        param_idx = headers.index('Parameter')
        params = set(row[param_idx] for row in rows if param_idx < len(row))
        summary += f"Parametrar: {len(params)}\n"

        # Viktiga för statusklassning
        important = ['Tot-N', 'Tot-P', 'Salinity', 'Temperature', 'Chlorophyll']
        found = [p for p in params if any(imp in p for imp in important)]
        if found:
            summary += f"\nStatusklassningsparametrar hittade:\n"
            for param in found[:10]:
                count = sum(1 for row in rows if param_idx < len(row) and row[param_idx] == param)
                summary += f"  - {param}: {count} mätningar\n"

    return summary


if __name__ == "__main__":
    mcp.run()
