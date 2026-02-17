"""
VISS MCP Server - Miljökvalitetsnormer och statusklassning
Hämtar data från Vatteninformationssystem Sverige (VISS) API

Version: 2.1.0
Författare: Länsstyrelsen Västra Götaland
Datum: 2026-02-16

VISS API: https://viss.lansstyrelsen.se/API
Alla anrop görs som GET mot bas-URL med ?method=...&apikey=...&format=Json
Dokumentation: https://viss.lansstyrelsen.se/APIHelp/Samples.aspx
"""

from mcp.server.fastmcp import FastMCP
import httpx
from typing import Dict, List, Any
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

mcp = FastMCP("viss-mcp")

VISS_BASE_URL = "https://viss.lansstyrelsen.se/API"
VISS_API_KEY = os.environ.get("VISS_API_KEY", "")

client = httpx.Client(timeout=30.0)


def _viss_get(method: str, extra_params: dict = None) -> Any:
    """Anropa VISS API med method som query-parameter."""
    params = {
        "method": method,
        "apikey": VISS_API_KEY,
        "format": "Json",
    }
    if extra_params:
        params.update(extra_params)

    logger.info(f"VISS API: {method} params={extra_params}")
    response = client.get(VISS_BASE_URL, params=params)
    response.raise_for_status()
    return response.json()


@mcp.tool()
def search_waterbody(
    name: str = None,
    eu_cd: str = None,
    water_category: str = None,
    county_code: str = None,
    municipality_code: str = None,
) -> Dict[str, Any]:
    """
    Sök efter vattenförekomst i VISS

    Args:
        name: Namn på vattenförekomst (fritext)
        eu_cd: EU_CD identifierare (t.ex. 'SE641190-129229')
        water_category: Vattenkategori ('LW'=sjö, 'RW'=vattendrag, 'CW'=kust, 'GW'=grundvatten)
        county_code: Länskod (t.ex. '14' för Västra Götaland)
        municipality_code: Kommunkod (t.ex. '1441' för Lerum)

    Returns:
        Dict med matchande vattenförekomster
    """
    try:
        params = {}
        if name:
            params["freetextsearch"] = name
        if eu_cd:
            params["watereucd"] = eu_cd
        if water_category:
            params["watercategory"] = water_category
        if county_code:
            params["countycode"] = county_code
        if municipality_code:
            params["municipalitycode"] = municipality_code

        data = _viss_get("waters", params)
        items = data if isinstance(data, list) else []

        waterbodies = []
        for wb in items:
            waterbodies.append({
                "eu_cd": wb.get("EU_CD", ""),
                "ms_cd": wb.get("MS_CD", ""),
                "name": wb.get("Name", ""),
                "swedish_name": wb.get("SwedishName", ""),
                "category": wb.get("WaterKind", ""),
                "rbd": wb.get("RBD", ""),
                "length_km": wb.get("LengthKM"),
                "surface_area_km2": wb.get("SurfaceAreaKM2"),
                "basin": wb.get("Basin", ""),
            })

        return {
            "success": True,
            "count": len(waterbodies),
            "waterbodies": waterbodies,
            "human_readable": _format_waterbody_summary(waterbodies),
        }

    except Exception as e:
        logger.error(f"Fel vid sökning av vattenförekomst: {e}")
        return {
            "success": False,
            "error": str(e),
            "message": "Kunde inte söka i VISS. Kontrollera API-nyckel och försök igen.",
        }


@mcp.tool()
def get_status_classification(
    eu_cd: str,
    management_cycle: int = 3,
) -> Dict[str, Any]:
    """
    Hämta statusklassificering för vattenförekomst

    Args:
        eu_cd: EU_CD för vattenförekomst
        management_cycle: Förvaltningscykel (1, 2, eller 3. Standard: 3)

    Returns:
        Dict med statusklassificering inkl. alla kvalitetsfaktorer med EK-värden
    """
    try:
        data = _viss_get("waterclassificationmotivations", {
            "watereucd": eu_cd,
            "managementcycleidentifier": str(management_cycle),
        })
        items = data if isinstance(data, list) else []

        if not items:
            return {
                "success": False,
                "eu_cd": eu_cd,
                "message": f"Ingen klassning hittades för {eu_cd} i cykel {management_cycle}",
            }

        item = items[0]
        motivations = item.get("Motivations", [])

        classification = {
            "eu_cd": item.get("EU_CD", eu_cd),
            "name": item.get("Name", ""),
            "category": item.get("WaterCategory", ""),
            "rbd": item.get("RBDSwedishName", ""),
            "municipalities": [m.get("Name", "") for m in item.get("Municipalities", [])],
            "ecological_status": None,
            "chemical_status": None,
            "chemical_status_excl_hg": None,
            "quality_elements": [],
        }

        for m in motivations:
            param = m.get("Parameter", "")
            name = m.get("ParameterSwedishName", "")
            status = m.get("ClassificationSwedishName", "")
            conf = m.get("ClassificationConfidence") or {}
            ek = conf.get("EcologicalQuote")
            confidence = conf.get("ConfidenceIndicator", "")

            if param == "ECO_STAT":
                classification["ecological_status"] = status
            elif param == "CHEM_STAT":
                classification["chemical_status"] = status
            elif param == "CHEM_STAT_NON_HG":
                classification["chemical_status_excl_hg"] = status
            elif not param.startswith("RISK_") and not param.startswith("SWB_TYPES"):
                classification["quality_elements"].append({
                    "parameter_id": param,
                    "name": name,
                    "status": status,
                    "ek_value": ek,
                    "confidence": confidence,
                    "motivation": m.get("Motivation", ""),
                })

        return {
            "success": True,
            "eu_cd": eu_cd,
            "classification": classification,
            "human_readable": _format_classification_summary(classification),
        }

    except Exception as e:
        logger.error(f"Fel vid hämtning av statusklassificering: {e}")
        return {
            "success": False,
            "error": str(e),
            "eu_cd": eu_cd,
            "message": f"Kunde inte hämta statusklassificering för {eu_cd}",
        }


@mcp.tool()
def get_environmental_quality_standard(eu_cd: str) -> Dict[str, Any]:
    """
    Hämta miljökvalitetsnorm (MKN) för vattenförekomst

    Args:
        eu_cd: EU_CD för vattenförekomst (t.ex. 'SE641190-129229')

    Returns:
        Dict med MKN-information
    """
    try:
        data = _viss_get("mkn", {"watereucd": eu_cd})
        items = data if isinstance(data, list) else []

        if not items:
            return {
                "success": True,
                "eu_cd": eu_cd,
                "mkn": {
                    "ecological_status_target": "God",
                    "chemical_status_target": "God",
                    "target_year": 2027,
                    "exceptions": [],
                },
                "message": "Inga MKN hittades, använder standardvärden (God status 2027)",
            }

        # MKN-data per vattenförekomst
        item = items[0]
        mkn = {
            "eu_cd": item.get("EU_CD", eu_cd),
            "name": item.get("Name", ""),
            "sections": [],
        }

        for section in item.get("MKNSections", item.get("Sections", [])):
            mkn["sections"].append({
                "parameter": section.get("ParameterSwedishName", section.get("Parameter", "")),
                "norm_value": section.get("ClassificationSwedishName", section.get("NormValue", "")),
                "target_year": section.get("TargetYear"),
                "exception": section.get("ExemptionType"),
            })

        return {
            "success": True,
            "eu_cd": eu_cd,
            "mkn": mkn,
            "raw_data": items,
            "human_readable": _format_mkn_summary(mkn),
        }

    except Exception as e:
        logger.error(f"Fel vid hämtning av MKN: {e}")
        return {
            "success": False,
            "error": str(e),
            "eu_cd": eu_cd,
            "message": f"Kunde inte hämta MKN för {eu_cd}.",
        }


@mcp.tool()
def check_mkn_compliance(eu_cd: str, current_status: str) -> Dict[str, Any]:
    """
    Kontrollera om vattenförekomst uppfyller miljökvalitetsnorm

    Args:
        eu_cd: EU_CD för vattenförekomst
        current_status: Nuvarande ekologisk status (Hög/God/Måttlig/Otillfredsställande/Dålig)

    Returns:
        Dict med compliance-bedömning
    """
    from datetime import datetime

    status_values = {
        "Hög": 5, "God": 4, "Måttlig": 3,
        "Otillfredsställande": 2, "Dålig": 1,
    }

    try:
        mkn_result = get_environmental_quality_standard(eu_cd)
        if not mkn_result.get("success"):
            return mkn_result

        mkn = mkn_result["mkn"]
        # Default target
        target_status = "God"
        target_year = 2027

        for section in mkn.get("sections", []):
            param = (section.get("parameter") or "").lower()
            if "ekologisk" in param:
                target_status = section.get("norm_value", "God")
                if section.get("target_year"):
                    target_year = int(section["target_year"])

        current_value = status_values.get(current_status, 0)
        target_value = status_values.get(target_status, 4)
        compliant = current_value >= target_value
        years_remaining = target_year - datetime.now().year

        return {
            "success": True,
            "eu_cd": eu_cd,
            "compliance": {
                "compliant": compliant,
                "current_status": current_status,
                "target_status": target_status,
                "target_year": target_year,
                "years_remaining": years_remaining,
                "action_needed": not compliant,
                "urgency": "high" if years_remaining < 3 and not compliant else "normal",
            },
            "human_readable": _format_compliance_summary(
                compliant, current_status, target_status, target_year, years_remaining
            ),
        }

    except Exception as e:
        logger.error(f"Fel vid MKN-compliance kontroll: {e}")
        return {
            "success": False,
            "error": str(e),
            "eu_cd": eu_cd,
        }


@mcp.tool()
def get_measures(eu_cd: str) -> Dict[str, Any]:
    """
    Hämta åtgärder för vattenförekomst

    Args:
        eu_cd: EU_CD för vattenförekomst

    Returns:
        Dict med åtgärder
    """
    try:
        data = _viss_get("measures", {"watereucd": eu_cd})
        items = data if isinstance(data, list) else []

        measures = []
        for item in items:
            measures.append({
                "id": item.get("MeasureID", item.get("ID", "")),
                "name": item.get("MeasureName", item.get("Name", "")),
                "type": item.get("MeasureType", item.get("Type", "")),
                "status": item.get("MeasureStatus", item.get("Status", "")),
                "responsible": item.get("ResponsibleAuthority", item.get("Auth", "")),
            })

        return {
            "success": True,
            "eu_cd": eu_cd,
            "count": len(measures),
            "measures": measures,
            "human_readable": _format_measures_summary(measures, eu_cd),
        }

    except Exception as e:
        logger.error(f"Fel vid hämtning av åtgärder: {e}")
        return {
            "success": False,
            "error": str(e),
            "eu_cd": eu_cd,
            "message": f"Kunde inte hämta åtgärder för {eu_cd}",
        }


@mcp.tool()
def get_quality_factors() -> Dict[str, Any]:
    """
    Hämta lista över alla kvalitetsfaktorer definierade i VISS.
    OBS: Returnerar systemets kvalitetsfaktorer, inte per vattenförekomst.
    Per-vatten kvalitetsfaktorer finns i get_status_classification.

    Returns:
        Dict med kvalitetsfaktorer
    """
    try:
        data = _viss_get("qualityfactors")
        items = data if isinstance(data, list) else []

        return {
            "success": True,
            "count": len(items),
            "factors": items,
        }

    except Exception as e:
        logger.error(f"Fel vid hämtning av kvalitetsfaktorer: {e}")
        return {
            "success": False,
            "error": str(e),
        }


# =============================================================================
# Formateringsfunktioner
# =============================================================================

def _format_waterbody_summary(waterbodies: List[Dict]) -> str:
    if not waterbodies:
        return "Inga vattenförekomster hittades"
    summary = f"=== Hittade {len(waterbodies)} vattenförekomst(er) ===\n\n"
    for wb in waterbodies[:5]:
        summary += f"Namn: {wb.get('swedish_name') or wb.get('name', 'N/A')}\n"
        summary += f"EU_CD: {wb.get('eu_cd', 'N/A')}\n"
        summary += f"Kategori: {wb.get('category', 'N/A')}\n"
        summary += f"Distrikt: {wb.get('rbd', 'N/A')}\n\n"
    if len(waterbodies) > 5:
        summary += f"... och {len(waterbodies) - 5} fler"
    return summary


def _format_classification_summary(classification: Dict) -> str:
    eu_cd = classification.get("eu_cd", "N/A")
    name = classification.get("name", "")
    summary = f"=== Statusklassificering: {name} ({eu_cd}) ===\n\n"
    summary += f"Ekologisk status: {classification.get('ecological_status', 'N/A')}\n"
    summary += f"Kemisk status: {classification.get('chemical_status', 'N/A')}\n"
    summary += f"Kemisk (exkl Hg): {classification.get('chemical_status_excl_hg', 'N/A')}\n"
    qe = classification.get("quality_elements", [])
    if qe:
        summary += f"\nKvalitetsfaktorer ({len(qe)}):\n"
        for e in qe[:15]:
            ek = e.get("ek_value")
            ek_str = f" (EK={ek:.2f})" if ek is not None else ""
            summary += f"  - {e.get('name')}: {e.get('status')}{ek_str}\n"
    return summary


def _format_mkn_summary(mkn: Dict) -> str:
    summary = f"=== MKN: {mkn.get('name', '')} ({mkn.get('eu_cd', '')}) ===\n\n"
    for s in mkn.get("sections", []):
        summary += f"  {s.get('parameter')}: {s.get('norm_value')}"
        if s.get("target_year"):
            summary += f" (målår {s['target_year']})"
        if s.get("exception"):
            summary += f" [undantag: {s['exception']}]"
        summary += "\n"
    return summary


def _format_compliance_summary(
    compliant: bool, current: str, target: str, year: int, years_left: int
) -> str:
    summary = "=== MKN-Compliance Kontroll ===\n\n"
    summary += f"Status: {'UPPFYLLER MKN' if compliant else 'UPPFYLLER EJ MKN'}\n\n"
    summary += f"Nuvarande status: {current}\n"
    summary += f"Målstatus (MKN): {target}\n"
    summary += f"Målår: {year}\n"
    summary += f"Tid kvar: {years_left} år\n"
    if not compliant:
        summary += "\nÅTGÄRDER KRÄVS för att uppnå MKN\n"
        if years_left < 3:
            summary += "HÖG PRIORITET - Mindre än 3 år till målår"
    return summary


def _format_measures_summary(measures: List[Dict], eu_cd: str) -> str:
    if not measures:
        return f"Inga åtgärder hittades för {eu_cd}"
    summary = f"=== Åtgärder för {eu_cd} ({len(measures)} st) ===\n\n"
    for m in measures[:10]:
        summary += f"  {m.get('name', 'N/A')}\n"
        summary += f"  Typ: {m.get('type', 'N/A')} | Status: {m.get('status', 'N/A')}\n\n"
    if len(measures) > 10:
        summary += f"... och {len(measures) - 10} fler åtgärder"
    return summary


def main():
    mcp.run()


if __name__ == "__main__":
    main()
