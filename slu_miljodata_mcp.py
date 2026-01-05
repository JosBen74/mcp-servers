#!/usr/bin/env python3
"""
SLU Miljödata MCP Server

MCP server för åtkomst till SLU:s miljödata-API (MVM - Mark-, Vatten- och Miljödata).
Ger strukturerad åtkomst till vattenkemi, biologiska observationer (makrofyter), 
och övervakningsdata för sjöar och vattendrag.

Datainnehåll:
- Vattenkemi (näringsämnen, metaller, organiska ämnen)
- Biologi (makrofyter, fisk, bottenfauna)
- Hydrologi (vattenstånd, flöden)
- Stationsmetadata (koordinater, EU_CD-koder)

API: https://miljodata.slu.se/MVM/OpenAPI
"""

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import Optional, List, Dict, Any, Literal
from enum import Enum
from datetime import datetime, date
import httpx
import json
import logging

# Initialize MCP server
mcp = FastMCP("slu_miljodata_mcp")

# Configuration - Using API Version 2 (OpenAPI Specification 3)
# Note: Public ticket shows "isAuthorized": false - may need dynamic token
BASE_URL = "https://miljodata.slu.se/api"
PUBLIC_TICKET = "PUJD93023KAS943HD"  # Public ticket (valid until 2026-10-31)
TIMEOUT = 60.0  # Moderate timeout

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================================
# ENUMS AND TYPES
# ============================================================================

class ResponseFormat(str, Enum):
    """Output format for tool responses."""
    MARKDOWN = "markdown"
    JSON = "json"


class DataType(str, Enum):
    """Types of environmental data available in MVM."""
    VATTENKEMI = "vattenkemi"
    MAKROFYTER = "makrofyter"
    FISK = "fisk"
    BOTTENFAUNA = "bottenfauna"
    HYDROLOGI = "hydrologi"


class WaterBody(str, Enum):
    """Type of water body."""
    LAKE = "sjö"
    STREAM = "vattendrag"
    COASTAL = "kustvatten"


# ============================================================================
# PYDANTIC INPUT MODELS
# ============================================================================

class SearchStationsInput(BaseModel):
    """Input for searching monitoring stations."""
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True)
    
    station_name: Optional[str] = Field(
        default=None,
        description="Station name to search for (partial match, e.g., 'Vänern', 'Mälaren')"
    )
    eu_cd: Optional[str] = Field(
        default=None,
        description="EU water body code (e.g., 'SE123456-123456')",
        min_length=5
    )
    water_body_type: Optional[WaterBody] = Field(
        default=None,
        description="Type of water body: 'sjö' (lake), 'vattendrag' (stream), 'kustvatten' (coastal)"
    )
    region: Optional[str] = Field(
        default=None,
        description="Geographic region or county (e.g., 'Västra Götaland', 'Stockholm')"
    )
    limit: int = Field(
        default=50,
        description="Maximum number of stations to return",
        ge=1,
        le=500
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' (human-readable) or 'json' (machine-readable)"
    )


class GetStationDetailsInput(BaseModel):
    """Input for retrieving detailed station information."""
    model_config = ConfigDict(str_strip_whitespace=True)
    
    station_id: str = Field(
        description="Station ID or EU_CD code",
        min_length=3
    )
    include_coordinates: bool = Field(
        default=True,
        description="Include coordinate information"
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' or 'json'"
    )


class GetObservationsInput(BaseModel):
    """Input for retrieving environmental observations."""
    model_config = ConfigDict(str_strip_whitespace=True)
    
    station_id: Optional[str] = Field(
        default=None,
        description="Station ID or EU_CD code to filter by"
    )
    eu_cd: Optional[str] = Field(
        default=None,
        description="EU water body code (alternative to station_id)"
    )
    data_type: DataType = Field(
        description="Type of data: 'vattenkemi', 'makrofyter', 'fisk', 'bottenfauna', 'hydrologi'"
    )
    parameter: Optional[str] = Field(
        default=None,
        description="Specific parameter to retrieve (e.g., 'totalfosfor', 'totalkväve', 'pH')"
    )
    start_date: Optional[date] = Field(
        default=None,
        description="Start date for observations (YYYY-MM-DD)"
    )
    end_date: Optional[date] = Field(
        default=None,
        description="End date for observations (YYYY-MM-DD)"
    )
    limit: int = Field(
        default=100,
        description="Maximum number of observations to return",
        ge=1,
        le=1000
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' or 'json'"
    )


class SearchParametersInput(BaseModel):
    """Input for searching available parameters."""
    model_config = ConfigDict(str_strip_whitespace=True)
    
    query: Optional[str] = Field(
        default=None,
        description="Search term for parameter name (e.g., 'fosfor', 'kväve', 'pH')"
    )
    data_type: Optional[DataType] = Field(
        default=None,
        description="Filter by data type"
    )
    limit: int = Field(
        default=50,
        description="Maximum results to return",
        ge=1,
        le=200
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' or 'json'"
    )


class GetWaterChemistryInput(BaseModel):
    """Input for retrieving water chemistry data."""
    model_config = ConfigDict(str_strip_whitespace=True)
    
    eu_cd: str = Field(
        description="EU water body code (e.g., 'SE123456-123456')",
        min_length=5
    )
    parameters: Optional[List[str]] = Field(
        default=None,
        description="List of parameters to retrieve (e.g., ['totalfosfor', 'totalkväve']). If None, returns all available."
    )
    start_year: Optional[int] = Field(
        default=None,
        description="Start year for time series",
        ge=1900,
        le=2100
    )
    end_year: Optional[int] = Field(
        default=None,
        description="End year for time series",
        ge=1900,
        le=2100
    )
    calculate_statistics: bool = Field(
        default=True,
        description="Calculate basic statistics (mean, min, max, trend)"
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' or 'json'"
    )


class GetMacrophytesInput(BaseModel):
    """Input for retrieving macrophyte (aquatic plant) data."""
    model_config = ConfigDict(str_strip_whitespace=True)
    
    eu_cd: str = Field(
        description="EU water body code",
        min_length=5
    )
    start_year: Optional[int] = Field(
        default=None,
        description="Start year",
        ge=1900,
        le=2100
    )
    end_year: Optional[int] = Field(
        default=None,
        description="End year",
        ge=1900,
        le=2100
    )
    include_species_list: bool = Field(
        default=True,
        description="Include list of observed species"
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' or 'json'"
    )


# ============================================================================
# API CLIENT HELPERS
# ============================================================================

def _build_api_url(endpoint: str, params: Dict[str, Any] = None) -> str:
    """Build complete API URL with public ticket (API v2 uses 'token' parameter)."""
    url = f"{BASE_URL}/{endpoint}"
    if params:
        url += "?" + "&".join(f"{k}={v}" for k, v in params.items() if v is not None)

    # Add public ticket as 'token' parameter (API v2 format)
    separator = "&" if "?" in url else "?"
    url += f"{separator}token={PUBLIC_TICKET}"

    return url


async def _make_api_request(
    endpoint: str,
    params: Dict[str, Any] = None,
    method: str = "GET"
) -> Dict[str, Any]:
    """
    Make async API request to SLU Miljödata.
    
    Args:
        endpoint: API endpoint path
        params: Query parameters
        method: HTTP method
        
    Returns:
        Parsed JSON response
        
    Raises:
        httpx.HTTPError: On API errors
    """
    url = _build_api_url(endpoint, params)
    
    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
        try:
            logger.info(f"API Request: {method} {endpoint}")
            logger.info(f"Full URL: {url}")

            if method == "GET":
                response = await client.get(url)
            elif method == "POST":
                response = await client.post(url)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            logger.info(f"Response status: {response.status_code}")
            response.raise_for_status()
            
            # Parse JSON response
            data = response.json()
            logger.info(f"API Response: {len(str(data))} bytes")
            
            return data
            
        except httpx.HTTPStatusError as e:
            return _handle_http_error(e)
        except httpx.TimeoutException:
            return {"error": "Request timeout. API might be slow or unavailable."}
        except Exception as e:
            logger.error(f"API request failed: {e}")
            return {"error": f"Unexpected error: {type(e).__name__}: {str(e)}"}


def _handle_http_error(error: httpx.HTTPStatusError) -> Dict[str, Any]:
    """Format HTTP errors with actionable messages."""
    status = error.response.status_code

    error_messages = {
        302: f"Redirect detected. URL: {error.request.url}. Response redirects to: {error.response.headers.get('location', 'unknown')}",
        400: "Bad request. Check that all parameters are correctly formatted.",
        401: "Authentication failed. Access token might be invalid or expired.",
        403: "Access forbidden. You don't have permission to access this resource.",
        404: "Resource not found. Check that station ID or EU_CD code is correct.",
        429: "Rate limit exceeded. Please wait before making more requests.",
        500: "Server error. The API is experiencing issues.",
        503: "Service unavailable. The API is temporarily down for maintenance."
    }

    message = error_messages.get(status, f"HTTP {status} error occurred")

    return {
        "error": message,
        "status_code": status,
        "detail": str(error),
        "request_url": str(error.request.url)
    }


def _format_markdown_table(data: List[Dict[str, Any]], headers: List[str]) -> str:
    """Format data as markdown table."""
    if not data:
        return "*No data available*"
    
    # Build header
    table = "| " + " | ".join(headers) + " |\n"
    table += "| " + " | ".join(["---"] * len(headers)) + " |\n"
    
    # Build rows
    for row in data:
        values = [str(row.get(h, "—")) for h in headers]
        table += "| " + " | ".join(values) + " |\n"
    
    return table


def _calculate_statistics(values: List[float]) -> Dict[str, Any]:
    """Calculate basic statistics for a dataset."""
    if not values:
        return {"error": "No data available for statistics"}
    
    sorted_values = sorted(values)
    n = len(sorted_values)
    
    stats = {
        "count": n,
        "mean": sum(values) / n,
        "min": min(values),
        "max": max(values),
        "median": sorted_values[n // 2] if n % 2 != 0 else (sorted_values[n // 2 - 1] + sorted_values[n // 2]) / 2
    }
    
    # Calculate trend (simple linear regression slope)
    if n > 2:
        x_mean = (n - 1) / 2
        y_mean = stats["mean"]
        
        numerator = sum((i - x_mean) * (values[i] - y_mean) for i in range(n))
        denominator = sum((i - x_mean) ** 2 for i in range(n))
        
        if denominator != 0:
            stats["trend_slope"] = numerator / denominator
            stats["trend_direction"] = "increasing" if stats["trend_slope"] > 0 else "decreasing" if stats["trend_slope"] < 0 else "stable"
    
    return stats


# ============================================================================
# MCP TOOLS
# ============================================================================

@mcp.tool(
    name="slu_search_stations",
    annotations={
        "title": "Search Monitoring Stations",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def search_stations(params: SearchStationsInput) -> str:
    """
    Search for water monitoring stations in SLU's database.
    
    Find stations by name, EU_CD code, water body type, or region. Returns station
    metadata including coordinates, water body type, and monitoring program info.
    
    Args:
        params (SearchStationsInput): Search parameters containing:
            - station_name (Optional[str]): Partial station name (e.g., 'Vänern')
            - eu_cd (Optional[str]): EU water body code
            - water_body_type (Optional[str]): 'sjö', 'vattendrag', or 'kustvatten'
            - region (Optional[str]): Geographic region/county
            - limit (int): Max results (1-500, default 50)
            - response_format (str): 'markdown' or 'json'
    
    Returns:
        str: Formatted station list with metadata in requested format
        
    Example queries:
        - Find all stations in Vänern: station_name="Vänern"
        - Find lake stations: water_body_type="sjö"
        - Find stations by EU code: eu_cd="SE123456-123456"
    """
    try:
        # Build API request for v2
        endpoint = "observations-service/v2/stations/query"
        api_params = {}

        # Add filters to avoid large responses
        if params.station_name:
            api_params["study"] = params.station_name
        if params.region:
            api_params["county"] = params.region
        if params.water_body_type:
            # v2 might support this - test it
            api_params["waterBodyType"] = params.water_body_type.value

        # Make API request to v2 endpoint
        data = await _make_api_request(endpoint, api_params)

        if "error" in data:
            return f"**Error:** {data['error']}"

        # Get stations from v2 response
        # Note: isAuthorized flag doesn't affect data access - can be false and still get data
        stations = data.get("stations", []) if isinstance(data, dict) else []
        num_stations = data.get("numberOfStations", len(stations)) if isinstance(data, dict) else len(stations)
        
        if params.response_format == ResponseFormat.JSON:
            return json.dumps(data, indent=2, ensure_ascii=False)
        
        # Format as Markdown
        if not stations:
            return f"**No stations found matching your criteria.**\n\n**Search parameters:**\n- Station name: {params.station_name or 'N/A'}\n- Region: {params.region or 'N/A'}\n- EU_CD: {params.eu_cd or 'N/A'}\n\n**Tips:**\n- Try using `region='Uppsala'` or `region='Stockholm'`\n- Use partial station names: `station_name='Mälaren'`"

        output = f"# Monitoring Stations (SLU MVM API v2)\n\n**Found {num_stations} stations** (showing first {min(params.limit, len(stations))})\n\n"

        for station in stations[:params.limit]:
            name = station.get('stationName', station.get('preferredName', 'Unknown'))
            station_id = station.get('stationId', station.get('nationalStationId', '—'))
            output += f"## {name}\n"
            output += f"- **Station ID:** {station_id}\n"
            output += f"- **National ID:** {station.get('nationalStationId', '—')}\n"
            output += f"- **EU ID:** {station.get('euId', station.get('sampleSiteEUId', '—'))}\n"
            output += f"- **Type:** {station.get('stationType', '—')}\n"
            output += f"- **County:** {station.get('county', '—')}\n"
            output += f"- **Municipality:** {station.get('municipality', '—')}\n"

            # Coordinates
            coord_x = station.get('stationCoordinateE', station.get('sampleSiteCoordinateE'))
            coord_y = station.get('stationCoordinateN', station.get('sampleSiteCoordinateN'))
            coord_sys = station.get('coordinateSystem', station.get('sampleSiteCoordinateSystem', 'Unknown'))

            if coord_x and coord_y:
                output += f"- **Coordinates:** E: {coord_x}, N: {coord_y} ({coord_sys})\n"

            output += "\n"

        if num_stations > params.limit:
            output += f"*...and {num_stations - params.limit} more stations. Increase `limit` parameter to see more.*\n"

        return output
        
    except Exception as e:
        logger.error(f"search_stations failed: {e}")
        return f"**Error:** Failed to search stations: {type(e).__name__}: {str(e)}"


@mcp.tool(
    name="slu_get_station_details",
    annotations={
        "title": "Get Station Details",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def get_station_details(params: GetStationDetailsInput) -> str:
    """
    Get detailed information about a specific monitoring station.
    
    Retrieves comprehensive station metadata including coordinates, water body
    classification, monitoring program participation, and available data types.
    
    Args:
        params (GetStationDetailsInput): Parameters containing:
            - station_id (str): Station ID or EU_CD code
            - include_coordinates (bool): Include coordinate info (default True)
            - response_format (str): 'markdown' or 'json'
    
    Returns:
        str: Detailed station information including:
            - Station metadata (name, ID, EU_CD)
            - Coordinates and coordinate system
            - Water body classification
            - Available data types and parameters
            - Monitoring period and frequency
    """
    try:
        api_params = {
            "stationId": params.station_id,
            "includeCoordinates": params.include_coordinates
        }
        
        data = await _make_api_request("GetStationDetails", api_params)
        
        if "error" in data:
            return f"**Error:** {data['error']}"
        
        if params.response_format == ResponseFormat.JSON:
            return json.dumps(data, indent=2, ensure_ascii=False)
        
        # Format as Markdown
        station = data.get("station", {})
        
        output = f"# Station: {station.get('name', 'Unknown')}\n\n"
        output += "## Basic Information\n"
        output += f"- **Station ID:** {station.get('id', '—')}\n"
        output += f"- **EU_CD:** {station.get('eu_cd', '—')}\n"
        output += f"- **Water Body Type:** {station.get('water_body_type', '—')}\n"
        output += f"- **Region:** {station.get('region', '—')}\n"
        output += f"- **County:** {station.get('county', '—')}\n\n"
        
        if params.include_coordinates and station.get('coordinates'):
            coords = station['coordinates']
            output += "## Coordinates\n"
            output += f"- **Latitude:** {coords.get('lat', '—')}\n"
            output += f"- **Longitude:** {coords.get('lon', '—')}\n"
            output += f"- **System:** {coords.get('system', 'WGS84')}\n"
            output += f"- **EPSG:** {coords.get('epsg', '—')}\n\n"
        
        if station.get('available_data'):
            output += "## Available Data Types\n"
            for data_type in station['available_data']:
                output += f"- {data_type}\n"
            output += "\n"
        
        if station.get('monitoring_period'):
            period = station['monitoring_period']
            output += "## Monitoring Period\n"
            output += f"- **Start:** {period.get('start', '—')}\n"
            output += f"- **End:** {period.get('end', 'Ongoing')}\n\n"
        
        return output
        
    except Exception as e:
        logger.error(f"get_station_details failed: {e}")
        return f"**Error:** Failed to get station details: {type(e).__name__}: {str(e)}"


@mcp.tool(
    name="slu_get_water_chemistry",
    annotations={
        "title": "Get Water Chemistry Data",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def get_water_chemistry(params: GetWaterChemistryInput) -> str:
    """
    Retrieve water chemistry data for a specific water body.
    
    Get time series data for chemical parameters like nutrients (phosphorus, nitrogen),
    pH, oxygen, metals, and organic substances. Optionally calculates statistics and trends.
    
    Args:
        params (GetWaterChemistryInput): Parameters containing:
            - eu_cd (str): EU water body code
            - parameters (Optional[List[str]]): Specific parameters or None for all
            - start_year (Optional[int]): Start year for time series
            - end_year (Optional[int]): End year for time series
            - calculate_statistics (bool): Calculate mean, trend, etc. (default True)
            - response_format (str): 'markdown' or 'json'
    
    Returns:
        str: Water chemistry data with:
            - Time series of measurements
            - Statistics (if requested): mean, min, max, median, trend
            - Data quality indicators
            - Sampling information
            
    Common parameters:
        - totalfosfor (total phosphorus)
        - totalkväve (total nitrogen)
        - pH
        - siktdjup (Secchi depth)
        - klorofyll (chlorophyll-a)
    """
    try:
        api_params = {
            "euCode": params.eu_cd,
            "dataType": "vattenkemi"
        }
        
        if params.parameters:
            api_params["parameters"] = ",".join(params.parameters)
        if params.start_year:
            api_params["startYear"] = params.start_year
        if params.end_year:
            api_params["endYear"] = params.end_year
        
        data = await _make_api_request("GetObservations", api_params)
        
        if "error" in data:
            return f"**Error:** {data['error']}"
        
        if params.response_format == ResponseFormat.JSON:
            return json.dumps(data, indent=2, ensure_ascii=False)
        
        # Format as Markdown
        observations = data.get("observations", [])
        
        if not observations:
            return f"**No water chemistry data found for EU_CD: {params.eu_cd}**\n\nCheck that:\n- The EU_CD code is correct\n- Data exists for the specified time period\n- The station monitors water chemistry"
        
        output = f"# Water Chemistry Data\n**EU_CD:** {params.eu_cd}\n\n"
        
        # Group by parameter
        by_parameter = {}
        for obs in observations:
            param = obs.get('parameter', 'Unknown')
            if param not in by_parameter:
                by_parameter[param] = []
            by_parameter[param].append(obs)
        
        # Display each parameter
        for param_name, param_data in by_parameter.items():
            output += f"## {param_name}\n"
            output += f"**Observations:** {len(param_data)}\n\n"
            
            # Calculate statistics if requested
            if params.calculate_statistics:
                values = [float(obs['value']) for obs in param_data if obs.get('value') is not None]
                if values:
                    stats = _calculate_statistics(values)
                    output += "### Statistics\n"
                    output += f"- **Count:** {stats['count']}\n"
                    output += f"- **Mean:** {stats['mean']:.2f}\n"
                    output += f"- **Median:** {stats['median']:.2f}\n"
                    output += f"- **Min:** {stats['min']:.2f}\n"
                    output += f"- **Max:** {stats['max']:.2f}\n"
                    if 'trend_direction' in stats:
                        output += f"- **Trend:** {stats['trend_direction']}\n"
                    output += "\n"
            
            # Show recent measurements
            output += "### Recent Measurements\n"
            recent = sorted(param_data, key=lambda x: x.get('date', ''), reverse=True)[:10]
            
            for obs in recent:
                date_str = obs.get('date', '—')
                value = obs.get('value', '—')
                unit = obs.get('unit', '')
                output += f"- **{date_str}:** {value} {unit}\n"
            
            output += "\n"
        
        return output
        
    except Exception as e:
        logger.error(f"get_water_chemistry failed: {e}")
        return f"**Error:** Failed to get water chemistry data: {type(e).__name__}: {str(e)}"


@mcp.tool(
    name="slu_get_macrophytes",
    annotations={
        "title": "Get Macrophyte Data",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def get_macrophytes(params: GetMacrophytesInput) -> str:
    """
    Retrieve macrophyte (aquatic plant) survey data.
    
    Get information about aquatic vegetation including species composition, coverage,
    depth distribution, and ecological quality indices for lakes and streams.
    
    Args:
        params (GetMacrophytesInput): Parameters containing:
            - eu_cd (str): EU water body code
            - start_year (Optional[int]): Start year
            - end_year (Optional[int]): End year
            - include_species_list (bool): Include species list (default True)
            - response_format (str): 'markdown' or 'json'
    
    Returns:
        str: Macrophyte data including:
            - Survey dates and methods
            - Species list with abundance
            - Ecological quality indices (if calculated)
            - Depth distribution
            - Coverage percentages
            
    Ecological indices may include:
        - IPS (Index of Plant Species)
        - TIc (Trophy Index)
        - Diversity measures
    """
    try:
        api_params = {
            "euCode": params.eu_cd,
            "dataType": "makrofyter"
        }
        
        if params.start_year:
            api_params["startYear"] = params.start_year
        if params.end_year:
            api_params["endYear"] = params.end_year
        
        data = await _make_api_request("GetObservations", api_params)
        
        if "error" in data:
            return f"**Error:** {data['error']}"
        
        if params.response_format == ResponseFormat.JSON:
            return json.dumps(data, indent=2, ensure_ascii=False)
        
        # Format as Markdown
        surveys = data.get("surveys", [])
        
        if not surveys:
            return f"**No macrophyte data found for EU_CD: {params.eu_cd}**\n\nThis water body may not have macrophyte surveys in the specified time period."
        
        output = f"# Macrophyte Data\n**EU_CD:** {params.eu_cd}\n\n"
        output += f"**Total Surveys:** {len(surveys)}\n\n"
        
        for survey in surveys:
            survey_date = survey.get('date', '—')
            output += f"## Survey: {survey_date}\n"
            output += f"- **Method:** {survey.get('method', '—')}\n"
            output += f"- **Surveyor:** {survey.get('surveyor', '—')}\n\n"
            
            # Ecological indices
            if survey.get('indices'):
                indices = survey['indices']
                output += "### Ecological Indices\n"
                for index_name, index_value in indices.items():
                    output += f"- **{index_name}:** {index_value}\n"
                output += "\n"
            
            # Species list
            if params.include_species_list and survey.get('species'):
                output += "### Observed Species\n"
                species_list = survey['species']
                
                for species in species_list:
                    name = species.get('name', 'Unknown')
                    abundance = species.get('abundance', '—')
                    coverage = species.get('coverage_percent', '')
                    
                    output += f"- **{name}**"
                    if abundance != '—':
                        output += f" - Abundance: {abundance}"
                    if coverage:
                        output += f" - Coverage: {coverage}%"
                    output += "\n"
                
                output += "\n"
        
        return output
        
    except Exception as e:
        logger.error(f"get_macrophytes failed: {e}")
        return f"**Error:** Failed to get macrophyte data: {type(e).__name__}: {str(e)}"


@mcp.tool(
    name="slu_search_parameters",
    annotations={
        "title": "Search Available Parameters",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def search_parameters(params: SearchParametersInput) -> str:
    """
    Search for available measurement parameters in the database.
    
    Find chemical, physical, and biological parameters that can be queried. Useful
    for discovering what data is available before requesting observations.
    
    Args:
        params (SearchParametersInput): Parameters containing:
            - query (Optional[str]): Search term (e.g., 'fosfor', 'kväve')
            - data_type (Optional[str]): Filter by data type
            - limit (int): Max results (1-200, default 50)
            - response_format (str): 'markdown' or 'json'
    
    Returns:
        str: List of parameters with:
            - Parameter name (Swedish and English)
            - Unit of measurement
            - Data type category
            - Description
            - Typical value ranges
            
    Common parameter categories:
        - Nutrients: fosfor (phosphorus), kväve (nitrogen)
        - Physical: pH, temperatur, siktdjup (Secchi depth)
        - Oxygen: syre (oxygen), syremättnad (oxygen saturation)
        - Biology: klorofyll (chlorophyll), makrofyter (macrophytes)
    """
    try:
        api_params = {
            "limit": params.limit
        }
        
        if params.query:
            api_params["search"] = params.query
        if params.data_type:
            api_params["dataType"] = params.data_type.value
        
        data = await _make_api_request("GetParameters", api_params)
        
        if "error" in data:
            return f"**Error:** {data['error']}"
        
        if params.response_format == ResponseFormat.JSON:
            return json.dumps(data, indent=2, ensure_ascii=False)
        
        # Format as Markdown
        parameters = data.get("parameters", [])
        
        if not parameters:
            return "**No parameters found matching your search.**\n\nTry:\n- Broader search terms\n- Different data type\n- Swedish parameter names (e.g., 'fosfor' not 'phosphorus')"
        
        output = f"# Available Parameters\n\n**Found {len(parameters)} parameters**\n\n"
        
        for param in parameters:
            output += f"## {param.get('name', 'Unknown')}\n"
            
            if param.get('name_english'):
                output += f"**English:** {param['name_english']}\n\n"
            
            output += f"- **Parameter ID:** {param.get('id', '—')}\n"
            output += f"- **Unit:** {param.get('unit', '—')}\n"
            output += f"- **Data Type:** {param.get('data_type', '—')}\n"
            
            if param.get('description'):
                output += f"- **Description:** {param['description']}\n"
            
            if param.get('typical_range'):
                range_info = param['typical_range']
                output += f"- **Typical Range:** {range_info.get('min', '—')} - {range_info.get('max', '—')} {param.get('unit', '')}\n"
            
            output += "\n"
        
        return output
        
    except Exception as e:
        logger.error(f"search_parameters failed: {e}")
        return f"**Error:** Failed to search parameters: {type(e).__name__}: {str(e)}"


@mcp.tool(
    name="slu_get_observations",
    annotations={
        "title": "Get Environmental Observations",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def get_observations(params: GetObservationsInput) -> str:
    """
    Retrieve environmental observations with flexible filtering.
    
    General-purpose tool for retrieving any type of environmental data with support
    for multiple filtering options including station, parameter, and time period.
    
    Args:
        params (GetObservationsInput): Parameters containing:
            - station_id (Optional[str]): Station ID
            - eu_cd (Optional[str]): EU water body code
            - data_type (str): Data type (vattenkemi, makrofyter, etc.)
            - parameter (Optional[str]): Specific parameter name
            - start_date (Optional[date]): Start date (YYYY-MM-DD)
            - end_date (Optional[date]): End date (YYYY-MM-DD)
            - limit (int): Max observations (1-1000, default 100)
            - response_format (str): 'markdown' or 'json'
    
    Returns:
        str: Observations data with:
            - Measurement values and dates
            - Station information
            - Data quality flags
            - Sampling metadata
            
    Use specialized tools for better formatted output:
        - slu_get_water_chemistry: For chemistry with statistics
        - slu_get_macrophytes: For plant surveys with species lists
    """
    try:
        if not params.station_id and not params.eu_cd:
            return "**Error:** Either station_id or eu_cd must be provided."
        
        api_params = {
            "dataType": params.data_type.value,
            "limit": params.limit
        }
        
        if params.station_id:
            api_params["stationId"] = params.station_id
        if params.eu_cd:
            api_params["euCode"] = params.eu_cd
        if params.parameter:
            api_params["parameter"] = params.parameter
        if params.start_date:
            api_params["startDate"] = params.start_date.isoformat()
        if params.end_date:
            api_params["endDate"] = params.end_date.isoformat()
        
        data = await _make_api_request("GetObservations", api_params)
        
        if "error" in data:
            return f"**Error:** {data['error']}"
        
        if params.response_format == ResponseFormat.JSON:
            return json.dumps(data, indent=2, ensure_ascii=False)
        
        # Format as Markdown
        observations = data.get("observations", [])
        
        if not observations:
            return "**No observations found.**\n\nCheck that:\n- Station ID or EU_CD is correct\n- Data type is available for this station\n- Time period contains data"
        
        output = f"# Environmental Observations\n"
        output += f"**Data Type:** {params.data_type.value}\n"
        output += f"**Total Observations:** {len(observations)}\n\n"
        
        # Group by parameter if multiple
        by_param = {}
        for obs in observations:
            param = obs.get('parameter', 'Unknown')
            if param not in by_param:
                by_param[param] = []
            by_param[param].append(obs)
        
        for param_name, param_obs in by_param.items():
            output += f"## {param_name}\n"
            output += f"**Count:** {len(param_obs)}\n\n"
            
            # Show observations
            for obs in param_obs[:params.limit]:
                date_str = obs.get('date', '—')
                value = obs.get('value', '—')
                unit = obs.get('unit', '')
                
                output += f"- **{date_str}:** {value} {unit}"
                
                if obs.get('quality_flag'):
                    output += f" [{obs['quality_flag']}]"
                
                output += "\n"
            
            if len(param_obs) > params.limit:
                output += f"\n*...and {len(param_obs) - params.limit} more observations*\n"
            
            output += "\n"
        
        return output
        
    except Exception as e:
        logger.error(f"get_observations failed: {e}")
        return f"**Error:** Failed to get observations: {type(e).__name__}: {str(e)}"


# ============================================================================
# SERVER ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    """Run the MCP server with stdio transport."""
    mcp.run()
