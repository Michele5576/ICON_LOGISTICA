"""
Ricerca del percorso a tempo minimo sul grafo stradale orientato di Bari.

- A*: f(n) = g(n) + h(n), con g = tempo di percorrenza (ore) e
  h = distanza in linea d'aria / V_MAX_KMH. h e' ammissibile (nessun arco
  si percorre a piu' di V_MAX_KMH, quindi h non sovrastima mai il tempo
  residuo) e consistente (disuguaglianza triangolare della distanza
  ortodromica): A* con eliminazione dei duplicati resta ottimale.
- LCFS (Lowest-Cost-First Search): stessa procedura con h = 0,
  usata come termine di confronto per misurare il guadagno dell'euristica.

Vincoli di transito forniti dalla KB, per veicolo:
- velocita' per tipo di strada (default ed eccezioni per classe di veicolo);
- tipi di strada vietati, ammessi solo come ultimo arco verso la destinazione;
- nodi ZTL da evitare se il veicolo non ha accesso alla ZTL in quel momento
  (sempre ammessi destinazione e partenza).
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import heapq
import math
import pickle
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from src.config import GRAFO_PICKLE, VELOCITA_KMH, V_MAX_KMH, ZTL_PL


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distanza ortodromica in km."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


@dataclass
class ProfiloVeicolo:
    """Vincoli di transito di un veicolo (derivati dalla KB)."""
    velocita: Dict[str, float] = field(default_factory=lambda: dict(VELOCITA_KMH))
    vietate: Set[str] = field(default_factory=set)
    evita_ztl: bool = False


@dataclass
class Risultato:
    percorso: Optional[List[str]]
    distanza_km: float
    tempo_ore: float
    nodi_espansi: int


def ricerca(start: str, goal: str, adj: dict, coords: dict,
            profilo: ProfiloVeicolo, ztl_set: Set[str], euristica: bool = True) -> Risultato:
    """A* (euristica=True) o LCFS (euristica=False) su grafo con pruning dei cammini multipli."""
    if start not in coords or goal not in coords:
        return Risultato(None, math.inf, math.inf, 0)
    lat_g, lon_g = coords[goal]

    def h(n: str) -> float:
        if not euristica:
            return 0.0
        lat, lon = coords[n]
        return haversine(lat, lon, lat_g, lon_g) / V_MAX_KMH

    frontiera = [(h(start), 0.0, start)]
    g = {start: 0.0}
    dist = {start: 0.0}
    padre = {}
    chiusi = set()
    espansi = 0
    v_default = profilo.velocita.get("default", VELOCITA_KMH["default"])

    while frontiera:
        _, g_corr, n = heapq.heappop(frontiera)
        if n in chiusi:
            continue  # cammino multiplo gia' espanso con costo minore
        chiusi.add(n)
        espansi += 1
        if n == goal:
            percorso = [n]
            while n in padre:
                n = padre[n]
                percorso.append(n)
            return Risultato(percorso[::-1], dist[goal], g[goal], espansi)

        for vicino, km, tipo in adj.get(n, []):
            if vicino in chiusi:
                continue
            if tipo in profilo.vietate and vicino != goal:
                continue
            if profilo.evita_ztl and vicino in ztl_set and vicino != goal:
                continue
            nuovo_g = g_corr + km / profilo.velocita.get(tipo, v_default)
            if nuovo_g < g.get(vicino, math.inf):
                g[vicino] = nuovo_g
                dist[vicino] = dist[n] + km
                padre[vicino] = n
                heapq.heappush(frontiera, (nuovo_g + h(vicino), nuovo_g, vicino))

    return Risultato(None, math.inf, math.inf, espansi)


def a_star(start, goal, adj, coords, profilo, ztl_set) -> Risultato:
    return ricerca(start, goal, adj, coords, profilo, ztl_set, euristica=True)


def lcfs(start, goal, adj, coords, profilo, ztl_set) -> Risultato:
    return ricerca(start, goal, adj, coords, profilo, ztl_set, euristica=False)


def carica_grafo() -> Tuple[Dict, Dict, Set]:
    """Carica lista di adiacenza, coordinate e insieme dei nodi ZTL."""
    with open(GRAFO_PICKLE, "rb") as f:
        data = pickle.load(f)
    ztl_set = set()
    if ZTL_PL.exists():
        for riga in ZTL_PL.read_text(encoding="utf-8").splitlines():
            if riga.startswith("in_ztl("):
                ztl_set.add(riga[len("in_ztl("):-2])
    return data["adj"], data["coords"], ztl_set


def trova_nodo_vicino(lat: float, lon: float, coords: Dict[str, Tuple[float, float]]) -> str:
    return min(coords, key=lambda n: haversine(lat, lon, *coords[n]))


if __name__ == "__main__":
    import random
    import time
    from src.config import DEPOSITO_LAT, DEPOSITO_LON

    adj, coords, ztl = carica_grafo()
    print(f"[OK] Grafo: {len(coords)} nodi, {sum(len(v) for v in adj.values())} archi, {len(ztl)} nodi ZTL")
    dep = trova_nodo_vicino(DEPOSITO_LAT, DEPOSITO_LON, coords)
    dest = random.Random(0).choice(sorted(ztl))
    for nome, fn in [("A*", a_star), ("LCFS", lcfs)]:
        t = time.perf_counter()
        r = fn(dep, dest, adj, coords, ProfiloVeicolo(), ztl)
        print(f"{nome}: {r.distanza_km:.2f} km, {r.tempo_ore * 60:.1f} min, "
              f"{r.nodi_espansi} nodi espansi, {time.perf_counter() - t:.3f} s")
