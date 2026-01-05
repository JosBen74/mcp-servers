# SLU Miljödata MCP - Användningsguide

**Uppdaterad:** 2025-12-14
**Status:** ✓ Verifierad fungerande

---

## VIKTIGT: Korrekta parametrar

### ❌ Funkar INTE:
```python
slu_search_stations(
    station_name="Mjörn",
    region="Västra Götaland"  # ❌ Använder 'county' som inte ger resultat
)
```

### ✅ Funkar:
```python
# Använd direkt API-anrop med municipality
import httpx

url = "https://miljodata.slu.se/api/observations-service/v2/stations/query"
params = {
    "token": "PUJD93023KAS943HD",
    "municipality": "Lerum"  # ✅ DETTA FUNGERAR!
}

response = httpx.get(url, params=params)
stations = response.json()["stations"]
```

---

## Verifierade arbetssätt

### 1. Hitta stationer för Mjörn

**Metod A: Direkt API (rekommenderad)**

```python
import httpx
import asyncio

async def hitta_mjorn_stationer():
    url = "https://miljodata.slu.se/api/observations-service/v2/stations/query"
    params = {
        "token": "PUJD93023KAS943HD",
        "municipality": "Alingsås"  # Eller "Lerum"
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.get(url, params=params)
        data = response.json()

        # Filtrera för Mjörn
        mjorn_stations = [
            s for s in data["stations"]
            if "Mjörn" in s["stationName"]
        ]

        return mjorn_stations

# Resultat:
# Station ID: 6121
# Namn: Mjörn
# EU_CD: SE642849-129932
# Kommun: Alingsås
```

### 2. Hämta vattenkemi för Mjörn

**VIKTIGT: Använd `/full-samples/query` endpoint**

```python
async def hamta_vattenkemi():
    url = "https://miljodata.slu.se/api/observations-service/v2/full-samples/query"
    params = {
        "token": "PUJD93023KAS943HD",
        "stationIds": "6121",  # Station-ID för Mjörn
        "fromYear": "2018",    # MÅSTE ha tidsfilter!
        "toYear": "2024"
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.get(url, params=params)
        data = response.json()

        # Extrahera data
        for sample in data.get("samples", []):
            print(f"Datum: {sample['samplingDate']}")

            for obs in sample.get("observations", []):
                param = obs["propertyName"]

                for val in obs.get("observationValues", []):
                    print(f"  {param}: {val['value']} {val['unit']}")

        return data
```

---

## Datastruktur

### Stationer (från `/stations/query`)

```json
{
  "numberOfStations": 5,
  "stations": [
    {
      "stationId": 6121,
      "stationName": "Mjörn",
      "euId": "SE642849-129932",
      "municipality": "Alingsås",
      "county": "14",
      "stationType": "Sjö",
      "stationCoordinateE": 362849,
      "stationCoordinateN": 6429932,
      "coordinateSystem": "SWEREF99TM"
    }
  ]
}
```

### Vattenkemi (från `/full-samples/query`)

```json
{
  "samples": [
    {
      "sampleId": 928188,
      "samplingDate": "2020-08-10",
      "stationName": "Mjörn",
      "minDepth": 0.5,
      "maxDepth": 0.5,
      "observations": [
        {
          "propertyName": "Totalfosfor",
          "propertyAbbrevName": "Tot-P",
          "observationValues": [
            {
              "value": "11,000",  // OBS: Komma som decimaltecken!
              "unit": "ug/l P"
            }
          ]
        }
      ]
    }
  ]
}
```

---

## MCP-verktyg (planerade uppdateringar)

### Nuvarande begränsningar i slu_miljodata_mcp.py:

1. `slu_search_stations` använder `county` parameter som inte fungerar
2. Saknar `municipality` parameter
3. Bör använda `/full-samples/query` för vattenkemi

### Rekommenderad lösning tills MCP uppdateras:

Använd direkt API-anrop enligt exemplen ovan.

---

## Exempel: Komplett statusklassning för Mjörn

Se filen: `C:\Users\josef\slu_mjorn_solution.py`

Denna fil innehåller:
- ✓ Fungerande stationssökning med `municipality`
- ✓ Vattenkemihämtning med `/full-samples/query`
- ✓ Databearbetning och statistik
- ✓ Export till JSON

---

## Troubleshooting

### Problem: Inga stationer hittas

**Lösning:**
```python
# ❌ Fungerar INTE
params = {"county": "Västra Götaland"}

# ✅ Fungerar
params = {"municipality": "Lerum"}  # eller "Alingsås"
```

### Problem: Timeout vid datahämtning

**Lösning:** Inkludera alltid `fromYear` och `toYear`

```python
# ❌ Orsakar timeout
params = {"stationIds": "6121"}

# ✅ Fungerar
params = {
    "stationIds": "6121",
    "fromYear": "2020",
    "toYear": "2024"
}
```

### Problem: Kan inte läsa värden

**Lösning:** Värden är strängar med komma som decimaltecken

```python
def parse_value(value_str):
    """Konvertera SLU-värde till float"""
    if isinstance(value_str, str):
        value_str = value_str.replace(',', '.')
    return float(value_str)

# Användning
varde = parse_value(val["value"])  # "11,000" -> 11.0
```

---

## Verifierade resultat för Mjörn

**Hämtad data (2018-2024):**
- 957 mätningar från 22 provtillfällen
- 156 olika parametrar
- Station-ID: 6121
- EU_CD: SE642849-129932

**Nyckelvärden:**
- Totalfosfor: 11.1 µg/l (6.9-26.0)
- Totalkväve: 728 µg/l (560-850)
- pH: 7.4 (7.0-7.9)
- Siktdjup: 3.2 m (2.0-4.5)
- Klorofyll a: 6.4 µg/l (3.9-10.0)

---

## Relaterade filer

- `SLU_API_SOLUTION.md` - Teknisk dokumentation av API-lösningen
- `SLU_API_GUIDE.md` - Praktisk guide för API-användning
- `slu_mjorn_solution.py` - Fungerande Python-implementation
- `mjorn_vattenkemi_data.json` - Exporterad data

---

**Skapad:** 2025-12-14
**Verifierad:** ✓ Fungerar i produktion
**Baserad på:** Framgångsrik datahämtning med Opus 4.5
