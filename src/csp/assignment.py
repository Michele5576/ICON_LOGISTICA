"""
Assegnamento dei clienti del giorno ai veicoli come CSP con vincoli soft
(problema di ottimizzazione vincolata).

Variabili   : un cliente da servire  -> X_c
Domini      : veicoli IDONEI per c in quella data, derivati dalla KB
              (ZTL, permessi, eventi, finestre, turno) = consistenza di nodo
Vincoli rigidi:
  H1 (binari)  compatibilita' temporale: se X_c1 = X_c2 = v deve esistere un
               ordine di visita (c1 prima di c2 o viceversa) che rispetta le
               finestre effettive di entrambi per il veicolo v;
  H2 (n-ario)  carico del turno: per ogni v, la somma di durata del servizio
               (prevista dal ML, via KB) e del tempo minimo di arrivo al
               cliente (dal vicino piu' prossimo) non supera il turno.
               E' un rilassamento: non esclude soluzioni ammissibili.
Vincoli flessibili (soft, costi da minimizzare):
  S1 dispersione: per ogni coppia di clienti sullo stesso veicolo, la loro
     distanza stimata (km);
  S2 attivazione: costo fisso per ogni veicolo utilizzato.

Algoritmi:
  - GAC sui vincoli binari H1, prima della ricerca e dopo ogni scelta;
  - Branch and Bound in profondita' sulle assegnazioni parziali con
    separazione dei domini (un caso per valore) e bound ammissibile (ESATTO);
  - Simulated Annealing su assegnamenti completi, con costo elevato per le
    violazioni dei vincoli rigidi (APPROSSIMATO).
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import math
import random
import time
from collections import deque
from dataclasses import dataclass
from itertools import combinations
from typing import Dict, List, Optional, Tuple

from src.config import (CSP_TIMEOUT_SECONDS, FATTORE_TORTUOSITA, TURNO_MIN,
                        VELOCITA_MEDIA_URBANA_KMH)

COSTO_ATTIVAZIONE_KM = 15.0   # S2: costo di un veicolo in piu', in km equivalenti
PENALITA_HARD = 1000.0        # costo di ogni violazione di un vincolo rigido nel simulated annealing


@dataclass
class IstanzaCSP:
    clienti: List[str]
    veicoli: List[str]
    domini: Dict[str, List[str]]                   # c -> veicoli idonei
    finestre: Dict[Tuple[str, str], List[Tuple[int, int]]]   # (v, c) -> finestre effettive
    servizio: Dict[str, int]                       # c -> minuti di servizio
    km: Dict[Tuple[str, str], float]               # distanza stimata tra due clienti (simmetrica)
    km_deposito: Dict[str, float]                  # distanza stimata deposito-cliente
    turno_min: int = TURNO_MIN

    def minuti(self, km: float) -> float:
        return km / VELOCITA_MEDIA_URBANA_KMH * 60

    def d(self, a: str, b: str) -> float:
        return self.km[(a, b)] if (a, b) in self.km else self.km[(b, a)]

    def __post_init__(self):
        # tempo minimo per arrivare a c (dal cliente piu' vicino o dal deposito)
        self.arrivo_min = {
            c: self.minuti(min([self.km_deposito[c]] + [self.d(c, o) for o in self.clienti if o != c]))
            for c in self.clienti}
        self.carico = {c: self.servizio[c] + self.arrivo_min[c] for c in self.clienti}


@dataclass
class Soluzione:
    assegnamento: Dict[str, str]
    costo: float
    ottima: bool
    nodi: int = 0
    tempo_s: float = 0.0
    valori_rimossi_gac: int = 0
    violazioni: int = 0


# ---------------------------------------------------------------------------
# Vincoli
# ---------------------------------------------------------------------------

def ordine_ammissibile(ist: IstanzaCSP, v: str, a: str, b: str) -> bool:
    """a poi b sul veicolo v: arrivo piu' presto in a, servizio, spostamento, entro la fine di b."""
    for ia, fa in ist.finestre[(v, a)]:
        for ib, fb in ist.finestre[(v, b)]:
            fine_a = ia + ist.servizio[a]
            arrivo_b = max(ib, fine_a + ist.minuti(ist.d(a, b)))
            if arrivo_b <= fb:
                return True
    return False


def compatibili(ist: IstanzaCSP, v: str, a: str, b: str) -> bool:
    """Vincolo H1 tra a e b quando entrambi sono assegnati a v."""
    return ordine_ammissibile(ist, v, a, b) or ordine_ammissibile(ist, v, b, a)


def costo_assegnamento(ist: IstanzaCSP, ass: Dict[str, str]) -> float:
    per_veicolo: Dict[str, List[str]] = {}
    for c, v in ass.items():
        per_veicolo.setdefault(v, []).append(c)
    costo = COSTO_ATTIVAZIONE_KM * len(per_veicolo)
    for lista in per_veicolo.values():
        costo += sum(ist.d(a, b) for a, b in combinations(lista, 2))
    return costo


def violazioni_hard(ist: IstanzaCSP, ass: Dict[str, str]) -> int:
    n = 0
    per_veicolo: Dict[str, List[str]] = {}
    for c, v in ass.items():
        if v not in ist.domini[c]:
            n += 1
        per_veicolo.setdefault(v, []).append(c)
    for v, lista in per_veicolo.items():
        n += sum(1 for a, b in combinations(lista, 2) if not compatibili(ist, v, a, b))
        if sum(ist.carico[c] for c in lista) > ist.turno_min:
            n += 1
    return n


# ---------------------------------------------------------------------------
# GAC (AC-3) sui vincoli binari H1
# ---------------------------------------------------------------------------

def gac(ist: IstanzaCSP, domini: Dict[str, List[str]],
        cambiata: Optional[str] = None) -> Tuple[Dict[str, List[str]], int]:
    """
    Consistenza d'arco sui vincoli binari H1: il valore v di X_a e' supportato
    rispetto a X_b se esiste un valore w di X_b con w != v oppure con w == v e
    a, b compatibili su v. Senza 'cambiata' si parte da tutti gli archi; con
    'cambiata' solo dagli archi (X_a, X_cambiata), dopo che il suo dominio e'
    stato ridotto.
    """
    dom = {c: list(d) for c, d in domini.items()}
    if cambiata is None:
        coda = deque((a, b) for a in dom for b in dom if a != b)
    else:
        coda = deque((a, cambiata) for a in dom if a != cambiata)
    rimossi = 0
    while coda:
        a, b = coda.popleft()
        da_togliere = [v for v in dom[a]
                       if not any(w != v or compatibili(ist, v, a, b) for w in dom[b])]
        if da_togliere:
            dom[a] = [v for v in dom[a] if v not in da_togliere]
            rimossi += len(da_togliere)
            if not dom[a]:
                break
            coda.extend((c, a) for c in dom if c not in (a, b))
    return dom, rimossi


# ---------------------------------------------------------------------------
# Branch and Bound in profondita'
# ---------------------------------------------------------------------------

def branch_and_bound(ist: IstanzaCSP, timeout: float = CSP_TIMEOUT_SECONDS,
                     usa_gac: bool = True, iniziale: Optional[Soluzione] = None) -> Optional[Soluzione]:
    """
    Ricerca in profondita' nello spazio delle assegnazioni parziali, combinata
    con la consistenza (schema Con_Solve): a ogni passo il dominio di una
    variabile viene separato in un caso per valore e GAC propaga la scelta.
    Il costo dei vincoli soft si somma quando entrambi i clienti di una coppia
    sono assegnati (costi d'arco non negativi), quindi il bound e' ammissibile.

    iniziale: soluzione ammissibile (es. dal Simulated Annealing) il cui costo
    fa da limite iniziale del Branch and Bound (altrimenti infinito).
    """
    t0 = time.perf_counter()
    domini, rimossi = gac(ist, ist.domini) if usa_gac else (ist.domini, 0)
    if any(not d for d in domini.values()):
        return None

    migliore = {"costo": math.inf, "ass": None}
    if iniziale is not None and iniziale.violazioni == 0:
        migliore = {"costo": iniziale.costo + 1e-9, "ass": dict(iniziale.assegnamento)}
    nodi = [0]
    scaduto = [False]
    # ordine statico delle variabili: prima i clienti che pesano di piu' sul turno
    ordine = sorted(ist.clienti, key=lambda c: -ist.carico[c])
    assegnati: Dict[str, str] = {}
    membri: Dict[str, List[str]] = {v: [] for v in ist.veicoli}
    carico: Dict[str, float] = {v: 0.0 for v in ist.veicoli}

    def costo_incrementale(c: str, v: str) -> float:
        extra = COSTO_ATTIVAZIONE_KM if not membri[v] else 0.0
        return extra + sum(ist.d(c, o) for o in membri[v])

    def bound(costo: float, dom: Dict[str, List[str]], da: int) -> float:
        # costo minimo che ogni cliente non assegnato aggiungera' rispetto agli
        # assegnati (le coppie tra non assegnati e le attivazioni sono >= 0)
        return costo + sum(min(sum(ist.d(c, o) for o in membri[v]) for v in dom[c])
                           for c in ordine[da:])

    def dfs(i: int, costo: float, dom: Dict[str, List[str]]) -> None:
        if time.perf_counter() - t0 > timeout:
            scaduto[0] = True
            return
        nodi[0] += 1
        if i == len(ordine):
            if costo < migliore["costo"]:
                migliore["costo"], migliore["ass"] = costo, dict(assegnati)
            return
        if bound(costo, dom, i) >= migliore["costo"]:
            return
        c = ordine[i]
        for v in sorted(dom[c], key=lambda v: costo_incrementale(c, v)):
            if carico[v] + ist.carico[c] > ist.turno_min:   # vincolo rigido H2
                continue
            nuovo_dom = dict(dom)
            nuovo_dom[c] = [v]
            if usa_gac:
                nuovo_dom, _ = gac(ist, nuovo_dom, cambiata=c)
                if any(not d for d in nuovo_dom.values()):
                    continue
            elif not all(compatibili(ist, v, c, o) for o in membri[v]):   # vincolo rigido H1
                continue
            inc = costo_incrementale(c, v)
            assegnati[c] = v
            membri[v].append(c)
            carico[v] += ist.carico[c]
            dfs(i + 1, costo + inc, nuovo_dom)
            del assegnati[c]
            membri[v].pop()
            carico[v] -= ist.carico[c]
            if scaduto[0]:
                return

    dfs(0, 0.0, domini)
    if migliore["ass"] is None:
        return None
    return Soluzione(migliore["ass"], costo_assegnamento(ist, migliore["ass"]), ottima=not scaduto[0], nodi=nodi[0],
                     tempo_s=time.perf_counter() - t0, valori_rimossi_gac=rimossi,
                     violazioni=violazioni_hard(ist, migliore["ass"]))


# ---------------------------------------------------------------------------
# Simulated Annealing
# ---------------------------------------------------------------------------

def simulated_annealing(ist: IstanzaCSP, seed: int = 0, iterazioni: int = 20000,
                        t_iniziale: float = 5.0, alfa: float = 0.9999) -> Soluzione:
    """
    Ricerca locale stocastica su assegnamenti completi.
    Funzione da minimizzare: costo soft + PENALITA_HARD * violazioni hard.
    Mossa: un cliente scelto a caso passa a un altro veicolo del suo dominio.
    Una mossa peggiorativa di delta e' accettata con probabilita' e^(-delta/T);
    la temperatura scende geometricamente, T <- alfa * T.
    T iniziale e alfa scelti con l'esperimento di taratura E5 (src/esperimenti.py).
    """
    t0 = time.perf_counter()
    rng = random.Random(seed)
    ass = {c: rng.choice(ist.domini[c]) for c in ist.clienti}
    membri = {v: set() for v in ist.veicoli}
    carico = {v: 0.0 for v in ist.veicoli}
    for c, v in ass.items():
        membri[v].add(c)
        carico[v] += ist.carico[c]

    def contributo(c: str, v: str, carico_v: float, n_membri: int) -> float:
        """Costo + penalita' legati alla presenza di c su v (con v contenente gia' gli altri membri)."""
        altri = [o for o in membri[v] if o != c]
        soft = sum(ist.d(c, o) for o in altri) + (COSTO_ATTIVAZIONE_KM if n_membri == 1 else 0.0)
        conflitti = sum(1 for o in altri if not compatibili(ist, v, c, o))
        sovraccarico = (carico_v > ist.turno_min) - (carico_v - ist.carico[c] > ist.turno_min)
        return soft + PENALITA_HARD * (conflitti + sovraccarico)

    corrente = costo_assegnamento(ist, ass) + PENALITA_HARD * violazioni_hard(ist, ass)
    migliore, migliore_ass = corrente, dict(ass)
    T = t_iniziale
    mobili = [c for c in ist.clienti if len(ist.domini[c]) > 1]
    for _ in range(iterazioni if mobili else 0):
        c = rng.choice(mobili)
        vecchio = ass[c]
        nuovo_v = rng.choice([v for v in ist.domini[c] if v != vecchio])
        # delta = (contributo di c sul nuovo veicolo) - (contributo di c sul vecchio)
        uscita = contributo(c, vecchio, carico[vecchio], len(membri[vecchio]))
        membri[nuovo_v].add(c)
        ingresso = contributo(c, nuovo_v, carico[nuovo_v] + ist.carico[c], len(membri[nuovo_v]))
        delta = ingresso - uscita
        if delta <= 0 or rng.random() < math.exp(-delta / T):
            membri[vecchio].discard(c)
            carico[vecchio] -= ist.carico[c]
            carico[nuovo_v] += ist.carico[c]
            ass[c] = nuovo_v
            corrente += delta
            if corrente < migliore - 1e-9:
                migliore, migliore_ass = corrente, dict(ass)
        else:
            membri[nuovo_v].discard(c)
        T = max(T * alfa, 1e-3)
    return Soluzione(migliore_ass, costo_assegnamento(ist, migliore_ass), ottima=False,
                     nodi=iterazioni, tempo_s=time.perf_counter() - t0,
                     violazioni=violazioni_hard(ist, migliore_ass))


def risolvi(ist: IstanzaCSP, timeout: float = CSP_TIMEOUT_SECONDS) -> Optional[Soluzione]:
    """Strategia usata in pianificazione: SA per il limite superiore, poi B&B esatto (entro il timeout)."""
    sa = simulated_annealing(ist)
    bb = branch_and_bound(ist, timeout=timeout, iniziale=sa)
    if bb is None:
        return sa if sa.violazioni == 0 else None
    bb.tempo_s += sa.tempo_s
    return bb


# ---------------------------------------------------------------------------
# Costruzione dell'istanza a partire dalla KB
# ---------------------------------------------------------------------------

def costruisci_istanza(kb, clienti: List[str], g: int, m: int, a: int,
                       coords_clienti: Dict[str, Tuple[float, float]],
                       coord_deposito: Tuple[float, float]) -> Tuple[IstanzaCSP, Dict[str, List[str]]]:
    """
    Interroga la KB per domini, finestre effettive e durate di servizio.
    Restituisce l'istanza (solo clienti con almeno un veicolo idoneo) e,
    per i clienti esclusi, i motivi spiegati dalla KB.
    """
    from src.search.a_star import haversine

    veicoli = kb.veicoli()
    ids = [v["id"] for v in veicoli]

    domini, finestre, esclusi = {}, {}, {}
    for c in clienti:
        idonei = kb.veicoli_idonei(c, g, m, a)
        if not idonei:
            esclusi[c] = sorted({mot for v in ids for mot in kb.perche_non_idoneo(v, c, g, m, a)})
            continue
        domini[c] = idonei
        for v in idonei:
            finestre[(v, c)] = kb.finestre_effettive(v, c, g, m, a)

    serviti = list(domini)
    km = {(x, y): haversine(*coords_clienti[x], *coords_clienti[y]) * FATTORE_TORTUOSITA
          for x, y in combinations(serviti, 2)}
    km_dep = {c: haversine(*coords_clienti[c], *coord_deposito) * FATTORE_TORTUOSITA for c in serviti}
    servizio = {c: kb.durata_servizio(c) for c in serviti}
    ist = IstanzaCSP(serviti, ids, domini, finestre, servizio, km, km_dep)
    return ist, esclusi
