import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

import xml.etree.ElementTree as ET
import pickle
from math import radians, sin, cos, sqrt, atan2
from src.config import *

R_TERRA_KM = 6371.0

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculates the great-circle distance between two points on the Earth surface."""
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R_TERRA_KM * c

def nodo_in_ztl(lat: float, lon: float) -> bool:
    """Checks if a node is inside the ZTL bounding box."""
    return ZTL_LAT_MIN <= lat <= ZTL_LAT_MAX and ZTL_LON_MIN <= lon <= ZTL_LON_MAX

def carica_grafo_xml(path: str) -> tuple[dict[str, tuple[float, float]], list[tuple[str, str, str]]]:
    """Parses OSM XML to extract valid nodes and edges."""
    tree = ET.parse(path)
    root = tree.getroot()
    
    all_nodes = {}
    for node in root.findall('node'):
        node_id = 'n' + node.get('id')
        lat = float(node.get('lat'))
        lon = float(node.get('lon'))
        all_nodes[node_id] = (lat, lon)
        
    archi = []
    used_nodes = set()
    
    for way in root.findall('way'):
        highway_tag = None
        for tag in way.findall('tag'):
            if tag.get('k') == 'highway':
                highway_tag = tag.get('v')
                break
                
        if highway_tag in HIGHWAY_PERCORRIBILI:
            nds = [ 'n' + nd.get('ref') for nd in way.findall('nd') ]
            # keep only nodes that actually exist in all_nodes
            valid_nds = [nd for nd in nds if nd in all_nodes]
            
            for i in range(len(valid_nds) - 1):
                n1 = valid_nds[i]
                n2 = valid_nds[i+1]
                archi.append((n1, n2, highway_tag))
                used_nodes.add(n1)
                used_nodes.add(n2)
                
    nodi = {nid: all_nodes[nid] for nid in used_nodes}
    return nodi, archi

def scrivi_fatti_prolog(nodi: dict[str, tuple[float, float]], archi: list[tuple[str, str, str]], output_path: str) -> None:
    """Writes nodes and edges as Prolog facts."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("% Fatti: nodo(ID, Lat, Lon).\n")
        for nid, (lat, lon) in nodi.items():
            f.write(f"nodo({nid}, {lat}, {lon}).\n")
            
        f.write("\n% Fatti: arco(ID1, ID2, TipoStrada).\n")
        for n1, n2, tipo in archi:
            f.write(f"arco({n1}, {n2}, '{tipo}').\n")
            f.write(f"arco({n2}, {n1}, '{tipo}').\n")
            
        f.write("\n% Fatti: in_ztl(ID).\n")
        for nid, (lat, lon) in nodi.items():
            if nodo_in_ztl(lat, lon):
                f.write(f"in_ztl({nid}).\n")

def salva_grafo_python(nodi: dict[str, tuple[float, float]], archi: list[tuple[str, str, str]], output_path: str) -> None:
    """Saves adjacency dictionary and coordinates into a Python pickle file."""
    adj = {nid: [] for nid in nodi}
    
    for n1, n2, tipo in archi:
        lat1, lon1 = nodi[n1]
        lat2, lon2 = nodi[n2]
        dist = haversine_km(lat1, lon1, lat2, lon2)
        adj[n1].append((n2, dist, tipo))
        adj[n2].append((n1, dist, tipo))
        
    data = {
        'adj': adj,
        'coords': nodi
    }
    
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'wb') as f:
        pickle.dump(data, f)

if __name__ == '__main__':
    print("[INFO] Caricamento del grafo da XML...")
    nodi, archi = carica_grafo_xml(str(XML_PATH))
    print(f"[OK] Trovati {len(nodi)} nodi e {len(archi)} archi.")
    
    ztl_nodes = sum(1 for lat, lon in nodi.values() if nodo_in_ztl(lat, lon))
    print(f"[INFO] Nodi in ZTL: {ztl_nodes}")
    
    print("[INFO] Scrittura dei fatti Prolog in corso...")
    scrivi_fatti_prolog(nodi, archi, str(GRAFO_PL))
    print("[OK] Fatti Prolog generati.")
    
    print("[INFO] Salvataggio del grafo Python in corso...")
    salva_grafo_python(nodi, archi, str(GRAFO_PICKLE))
    print("[OK] Pickle salvato.")
