"""
Parsing della rete stradale OpenStreetMap (XML) e generazione:
- dei fatti Prolog nodo/3, arco/3, in_ztl/1 (kb/grafo.pl, kb/ztl_nodi.pl)
- del grafo in formato Python (kb/grafo_python.pkl) usato da A*.

Rispetto al semplice elenco di way, il grafo:
- e' ORIENTATO: rispetta i sensi unici (oneway=yes/-1, rotatorie);
- e' ridotto ai nodi raggiungibili dal deposito e da cui si puo' tornare al
  deposito, cosi' da ogni nodo si puo' raggiungere ogni altro nodo (altrimenti
  A* fallirebbe su clienti agganciati a tratti isolati o a strade senza uscita
  percorribili solo in un verso).
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

import xml.etree.ElementTree as ET
import pickle
from collections import deque
from math import radians, sin, cos, sqrt, atan2
from src.config import (XML_PATH, GRAFO_PL, ZTL_PL, GRAFO_PICKLE, HIGHWAY_PERCORRIBILI,
                        DEPOSITO_LAT, DEPOSITO_LON,
                        ZTL_LAT_MIN, ZTL_LAT_MAX, ZTL_LON_MIN, ZTL_LON_MAX)

R_TERRA_KM = 6371.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distanza ortodromica (in km) tra due punti della superficie terrestre."""
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R_TERRA_KM * c


def nodo_in_ztl(lat: float, lon: float) -> bool:
    """Verifica se un nodo cade nel rettangolo della ZTL."""
    return ZTL_LAT_MIN <= lat <= ZTL_LAT_MAX and ZTL_LON_MIN <= lon <= ZTL_LON_MAX


def senso_di_marcia(tags: dict) -> int:
    """
    Restituisce 0 se la strada e' a doppio senso, 1 se a senso unico nel verso
    dei nodi della way, -1 se a senso unico nel verso opposto.
    """
    oneway = tags.get("oneway", "no")
    if oneway in ("yes", "true", "1"):
        return 1
    if oneway == "-1":
        return -1
    if tags.get("junction") in ("roundabout", "circular") and oneway != "no":
        return 1
    if tags.get("highway") in ("motorway", "motorway_link") and oneway != "no":
        return 1
    return 0


def carica_grafo_xml(path: str) -> tuple[dict[str, tuple[float, float]], list[tuple[str, str, str]]]:
    """Estrae dall'XML OSM i nodi e gli archi ORIENTATI delle strade percorribili."""
    root = ET.parse(path).getroot()

    all_nodes = {}
    for node in root.findall('node'):
        all_nodes['n' + node.get('id')] = (float(node.get('lat')), float(node.get('lon')))

    archi = []
    for way in root.findall('way'):
        tags = {t.get('k'): t.get('v') for t in way.findall('tag')}
        highway_tag = tags.get('highway')
        if highway_tag not in HIGHWAY_PERCORRIBILI:
            continue
        nds = ['n' + nd.get('ref') for nd in way.findall('nd')]
        nds = [nd for nd in nds if nd in all_nodes]
        verso = senso_di_marcia(tags)
        for n1, n2 in zip(nds, nds[1:]):
            if verso in (0, 1):
                archi.append((n1, n2, highway_tag))
            if verso in (0, -1):
                archi.append((n2, n1, highway_tag))

    usati = {n for a in archi for n in a[:2]}
    nodi = {nid: all_nodes[nid] for nid in usati}
    return nodi, archi


def raggiungibili(sorgente: str, vicini: dict) -> set:
    """Nodi raggiungibili da sorgente (ricerca in ampiezza)."""
    visti, frontiera = {sorgente}, deque([sorgente])
    while frontiera:
        for w in vicini[frontiera.popleft()]:
            if w not in visti:
                visti.add(w)
                frontiera.append(w)
    return visti


def nodi_mutuamente_raggiungibili(nodi: dict, archi: list, radice: str) -> set:
    """
    Nodi n tali che esiste un percorso radice -> n e un percorso n -> radice:
    l'intersezione tra la visita in avanti e quella sul grafo con archi invertiti.
    Ogni coppia di questi nodi e' collegata in entrambi i versi passando per la radice.
    """
    succ = {n: [] for n in nodi}
    pred = {n: [] for n in nodi}
    for a, b, _ in archi:
        succ[a].append(b)
        pred[b].append(a)
    return raggiungibili(radice, succ) & raggiungibili(radice, pred)


def scrivi_fatti_prolog(nodi: dict[str, tuple[float, float]], archi: list[tuple[str, str, str]]) -> None:
    """Scrive nodi e archi come fatti Prolog e, separatamente, i nodi in ZTL."""
    GRAFO_PL.parent.mkdir(parents=True, exist_ok=True)
    with open(GRAFO_PL, 'w', encoding='utf-8') as f:
        f.write("% Fatti generati da src/parsing/xml_to_prolog.py\n")
        f.write("% nodo(ID, Lat, Lon).\n")
        for nid, (lat, lon) in nodi.items():
            f.write(f"nodo({nid}, {lat}, {lon}).\n")
        f.write("\n% arco(Da, A, TipoStrada): archi orientati (sensi unici rispettati).\n")
        for n1, n2, tipo in archi:
            f.write(f"arco({n1}, {n2}, {tipo}).\n")

    with open(ZTL_PL, 'w', encoding='utf-8') as f:
        f.write("% Nodi del grafo dentro la ZTL (generati da src/parsing/xml_to_prolog.py)\n")
        for nid, (lat, lon) in nodi.items():
            if nodo_in_ztl(lat, lon):
                f.write(f"in_ztl({nid}).\n")


def salva_grafo_python(nodi: dict[str, tuple[float, float]], archi: list[tuple[str, str, str]]) -> None:
    """Salva lista di adiacenza (orientata) e coordinate in un pickle."""
    adj = {nid: [] for nid in nodi}
    for n1, n2, tipo in archi:
        lat1, lon1 = nodi[n1]
        lat2, lon2 = nodi[n2]
        adj[n1].append((n2, haversine_km(lat1, lon1, lat2, lon2), tipo))
    with open(GRAFO_PICKLE, 'wb') as f:
        pickle.dump({'adj': adj, 'coords': nodi}, f)


if __name__ == '__main__':
    print("[INFO] Caricamento del grafo da XML...")
    nodi, archi = carica_grafo_xml(str(XML_PATH))
    print(f"[OK] Grafo completo: {len(nodi)} nodi, {len(archi)} archi orientati.")

    radice = min(nodi, key=lambda n: haversine_km(DEPOSITO_LAT, DEPOSITO_LON, *nodi[n]))
    connessi = nodi_mutuamente_raggiungibili(nodi, archi, radice)
    nodi = {n: c for n, c in nodi.items() if n in connessi}
    archi = [a for a in archi if a[0] in connessi and a[1] in connessi]
    print(f"[OK] Nodi raggiungibili dal deposito e da cui si torna al deposito: "
          f"{len(nodi)} nodi, {len(archi)} archi.")
    print(f"[INFO] Nodi in ZTL: {sum(1 for lat, lon in nodi.values() if nodo_in_ztl(lat, lon))}")

    scrivi_fatti_prolog(nodi, archi)
    salva_grafo_python(nodi, archi)
    print("[OK] Fatti Prolog e pickle salvati.")
