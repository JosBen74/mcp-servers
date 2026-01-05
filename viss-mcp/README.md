# VISS MCP Server

MCP-server för VISS (Vatteninformationssystem Sverige). Automatisk hämtning av miljökvalitetsnormer (MKN), statusklassning och åtgärder.

## Funktioner

- ✓ Sök vattenförekomster i VISS
- ✓ Hämta miljökvalitetsnormer (MKN) automatiskt
- ✓ Kontrollera MKN-compliance
- ✓ Hämta statusklassning per förvaltningscykel
- ✓ Hämta åtgärder och åtgärdsprogram
- ✓ Både JSON och läsbara format

## Installation

```bash
cd viss-mcp
uv pip install -e .
```

## Konfiguration (Claude Desktop)

```json
{
  "mcpServers": {
    "viss": {
      "command": "uv",
      "args": ["--directory", "/path/to/viss-mcp", "run", "viss-mcp"]
    }
  }
}
```

## Användning

Se INSTALLATION_GUIDE.md för fullständig dokumentation.

## Verktyg (Tools)

1. `search_waterbody` - Sök vattenförekomster
2. `get_environmental_quality_standard` - Hämta MKN
3. `get_status_classification` - Hämta statusklassning
4. `check_mkn_compliance` - Kontrollera compliance
5. `get_measures` - Hämta åtgärder

## Support

- E-post: josef@lansstyrelsen.se
- VISS support: viss@lansstyrelsen.se
- Dokumentation: https://visshjalp.lansstyrelsen.se/
