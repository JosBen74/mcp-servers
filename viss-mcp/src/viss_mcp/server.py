"""
VISS MCP Server - Miljökvalitetsnormer och statusklassning
Automatisk hämtning från Vatteninformationssystem Sverige

Version: 1.0.0
Författare: Länsstyrelsen Västra Götaland
Datum: 2025-12-14
"""

from mcp.server.fastmcp import FastMCP
import httpx
from typing import Dict, List, Optional, Any
import json
from datetime import datetime
import logging
import xml.etree.ElementTree as ET

# Konfigurera logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initiera FastMCP
mcp = FastMCP("viss-mcp")

# VISS API bas-URL
VISS_BASE_URL = "https://viss.lansstyrelsen.se/api"

# HTTP-klient med timeout
client = httpx.Client(timeout=30.0)


@mcp.tool()
def search_waterbody(
    name: str = None,
    eu_cd: str = None,
    water_category: str = None,
    county: str = None
) -> Dict[str, Any]:
    """
    Sök efter vattenförekomst i VISS
    
    Args:
        name: Namn på vattenförekomst (fritext)
        eu_cd: EU_CD identifierare (t.ex. 'SE658352-163189')
        water_category: Vattenkategori ('LW'=sjö, 'RW'=vattendrag, 'CW'=kust)
        county: Län (t.ex. 'Västra Götaland')
        
    Returns:
        Dict med matchande vattenförekomster
    """
    try:
        params = {}
        
        if name:
            params['name'] = name
        if eu_cd:
            params['waterpublicid'] = eu_cd
        if water_category:
            params['watercategoryidentifier'] = water_category
        if county:
            params['county'] = county
        
        # VISS API endpoint för vattenförekomster
        url = f"{VISS_BASE_URL}/waterbodies"
        
        response = client.get(url, params=params)
        response.raise_for_status()
        
        # Parse XML-svar (VISS returnerar primärt XML)
        root = ET.fromstring(response.content)
        
        waterbodies = []
        for wb in root.findall('.//Waterbody'):
            waterbody = {
                "eu_cd": wb.findtext('EUCD'),
                "name": wb.findtext('Name'),
                "category": wb.findtext('Category'),
                "type": wb.findtext('Type'),
                "county": wb.findtext('County'),
                "district": wb.findtext('WaterDistrict')
            }
            waterbodies.append(waterbody)
        
        return {
            "success": True,
            "count": len(waterbodies),
            "waterbodies": waterbodies,
            "human_readable": format_waterbody_summary(waterbodies)
        }
        
    except Exception as e:
        logger.error(f"Fel vid sökning av vattenförekomst: {e}")
        return {
            "success": False,
            "error": str(e),
            "message": "Kunde inte söka i VISS. Använd webbgränssnittet: https://viss.lansstyrelsen.se/"
        }


@mcp.tool()
def get_environmental_quality_standard(eu_cd: str) -> Dict[str, Any]:
    """
    Hämta miljökvalitetsnorm (MKN) för vattenförekomst
    
    Args:
        eu_cd: EU_CD för vattenförekomst (t.ex. 'SE658352-163189')
        
    Returns:
        Dict med MKN-information
    """
    try:
        params = {'waterpublicid': eu_cd}
        url = f"{VISS_BASE_URL}/environmentalqualitystandards"
        
        response = client.get(url, params=params)
        response.raise_for_status()
        
        root = ET.fromstring(response.content)
        
        mkn = {
            "eu_cd": eu_cd,
            "ecological_status": {},
            "chemical_status": {},
            "target_year": None,
            "justification": None
        }
        
        # Parse ekologisk status
        eco_elem = root.find('.//EcologicalStatus')
        if eco_elem is not None:
            mkn["ecological_status"] = {
                "target": eco_elem.findtext('Target'),
                "current": eco_elem.findtext('Current'),
                "classification": eco_elem.findtext('Classification')
            }
        
        # Parse kemisk status
        chem_elem = root.find('.//ChemicalStatus')
        if chem_elem is not None:
            mkn["chemical_status"] = {
                "target": chem_elem.findtext('Target'),
                "current": chem_elem.findtext('Current')
            }
        
        # Parse målår
        target_elem = root.find('.//TargetYear')
        if target_elem is not None:
            mkn["target_year"] = int(target_elem.text)
        
        # Parse motivering
        just_elem = root.find('.//Justification')
        if just_elem is not None:
            mkn["justification"] = just_elem.text
        
        return {
            "success": True,
            "eu_cd": eu_cd,
            "mkn": mkn,
            "human_readable": format_mkn_summary(mkn, eu_cd)
        }
        
    except Exception as e:
        logger.error(f"Fel vid hämtning av MKN: {e}")
        return {
            "success": False,
            "error": str(e),
            "eu_cd": eu_cd,
            "message": f"Kunde inte hämta MKN för {eu_cd}. Kontrollera i VISS manuellt."
        }


@mcp.tool()
def get_status_classification(eu_cd: str, cycle: int = 3) -> Dict[str, Any]:
    """
    Hämta statusklassificering för vattenförekomst
    
    Args:
        eu_cd: EU_CD för vattenförekomst
        cycle: Förvaltningscykel (1, 2, eller 3. Standard: 3)
        
    Returns:
        Dict med statusklassificering
    """
    try:
        params = {
            'waterpublicid': eu_cd,
            'cycle': cycle
        }
        url = f"{VISS_BASE_URL}/statusclassifications"
        
        response = client.get(url, params=params)
        response.raise_for_status()
        
        root = ET.fromstring(response.content)
        
        classification = {
            "eu_cd": eu_cd,
            "cycle": cycle,
            "ecological_status": None,
            "chemical_status": None,
            "quality_elements": [],
            "assessment_date": None
        }
        
        # Parse ekologisk status
        eco_elem = root.find('.//EcologicalStatus')
        if eco_elem is not None:
            classification["ecological_status"] = eco_elem.text
        
        # Parse kemisk status
        chem_elem = root.find('.//ChemicalStatus')
        if chem_elem is not None:
            classification["chemical_status"] = chem_elem.text
        
        # Parse kvalitetsfaktorer
        for qe in root.findall('.//QualityElement'):
            element = {
                "name": qe.findtext('Name'),
                "status": qe.findtext('Status'),
                "value": qe.findtext('Value')
            }
            classification["quality_elements"].append(element)
        
        # Parse bedömningsdatum
        date_elem = root.find('.//AssessmentDate')
        if date_elem is not None:
            classification["assessment_date"] = date_elem.text
        
        return {
            "success": True,
            "eu_cd": eu_cd,
            "classification": classification,
            "human_readable": format_classification_summary(classification)
        }
        
    except Exception as e:
        logger.error(f"Fel vid hämtning av statusklassificering: {e}")
        return {
            "success": False,
            "error": str(e),
            "eu_cd": eu_cd,
            "message": f"Kunde inte hämta statusklassificering för {eu_cd}"
        }


@mcp.tool()
def check_mkn_compliance(
    eu_cd: str,
    current_status: str
) -> Dict[str, Any]:
    """
    Kontrollera om vattenförekomst uppfyller miljökvalitetsnorm
    
    Args:
        eu_cd: EU_CD för vattenförekomst
        current_status: Nuvarande status (Hög/God/Måttlig/Otillfredsställande/Dålig)
        
    Returns:
        Dict med compliance-bedömning
    """
    # Statusvärden
    status_values = {
        "Hög": 5,
        "God": 4,
        "Måttlig": 3,
        "Otillfredsställande": 2,
        "Dålig": 1
    }
    
    try:
        # Hämta MKN
        mkn_result = get_environmental_quality_standard(eu_cd)
        
        if not mkn_result.get('success'):
            return mkn_result
        
        mkn = mkn_result['mkn']
        target_status = mkn['ecological_status'].get('target', 'God')
        target_year = mkn.get('target_year', 2027)
        
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
                "urgency": "high" if years_remaining < 3 and not compliant else "normal"
            },
            "human_readable": format_compliance_summary(
                compliant, current_status, target_status, target_year, years_remaining
            )
        }
        
    except Exception as e:
        logger.error(f"Fel vid MKN-compliance kontroll: {e}")
        return {
            "success": False,
            "error": str(e),
            "eu_cd": eu_cd,
            "message": f"Kunde inte kontrollera MKN-compliance för {eu_cd}"
        }


@mcp.tool()
def get_measures(
    eu_cd: str,
    status: str = "planned"
) -> Dict[str, Any]:
    """
    Hämta åtgärder för vattenförekomst
    
    Args:
        eu_cd: EU_CD för vattenförekomst
        status: Status på åtgärder ('planned', 'implemented', 'proposed')
        
    Returns:
        Dict med åtgärder
    """
    try:
        params = {
            'waterpublicid': eu_cd,
            'measurestatus': status
        }
        url = f"{VISS_BASE_URL}/measures"
        
        response = client.get(url, params=params)
        response.raise_for_status()
        
        root = ET.fromstring(response.content)
        
        measures = []
        for measure in root.findall('.//Measure'):
            m = {
                "id": measure.findtext('ID'),
                "name": measure.findtext('Name'),
                "type": measure.findtext('Type'),
                "status": measure.findtext('Status'),
                "responsible": measure.findtext('Responsible'),
                "target_year": measure.findtext('TargetYear')
            }
            measures.append(m)
        
        return {
            "success": True,
            "eu_cd": eu_cd,
            "status": status,
            "count": len(measures),
            "measures": measures,
            "human_readable": format_measures_summary(measures, eu_cd)
        }
        
    except Exception as e:
        logger.error(f"Fel vid hämtning av åtgärder: {e}")
        return {
            "success": False,
            "error": str(e),
            "eu_cd": eu_cd,
            "message": f"Kunde inte hämta åtgärder för {eu_cd}"
        }


def format_waterbody_summary(waterbodies: List[Dict]) -> str:
    """Formatera vattenförekomster till läsbar text"""
    if not waterbodies:
        return "Inga vattenförekomster hittades"
    
    summary = f"=== Hittade {len(waterbodies)} vattenförekomst(er) ===\n\n"
    
    for wb in waterbodies[:5]:
        summary += f"Namn: {wb.get('name', 'N/A')}\n"
        summary += f"EU_CD: {wb.get('eu_cd', 'N/A')}\n"
        summary += f"Kategori: {wb.get('category', 'N/A')}\n"
        summary += f"Län: {wb.get('county', 'N/A')}\n"
        summary += f"Vattendistrikt: {wb.get('district', 'N/A')}\n\n"
    
    if len(waterbodies) > 5:
        summary += f"... och {len(waterbodies) - 5} fler"
    
    return summary


def format_mkn_summary(mkn: Dict, eu_cd: str) -> str:
    """Formatera MKN till läsbar text"""
    eco = mkn.get('ecological_status', {})
    target = eco.get('target', 'N/A')
    current = eco.get('current', 'N/A')
    year = mkn.get('target_year', 'N/A')
    
    summary = f"=== Miljökvalitetsnorm för {eu_cd} ===\n\n"
    summary += f"Målstatus (ekologisk): {target}\n"
    summary += f"Nuvarande status: {current}\n"
    summary += f"Målår: {year}\n"
    
    return summary


def format_classification_summary(classification: Dict) -> str:
    """Formatera statusklassificering till läsbar text"""
    eu_cd = classification.get('eu_cd', 'N/A')
    eco = classification.get('ecological_status', 'N/A')
    chem = classification.get('chemical_status', 'N/A')
    
    summary = f"=== Statusklassificering för {eu_cd} ===\n\n"
    summary += f"Ekologisk status: {eco}\n"
    summary += f"Kemisk status: {chem}\n"
    
    qe = classification.get('quality_elements', [])
    if qe:
        summary += f"\nKvalitetsfaktorer ({len(qe)}):\n"
        for element in qe[:3]:
            summary += f"  - {element.get('name')}: {element.get('status')}\n"
    
    return summary


def format_compliance_summary(
    compliant: bool, 
    current: str, 
    target: str, 
    year: int,
    years_left: int
) -> str:
    """Formatera MKN-compliance till läsbar text"""
    summary = "=== MKN-Compliance Kontroll ===\n\n"
    summary += f"Status: {'✓ UPPFYLLER MKN' if compliant else '✗ UPPFYLLER EJ MKN'}\n\n"
    summary += f"Nuvarande status: {current}\n"
    summary += f"Målstatus (MKN): {target}\n"
    summary += f"Målår: {year}\n"
    summary += f"Tid kvar: {years_left} år\n\n"
    
    if not compliant:
        summary += "⚠ ÅTGÄRDER KRÄVS för att uppnå MKN\n"
        if years_left < 3:
            summary += "⚠ HÖG PRIORITET - Mindre än 3 år till målår"
    
    return summary


def format_measures_summary(measures: List[Dict], eu_cd: str) -> str:
    """Formatera åtgärder till läsbar text"""
    if not measures:
        return f"Inga åtgärder hittades för {eu_cd}"
    
    summary = f"=== Åtgärder för {eu_cd} ===\n\n"
    summary += f"Antal åtgärder: {len(measures)}\n\n"
    
    for m in measures[:5]:
        summary += f"• {m.get('name', 'N/A')}\n"
        summary += f"  Typ: {m.get('type', 'N/A')}\n"
        summary += f"  Status: {m.get('status', 'N/A')}\n"
        summary += f"  Ansvarig: {m.get('responsible', 'N/A')}\n\n"
    
    if len(measures) > 5:
        summary += f"... och {len(measures) - 5} fler åtgärder"
    
    return summary


if __name__ == "__main__":
    mcp.run()
