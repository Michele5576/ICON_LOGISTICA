# SCHEMA REALE DEI DATASET
*Generato da `src/parsing/ispeziona_dataset.py`*

## 1. File Excel

### Foglio: `1_Flotta_Veicoli`

- **Righe dati**: 5
- **Colonne**: 8

| # | Colonna | Validi | Missing | Tipi | Val. Unici | Esempi |
|---|---------|--------|---------|------|------------|--------|
| 1 | `ID_Veicolo` | 5 | 0 | str | 5 | V-SPR-01, V-SPR-02, V-SPR-03 |
| 2 | `Marca` | 5 | 0 | str | 1 | Mercedes-Benz, Mercedes-Benz, Mercedes-Benz |
| 3 | `Modello` | 5 | 0 | str | 2 | Sprinter, Sprinter, Sprinter |
| 4 | `Anno_Immatricolazione` | 5 | 0 | int | 2 | 2021, 2021, 2021 |
| 5 | `Alimentazione` | 5 | 0 | str | 1 | Diesel, Diesel, Diesel |
| 6 | `Cella_Frigo` | 5 | 0 | str | 2 | SI, SI, SI |
| 7 | `Capacita_Carico_kg` | 5 | 0 | int | 2 | 1500, 1500, 1500 |
| 8 | `Volume_Carico_m3` | 5 | 0 | int, float | 2 | 14, 14, 14 |

### Foglio: `2_Anagrafica_Clienti`

- **Righe dati**: 100
- **Colonne**: 8

| # | Colonna | Validi | Missing | Tipi | Val. Unici | Esempi |
|---|---------|--------|---------|------|------------|--------|
| 1 | `Codice_Cliente` | 100 | 0 | str | 100 | 983810, 996530, 928657 |
| 2 | `Ragione_Sociale` | 100 | 0 | str | 100 | Cliente Azienda 001 SRL, Cliente Azienda 002 SRL, Cliente Azienda 003 SRL |
| 3 | `Indirizzo` | 100 | 0 | str | 97 | Via Roma, 190, Via Vittorio Emanuele, 23, Via Vittorio Emanuele, 155 |
| 4 | `Citta` | 100 | 0 | str | 7 | Bari, Bari, Lecce |
| 5 | `Provincia` | 100 | 0 | str | 6 | BA, BA, LE |
| 6 | `CAP` | 100 | 0 | str | 9 | 70123, 70123, 73100 |
| 7 | `Macrozona` | 100 | 0 | str | 9 | Bari Nord, Bari Nord, Lecce Nord (Versante Adriatico) |
| 8 | `Orario_Consegna_Richiesto` | 100 | 0 | str | 24 | 12:00 - 14:00, 14:00 - 16:00, 08:00 - 12:00 |

### Foglio: `3_Tragitti_Mensili_Storico`

- **Righe dati**: 1393
- **Colonne**: 11

| # | Colonna | Validi | Missing | Tipi | Val. Unici | Esempi |
|---|---------|--------|---------|------|------------|--------|
| 1 | `Data` | 1393 | 0 | str | 26 | 2026-06-01, 2026-06-01, 2026-06-01 |
| 2 | `ID_Veicolo` | 1393 | 0 | str | 5 | V-SPR-01, V-SPR-01, V-SPR-01 |
| 3 | `Codice_Cliente` | 1393 | 0 | str | 100 | 939240, 924356, 983810 |
| 4 | `Macrozona` | 1393 | 0 | str | 9 | Bari Nord, Bari Nord, Bari Nord |
| 5 | `Sequenza_Visita` | 1393 | 0 | int | 15 | 1, 2, 3 |
| 6 | `Distanza_Stimata_km` | 1393 | 0 | float | 244 | 22.5, 11.6, 10.1 |
| 7 | `Ora_Arrivo_Effettiva` | 1393 | 0 | str | 522 | 08:33, 09:13, 09:34 |
| 8 | `Tempo_Scarico_Previsto_min` | 1393 | 0 | int | 1 | 10, 10, 10 |
| 9 | `Tempo_Scarico_Effettivo_min` | 1393 | 0 | int | 42 | 23, 10, 10 |
| 10 | `Esito_Consegna` | 1393 | 0 | str | 2 | Completata, Completata, Completata |
| 11 | `Note_Autista` | 84 | 1309 | str | 1 | Cliente Assente/Chiuso, Cliente Assente/Chiuso, Cliente Assente/Chiuso |

## 2. File XML (Grafo Stradale)

- **Dimensione**: 8.11 MB
- **Tag root**: `osm`
- **Nodi**: 57242
- **Way**: 13054
- **Relazioni**: 0

### Bounding Box Geografico

| | Min | Max |
|---|-----|-----|
| Latitudine | 41.061973 | 41.160169 |
| Longitudine | 16.773157 | 16.946248 |

### Tipi di Strada (`highway` tag)

| Tipo | Conteggio |
|------|-----------|
| `footway` | 4183 |
| `service` | 2908 |
| `residential` | 1682 |
| `unclassified` | 1137 |
| `secondary` | 609 |
| `tertiary` | 574 |
| `pedestrian` | 393 |
| `track` | 285 |
| `cycleway` | 240 |
| `trunk_link` | 200 |
| `steps` | 195 |
| `trunk` | 127 |
| `secondary_link` | 109 |
| `path` | 98 |
| `primary` | 92 |
| `primary_link` | 45 |
| `motorway_link` | 36 |
| `motorway` | 32 |
| `construction` | 31 |
| `tertiary_link` | 24 |
| `living_street` | 20 |
| `bus_guideway` | 11 |
| `bridleway` | 7 |
| `emergency_bay` | 5 |
| `elevator` | 4 |
| `services` | 3 |
| `rest_area` | 1 |
| `corridor` | 1 |
| `raceway` | 1 |
| `planned` | 1 |

### Struttura XML (primi livelli)

#### Tag `<note>` — 1 occorrenze

#### Tag `<meta>` — 1 occorrenze

Attributi esempio: `{'osm_base': '2026-07-20T10:09:44Z'}`

#### Tag `<node>` — 57242 occorrenze

Attributi esempio: `{'id': '15502799', 'lat': '41.0915453', 'lon': '16.8941294'}`

#### Tag `<way>` — 13054 occorrenze

Attributi esempio: `{'id': '14347427'}`

Sotto-tag esempio:
- `<nd>` attrib=`{'ref': '139160792'}`
- `<nd>` attrib=`{'ref': '139160793'}`
- `<nd>` attrib=`{'ref': '11347448100'}`
- `<nd>` attrib=`{'ref': '139160794'}`
- `<nd>` attrib=`{'ref': '11347448101'}`

