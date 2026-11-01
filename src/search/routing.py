"""
Costruzione dei giri di consegna di ciascun veicolo.

1) Ordine di visita: ricerca in profondita' Branch and Bound nello spazio
   delle sequenze parziali (stato = clienti gia' visitati in ordine, ora
   corrente). Costo = minuti di guida stimati + PESO_RITARDO * minuti di
   ritardo rispetto alle finestre effettive. Bound: costo del prefisso
   (i costi d'arco sono non negativi, quindi e' un limite inferiore).
   Per giri lunghi (> MAX_CLIENTI_BB) si usa l'ordine per inizio finestra.
2) Simulazione con A*: ogni tratta e' calcolata sul grafo stradale con il
   profilo del veicolo; prima di ogni tratta si chiede alla KB se il veicolo
   puo' trovarsi in ZTL a quell'ora (altrimenti i nodi ZTL vengono evitati).
   Il veicolo parte dal deposito (non prima dell'inizio del turno) in modo da
   arrivare all'apertura della prima finestra; se arriva in anticipo a un
   cliente successivo attende.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import math
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from src.config import FATTORE_TORTUOSITA, INIZIO_TURNO_MIN, VELOCITA_MEDIA_URBANA_KMH
from src.search.a_star import ProfiloVeicolo, a_star, haversine

PESO_RITARDO = 10.0     # 1 minuto di ritardo "costa" come 10 minuti di guida
MAX_CLIENTI_BB = 9


@dataclass
class Tappa:
    cliente: str
    arrivo_min: float
    inizio_servizio_min: float
    ritardo_min: float
    km: float
    nodi_espansi: int


@dataclass
class Giro:
    veicolo: str
    tappe: List[Tappa] = field(default_factory=list)
    partenza_min: float = 0.0
    km_totali: float = 0.0
    rientro_min: float = 0.0
    nodi_espansi: int = 0
    transiti_ztl: int = 0     # tratte in cui non era possibile evitare la ZTL

    @property
    def ritardi(self) -> int:
        return sum(1 for t in self.tappe if t.ritardo_min > 0)


def _minuti_stimati(km_linea_aria: float) -> float:
    return km_linea_aria * FATTORE_TORTUOSITA / VELOCITA_MEDIA_URBANA_KMH * 60


def ordina_visite(clienti: List[str], finestre: Dict[str, Tuple[int, int]],
                  servizio: Dict[str, int], coords: Dict[str, Tuple[float, float]],
                  deposito: Tuple[float, float]) -> List[str]:
    """Sequenza di visita a costo minimo (DF Branch and Bound)."""
    def t(a, b):
        pa = deposito if a is None else coords[a]
        pb = deposito if b is None else coords[b]
        return _minuti_stimati(haversine(*pa, *pb))

    if len(clienti) > MAX_CLIENTI_BB:
        return sorted(clienti, key=lambda c: (finestre[c][0], finestre[c][1]))

    migliore = {"costo": math.inf, "seq": None}

    def dfs(seq, ora, costo, rimanenti):
        if costo >= migliore["costo"]:
            return  # pruning: il prefisso costa gia' piu' della migliore soluzione
        if not rimanenti:
            totale = costo + t(seq[-1] if seq else None, None)
            if totale < migliore["costo"]:
                migliore["costo"], migliore["seq"] = totale, list(seq)
            return
        prec = seq[-1] if seq else None
        for c in sorted(rimanenti, key=lambda x: finestre[x][0]):
            guida = t(prec, c)
            arrivo = ora + guida
            inizio, fine = finestre[c]
            ritardo = max(0.0, arrivo - fine)
            seq.append(c)
            dfs(seq, max(arrivo, inizio) + servizio[c], costo + guida + PESO_RITARDO * ritardo,
                rimanenti - {c})
            seq.pop()

    dfs([], INIZIO_TURNO_MIN, 0.0, frozenset(clienti))
    return migliore["seq"]


def simula_giro(veicolo: str, sequenza: List[str], kb, data: Tuple[int, int, int],
                finestre: Dict[str, Tuple[int, int]], servizio: Dict[str, int],
                nodi: Dict[str, str], nodo_deposito: str,
                grafo: tuple, profilo_base: ProfiloVeicolo) -> Giro:
    """Percorre la sequenza con A* simulando orari, accesso ZTL e ritardi."""
    adj, coords, ztl = grafo
    giro = Giro(veicolo)

    def tratta(da: str, a: str, partenza: float):
        profilo = ProfiloVeicolo(profilo_base.velocita, profilo_base.vietate,
                                 evita_ztl=not kb.accesso_ztl(veicolo, *data, int(partenza)))
        r = a_star(da, a, adj, coords, profilo, ztl)
        if r.percorso is None:
            # la tratta non si puo' fare evitando la ZTL (es. uscita dalla ZTL
            # dopo una consegna): si percorre comunque e si registra il transito
            return a_star(da, a, adj, coords, ProfiloVeicolo(profilo.velocita, profilo.vietate), ztl), True
        return r, False

    # partenza dal deposito calcolata per arrivare all'apertura della prima finestra
    ora, nodo = float(INIZIO_TURNO_MIN), nodo_deposito
    if sequenza:
        r, _ = tratta(nodo, nodi[sequenza[0]], ora)
        ora = max(ora, finestre[sequenza[0]][0] - r.tempo_ore * 60)
    giro.partenza_min = ora

    for c in sequenza + [None]:
        dest = nodo_deposito if c is None else nodi[c]
        r, transito = tratta(nodo, dest, ora)
        giro.transiti_ztl += transito
        ora += r.tempo_ore * 60
        giro.km_totali += r.distanza_km
        giro.nodi_espansi += r.nodi_espansi
        if c is None:
            giro.rientro_min = ora
            break
        inizio, fine = finestre[c]
        inizio_servizio = max(ora, inizio)
        giro.tappe.append(Tappa(c, ora, inizio_servizio, max(0.0, ora - fine), r.distanza_km, r.nodi_espansi))
        ora = inizio_servizio + servizio[c]
        nodo = dest
    return giro
