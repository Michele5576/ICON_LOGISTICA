import sys
from pathlib import Path
import pandas as pd
import logging
import re
from typing import Dict, Tuple

# Setup import path for src module
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from src.config import EXCEL_PATH, FOGLIO_FLOTTA, FOGLIO_CLIENTI, FOGLIO_STORICO, FLOTTA_PL, CLIENTI_PL

# Configure logging
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")


def sanitize_prolog_atom(s: str) -> str:
    """
    Sanitizes a string to be a valid Prolog atom.
    Lowercases and replaces '-' and ' ' with '_'.
    """
    s = str(s).lower()
    s = re.sub(r'[\-\s]+', '_', s)
    return s


def parse_flotta() -> pd.DataFrame:
    """
    Legge il foglio flotta e restituisce il DataFrame corrispondente.
    """
    if not EXCEL_PATH.exists():
        logging.error(f"Excel file not found: {EXCEL_PATH}")
        return pd.DataFrame()
    
    df = pd.read_excel(EXCEL_PATH, sheet_name=FOGLIO_FLOTTA)
    return df


def genera_flotta_prolog(df_flotta: pd.DataFrame) -> None:
    """
    Genera il file flotta.pl a partire dal dataframe della flotta.
    """
    facts = []
    
    for _, row in df_flotta.iterrows():
        # Handle missing Cella_Frigo
        cella_frigo_raw = str(row.get('Cella_Frigo', 'NO')).strip().lower()
        if pd.isna(row.get('Cella_Frigo')):
             cella_frigo_raw = 'no'
        
        cella_frigo = 'si' if cella_frigo_raw == 'si' else 'no'
        
        id_furgone = sanitize_prolog_atom(row['ID_Veicolo'])
        capacita = int(row['Capacita_Carico_kg'])
        volume = row['Volume_Carico_m3']
        
        # Volume could be int or float. Let's keep it as is.
        if isinstance(volume, float) and volume.is_integer():
            volume = int(volume)
            
        facts.append(f"furgone({id_furgone}, {capacita}, {volume}, {cella_frigo}).")
        
        if capacita <= 800:
            facts.append(f"permesso_ztl({id_furgone}).")
            
    try:
        FLOTTA_PL.parent.mkdir(parents=True, exist_ok=True)
        with open(FLOTTA_PL, 'w', encoding='utf-8') as f:
            f.write("% Fatti flotta veicoli generati automaticamente\n")
            f.write("\n".join(facts))
            f.write("\n")
        logging.info(f"Generated {FLOTTA_PL} with {len(facts)} facts.")
    except Exception as e:
        logging.error(f"Failed to write {FLOTTA_PL}: {e}")


def prepara_clienti() -> pd.DataFrame:
    """
    Legge il foglio clienti e restituisce il DataFrame pronto per il geocoding.
    """
    if not EXCEL_PATH.exists():
        logging.error(f"Excel file not found: {EXCEL_PATH}")
        return pd.DataFrame()
    
    df = pd.read_excel(EXCEL_PATH, sheet_name=FOGLIO_CLIENTI)
    return df


def clienti_to_prolog(nodo_per_cliente: Dict[str, str], df_clienti: pd.DataFrame = None) -> None:
    """
    Scrive il file clienti.pl usando il dizionario nodo_per_cliente ottenuto
    dalla fase di geocoding.
    """
    if df_clienti is None:
        df_clienti = prepara_clienti()
        
    facts = []
    for _, row in df_clienti.iterrows():
        codice_raw = sanitize_prolog_atom(row['Codice_Cliente'])
        # Prepend 'c_' to numeric codes so they are Prolog atoms, not integers
        codice = f"c_{codice_raw}" if codice_raw[0].isdigit() else codice_raw
        # Look up the node mapping using the original string key
        nodo_raw = nodo_per_cliente.get(str(row['Codice_Cliente']))
        
        if not nodo_raw:
            # Fallback if dictionary has sanitized keys
            nodo_raw = nodo_per_cliente.get(codice_raw)
            
        if nodo_raw:
            # nodo IDs already have 'n' prefix from xml_to_prolog — don't re-sanitize
            nodo = nodo_raw
            orario = row.get('Orario_Consegna_Richiesto', '')
            if pd.isna(orario):
                orario = ''
                
            # E.g. cliente(c_983810, n5171427190, '12:00 - 14:00').
            facts.append(f"cliente({codice}, {nodo}, '{orario}').")
        else:
            logging.warning(f"Nessun nodo trovato per il cliente {codice}")
            
    try:
        CLIENTI_PL.parent.mkdir(parents=True, exist_ok=True)
        with open(CLIENTI_PL, 'w', encoding='utf-8') as f:
            f.write("% Fatti clienti generati automaticamente\n")
            f.write("\n".join(facts))
            f.write("\n")
        logging.info(f"Generated {CLIENTI_PL} with {len(facts)} facts.")
    except Exception as e:
        logging.error(f"Failed to write {CLIENTI_PL}: {e}")


def carica_storico() -> pd.DataFrame:
    """
    Legge il foglio dello storico mensile dei tragitti.
    """
    if not EXCEL_PATH.exists():
        logging.error(f"Excel file not found: {EXCEL_PATH}")
        return pd.DataFrame()
    
    df = pd.read_excel(EXCEL_PATH, sheet_name=FOGLIO_STORICO)
    return df


if __name__ == "__main__":
    logging.info("Iniziando il parsing dei dati Excel...")
    
    # 1. Flotta
    df_f = parse_flotta()
    if not df_f.empty:
        genera_flotta_prolog(df_f)
    
    # 2. Clienti (preparazione)
    df_c = prepara_clienti()
    if not df_c.empty:
        logging.info(f"Caricati {len(df_c)} clienti. Geocoding necessario prima di esportare in Prolog.")
        
    # 3. Storico
    df_s = carica_storico()
    if not df_s.empty:
        logging.info(f"Caricate {len(df_s)} righe di storico.")
        
    logging.info("Operazione completata.")
