# SHARK MCP Server

MCP-server för SHARK kustvattendata från SMHI. Integrerar med Claude Desktop för automatiserad statusklassning av kustvattenförekomster.

## Funktioner

- ✓ Sök efter SHARK dataset (PhysicalChemical, Phytoplankton, Zoobenthos)
- ✓ Hämta vattenkemidata för statusklassning
- ✓ Filtrera på område, år och parametrar
- ✓ Aggregerad datahämtning för förvaltningscykler
- ✓ Både JSON och läsbara format

## Installation

```bash
cd shark-mcp
uv pip install -e .
```

## Konfiguration (Claude Desktop)

```json
{
  "mcpServers": {
    "shark": {
      "command": "uv",
      "args": ["--directory", "/path/to/shark-mcp", "run", "shark-mcp"]
    }
  }
}
```

## Användning

Se INSTALLATION_GUIDE.md för fullständig dokumentation.

## Verktyg (Tools)

1. `search_datasets` - Sök efter dataset
2. `get_dataset_metadata` - Hämta metadata
3. `get_dataset_data` - Hämta data
4. `get_coastal_chemistry` - Aggregerad vattenkemi
5. `list_available_areas` - Lista områden

## Support

- E-post: josef@lansstyrelsen.se
- SHARK dokumentation: https://shark.smhi.se/
