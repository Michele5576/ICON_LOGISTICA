"""
Configurazione centralizzata del progetto.
Tutti i path e le costanti globali sono qui - nessun altro file
deve avere path hardcoded.
"""

import os
from pathlib import Path

# === PATH ===
ROOT = Path(__file__).resolve().parent.parent  # PROGETTO/
DATASET_DIR = ROOT / "dataset"
KB_DIR = ROOT / "kb"
MODELS_DIR = ROOT / "models"
OUTPUT_DIR = ROOT / "output"
SRC_DIR = ROOT / "src"

# === SWI-PROLOG PORTABILE ===
SWIPL_DIR = Path("C:/Users/baron/UNIVERSITA/ICON/file progetto supplementari/swipl")

def setup_swipl_env() -> None:
    """Configura le variabili d'ambiente per SWI-Prolog portabile."""
    os.environ["SWI_HOME_DIR"] = str(SWIPL_DIR)
    os.environ["Path"] = str(SWIPL_DIR / "bin") + ";" + os.environ.get("Path", "")

# File dataset reali (da SCHEMA_REALE.md)
EXCEL_PATH = DATASET_DIR / "Dataset_Logistica_VRP_MachineLearning.xlsx"
XML_PATH = DATASET_DIR / "bari_osm.xml"

# File generati
GRAFO_PL = KB_DIR / "grafo.pl"
FLOTTA_PL = KB_DIR / "flotta.pl"
CLIENTI_PL = KB_DIR / "clienti.pl"
KB_PL = KB_DIR / "knowledge_base.pl"
GRAFO_PICKLE = KB_DIR / "grafo_python.pkl"
GEOCODING_CACHE = DATASET_DIR / "clienti_geocoded.json"

# === NOMI FOGLI EXCEL (da SCHEMA_REALE.md) ===
FOGLIO_FLOTTA = "1_Flotta_Veicoli"
FOGLIO_CLIENTI = "2_Anagrafica_Clienti"
FOGLIO_STORICO = "3_Tragitti_Mensili_Storico"

# === VELOCITA' PLAUSIBILI PER TIPO STRADA (km/h) — urbano Bari ===
VELOCITA_KMH = {
    "motorway": 90,
    "motorway_link": 60,
    "trunk": 70,
    "trunk_link": 50,
    "primary": 50,
    "primary_link": 40,
    "secondary": 45,
    "secondary_link": 35,
    "tertiary": 40,
    "tertiary_link": 30,
    "residential": 30,
    "living_street": 20,
    "unclassified": 30,
    "service": 20,
    "default": 35,
}

# Velocita' massima assoluta (per euristica ammissibile A*)
V_MAX_KMH = 90.0

# === BOUNDING BOX ZTL CENTRO STORICO BARI ===
# Calibrato sul bbox reale del grafo: lat [41.062, 41.160], lon [16.773, 16.946]
# Centro storico di Bari (Bari Vecchia): rettangolo ragionevole
ZTL_LAT_MIN = 41.115
ZTL_LAT_MAX = 41.132
ZTL_LON_MIN = 16.865
ZTL_LON_MAX = 16.882

# Finestra oraria ZTL (ore, minuti inizio — ore, minuti fine)
ZTL_ORARIO = (7, 30, 20, 0)

# === TIPO STRADE DA INCLUDERE NEL GRAFO ===
# Escludiamo strade pedonali, ciclabili, sentieri, ecc. — non percorribili da furgoni
HIGHWAY_PERCORRIBILI = {
    "motorway", "motorway_link",
    "trunk", "trunk_link",
    "primary", "primary_link",
    "secondary", "secondary_link",
    "tertiary", "tertiary_link",
    "residential", "living_street",
    "unclassified", "service",
}

# === DEPOSITO (nodo di partenza dei furgoni) ===
# Zona industriale Bari — approssimazione centro geografico area sud-ovest
# Verra' agganciato al nodo piu' vicino del grafo in fase di geocoding
DEPOSITO_LAT = 41.092
DEPOSITO_LON = 16.850

# === COSTANTI ML ===
RANDOM_STATE = 42

# === COSTANTI CSP ===
PENALITA_PROFILO = {"puntuale": 0, "lieve_ritardo": 5, "recidivo": 15}
CSP_TIMEOUT_SECONDS = 30
MAX_CLIENTI_PER_VEICOLO = 25  # 100 clienti / 5 veicoli = 20 medi, margine 25
PESO_MEDIO_CLIENTE_KG = 50  # stima media peso consegna per cliente
