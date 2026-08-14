import sys
import json
import time
import pickle
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import numpy as np
from scipy.spatial import cKDTree
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError

# Setup import path for src module
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from src.config import *
from src.parsing.excel_to_prolog import prepara_clienti, clienti_to_prolog


def geocodifica_con_cache(df_clienti: Any) -> Dict[str, Optional[List[float]]]:
    """
    Effettua la geocodifica degli indirizzi dei clienti usando Nominatim.
    Utilizza una cache su file JSON per evitare richieste duplicate.
    
    Args:
        df_clienti: DataFrame pandas con i dati dei clienti.
        
    Returns:
        Dict[str, Optional[List[float]]]: Mappatura tra Codice_Cliente e coordinate [lat, lon] (o None se fallisce).
    """
    cache_path = GEOCODING_CACHE
    geocoded_data: Dict[str, Optional[List[float]]] = {}
    
    if cache_path.exists():
        with open(cache_path, 'r', encoding='utf-8') as f:
            try:
                geocoded_data = json.load(f)
            except json.JSONDecodeError:
                print("[WARNING] File di cache non valido. Verra' ricreato.")
                geocoded_data = {}

    geolocator = Nominatim(user_agent="vrp_logistica_bari")
    
    updated = False
    for _, row in df_clienti.iterrows():
        codice = str(row['Codice_Cliente'])
        if codice in geocoded_data:
            continue
            
        indirizzo = f"{row['Indirizzo']}, {row['Citta']}, {row['CAP']}, Italy"
        print(f"[INFO] Geocoding {codice}: {indirizzo}")
        
        try:
            time.sleep(1.1)  # Rispetto limiti Nominatim
            location = geolocator.geocode(indirizzo, timeout=10)
            if location:
                geocoded_data[codice] = [location.latitude, location.longitude]
                print(f"  -> [OK] Trovato: {location.latitude}, {location.longitude}")
            else:
                geocoded_data[codice] = None
                print("  -> [ERROR] Non trovato.")
            updated = True
        except (GeocoderTimedOut, GeocoderServiceError) as e:
            print(f"  -> [ERROR] Eccezione Geopy: {e}")
            geocoded_data[codice] = None
            updated = True
            
    if updated:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(geocoded_data, f, indent=4)
            
    return geocoded_data


def trova_nodo_piu_vicino(lat: float, lon: float, nodi_grafo: Dict[str, Tuple[float, float]], kdtree: Optional[cKDTree] = None, nodi_ids: Optional[List[str]] = None) -> str:
    """
    Trova il nodo del grafo piu' vicino alle coordinate (lat, lon).
    
    Args:
        lat: Latitudine.
        lon: Longitudine.
        nodi_grafo: Dizionario {nodo_id: (lat, lon)}.
        kdtree: Istanza di cKDTree (opzionale, calcolata se None).
        nodi_ids: Lista delle chiavi dei nodi (opzionale).
        
    Returns:
        str: ID del nodo piu' vicino.
    """
    if kdtree is None or nodi_ids is None:
        nodi_ids = list(nodi_grafo.keys())
        coords = np.array([nodi_grafo[nid] for nid in nodi_ids])
        kdtree = cKDTree(coords)
        
    _, idx = kdtree.query([lat, lon])
    return nodi_ids[idx]


def fallback_centroide_macrozona(codice: str, riga_cliente: Any, df_clienti: Any, nodi_grafo: Dict[str, Tuple[float, float]], cache: Dict[str, Optional[List[float]]], kdtree: cKDTree, nodi_ids: List[str]) -> str:
    """
    Calcola un nodo di fallback basato sul centroide dei clienti con successo nella stessa macrozona.
    Se non ci sono clienti validi nella macrozona, usa le coordinate del deposito.
    """
    macrozona = riga_cliente['Macrozona']
    
    clienti_macrozona = df_clienti[df_clienti['Macrozona'] == macrozona]
    lat_list = []
    lon_list = []
    
    for _, row in clienti_macrozona.iterrows():
        cod = str(row['Codice_Cliente'])
        if cod in cache and cache[cod] is not None:
            lat_list.append(cache[cod][0])
            lon_list.append(cache[cod][1])
            
    if lat_list and lon_list:
        avg_lat = sum(lat_list) / len(lat_list)
        avg_lon = sum(lon_list) / len(lon_list)
        print(f"[INFO] Fallback per {codice}: Centroide Macrozona {macrozona} ({avg_lat:.5f}, {avg_lon:.5f})")
        return trova_nodo_piu_vicino(avg_lat, avg_lon, nodi_grafo, kdtree, nodi_ids)
    else:
        print(f"[INFO] Fallback estremo per {codice}: coordinate Deposito ({DEPOSITO_LAT}, {DEPOSITO_LON})")
        return trova_nodo_piu_vicino(DEPOSITO_LAT, DEPOSITO_LON, nodi_grafo, kdtree, nodi_ids)


def costruisci_mapping_cliente_nodo(df_clienti: Any, nodi_grafo: Dict[str, Tuple[float, float]]) -> Dict[str, str]:
    """
    Geocodifica i clienti e mappa ciascuno al nodo del grafo più vicino.
    
    Args:
        df_clienti: DataFrame pandas dei clienti.
        nodi_grafo: Dizionario {nodo_id: (lat, lon)}.
        
    Returns:
        Dict[str, str]: Mappa {Codice_Cliente: nodo_id}.
    """
    cache = geocodifica_con_cache(df_clienti)
    
    mapping: Dict[str, str] = {}
    nodi_ids = list(nodi_grafo.keys())
    coords = np.array([nodi_grafo[nid] for nid in nodi_ids])
    kdtree = cKDTree(coords)
    
    success_count = 0
    fallback_count = 0
    
    for _, row in df_clienti.iterrows():
        codice = str(row['Codice_Cliente'])
        coords_cliente = cache.get(codice)
        
        if coords_cliente is not None:
            lat, lon = coords_cliente
            nodo = trova_nodo_piu_vicino(lat, lon, nodi_grafo, kdtree, nodi_ids)
            mapping[codice] = nodo
            success_count += 1
        else:
            nodo_fallback = fallback_centroide_macrozona(codice, row, df_clienti, nodi_grafo, cache, kdtree, nodi_ids)
            mapping[codice] = nodo_fallback
            fallback_count += 1
            
    print(f"\n[STATISTICHE]")
    print(f"Clienti totali: {len(df_clienti)}")
    print(f"Geocodifica OK: {success_count} ({(success_count/len(df_clienti))*100:.1f}%)")
    print(f"Fallback applicati: {fallback_count} ({(fallback_count/len(df_clienti))*100:.1f}%)")
    
    return mapping


if __name__ == "__main__":
    print("[INFO] Avvio geocodifica e mapping clienti...")
    
    # 1. Carica dataframe clienti
    df_clienti = prepara_clienti()
    if df_clienti.empty:
        print("[ERROR] DataFrame clienti vuoto. Uscita.")
        sys.exit(1)
        
    # 2. Carica nodi grafo
    if not GRAFO_PICKLE.exists():
        print(f"[ERROR] Grafo pickle non trovato in {GRAFO_PICKLE}")
        sys.exit(1)
        
    with open(GRAFO_PICKLE, 'rb') as f:
        grafo_data = pickle.load(f)
        
    nodi_grafo = grafo_data.get('coords', {})
    if not nodi_grafo:
        print("[ERROR] Nessuna coordinata nodo trovata nel grafo.")
        sys.exit(1)
        
    print(f"[INFO] Trovati {len(nodi_grafo)} nodi nel grafo.")
    
    # 3. Costruisci mapping
    mapping = costruisci_mapping_cliente_nodo(df_clienti, nodi_grafo)
    
    # 4. Genera file prolog
    clienti_to_prolog(mapping, df_clienti)
    
    print("[INFO] Processo completato con successo.")
