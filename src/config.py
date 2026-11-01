"""
Configurazione centralizzata del progetto.
Tutti i path e le costanti globali sono qui - nessun altro file
deve avere path hardcoded.
"""

import os
import shutil
from pathlib import Path

# === PATH ===
ROOT = Path(__file__).resolve().parent.parent
DATASET_DIR = ROOT / "dataset"
KB_DIR = ROOT / "kb"
MODELS_DIR = ROOT / "models"
OUTPUT_DIR = ROOT / "output"

# === SWI-PROLOG ===
# Ordine di ricerca: variabile SWI_HOME_DIR, swipl nel PATH, installazione standard Windows.
_SWIPL_CANDIDATI = [
    os.environ.get("SWI_HOME_DIR"),
    str(Path(shutil.which("swipl")).parent.parent) if shutil.which("swipl") else None,
    "C:/Program Files/swipl",
    "/usr/lib/swi-prolog",
    "/Applications/SWI-Prolog.app/Contents/swipl",
]


def setup_swipl_env() -> None:
    """Configura le variabili d'ambiente necessarie a PySwip per trovare SWI-Prolog."""
    for cand in _SWIPL_CANDIDATI:
        if cand and Path(cand).exists():
            os.environ["SWI_HOME_DIR"] = str(cand)
            bin_dir = str(Path(cand) / "bin")
            if bin_dir not in os.environ.get("PATH", ""):
                os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")
            return
    raise RuntimeError("SWI-Prolog non trovato: installarlo o impostare SWI_HOME_DIR")


# File dataset (da SCHEMA_REALE.md)
EXCEL_PATH = DATASET_DIR / "Dataset_Logistica_VRP_MachineLearning.xlsx"
XML_PATH = DATASET_DIR / "bari_osm.xml"
POSIZIONI_CLIENTI_CSV = DATASET_DIR / "clienti_posizione.csv"
ML_DATASET_CSV = DATASET_DIR / "ml_dataset.csv"

# File generati
GRAFO_PL = KB_DIR / "grafo.pl"
FLOTTA_PL = KB_DIR / "flotta.pl"
CLIENTI_PL = KB_DIR / "clienti.pl"
ZTL_PL = KB_DIR / "ztl_nodi.pl"
PREVISIONI_PL = KB_DIR / "previsioni.pl"
KB_PL = KB_DIR / "knowledge_base.pl"
GRAFO_PICKLE = KB_DIR / "grafo_python.pkl"

# === NOMI FOGLI EXCEL (da SCHEMA_REALE.md) ===
FOGLIO_FLOTTA = "1_Flotta_Veicoli"
FOGLIO_CLIENTI = "2_Anagrafica_Clienti"
FOGLIO_STORICO = "3_Tragitti_Mensili_Storico"

# === VELOCITA' PLAUSIBILI PER TIPO STRADA (km/h) — urbano Bari ===
# Valori di default: la KB puo' ridurli per classe di veicolo (vedi knowledge_base.pl)
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

# === BOUNDING BOX ZTL CENTRO BARI (Murat + Bari Vecchia, approssimato) ===
ZTL_LAT_MIN = 41.115
ZTL_LAT_MAX = 41.132
ZTL_LON_MIN = 16.865
ZTL_LON_MAX = 16.882

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

# === AREA DI SERVIZIO ===
# I clienti hanno indirizzi fittizi: quelli di Bari vengono posizionati su un nodo
# stradale reale della propria macrozona (vedi src/parsing/posiziona_clienti.py).
# Rettangoli (lat_min, lat_max, lon_min, lon_max) dei quartieri associati.
MACROZONE_BARI = {
    "Bari Citta": (41.112, 41.130, 16.860, 16.885),  # Murat, Madonnella, Bari Vecchia
    "Bari Nord": (41.110, 41.135, 16.825, 16.860),   # Liberta', Marconi, San Girolamo
    "Bari Sud": (41.085, 41.112, 16.865, 16.910),    # Carrassi, Poggiofranco, Japigia
}
# Tipi di strada su cui puo' trovarsi l'accesso di un cliente
HIGHWAY_CONSEGNA = {"residential", "tertiary", "secondary", "unclassified", "living_street"}

# === DEPOSITO (nodo di partenza dei furgoni) ===
# Agganciato al nodo piu' vicino del grafo
DEPOSITO_LAT = 41.092
DEPOSITO_LON = 16.850

# === COSTANTI ML ===
RANDOM_STATE = 42
N_RIPETIZIONI_CV = 3   # ripetizioni della CV esterna (gruppi rimescolati)
K_ESTERNO = 5          # fold esterni (raggruppati per data)
K_INTERNO = 3          # fold interni per la scelta degli iperparametri

# === COSTANTI CSP ===
TURNO_MIN = 540                 # durata del turno (08:00-17:00): deve coincidere con turno_lavoro/2 della KB
INIZIO_TURNO_MIN = 8 * 60
TEMPO_SCARICO_BASE_MIN = 10     # Tempo_Scarico_Previsto_min nel dataset
VELOCITA_MEDIA_URBANA_KMH = 25  # per stimare i tempi di spostamento nel CSP
FATTORE_TORTUOSITA = 1.4        # distanza stradale / linea d'aria: mediana misurata con A* (esperimento E2)
CSP_TIMEOUT_SECONDS = 20
