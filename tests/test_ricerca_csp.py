"""Test di A*/LCFS e del CSP. Eseguire con: pytest tests/"""
import sys
import random
from itertools import product
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest

from src.csp.assignment import (IstanzaCSP, branch_and_bound, compatibili, costo_assegnamento,
                                gac, simulated_annealing, violazioni_hard)
from src.search.a_star import ProfiloVeicolo, a_star, carica_grafo, lcfs


@pytest.fixture(scope="module")
def grafo():
    return carica_grafo()


def test_a_star_ottimo_come_lcfs(grafo):
    adj, coords, ztl = grafo
    rng = random.Random(1)
    nodi = sorted(coords)
    for _ in range(15):
        a, b = rng.choice(nodi), rng.choice(nodi)
        ra = a_star(a, b, adj, coords, ProfiloVeicolo(), ztl)
        rl = lcfs(a, b, adj, coords, ProfiloVeicolo(), ztl)
        assert ra.percorso is not None  # grafo fortemente connesso
        assert ra.tempo_ore == pytest.approx(rl.tempo_ore)
        assert ra.nodi_espansi <= rl.nodi_espansi


def test_vincoli_di_transito(grafo):
    adj, coords, ztl = grafo
    rng = random.Random(2)
    fuori = sorted(set(coords) - ztl)
    prof = ProfiloVeicolo(vietate={"living_street"}, evita_ztl=True)
    for _ in range(10):
        a, b = rng.choice(fuori), rng.choice(fuori)
        r = a_star(a, b, adj, coords, prof, ztl)
        if r.percorso:
            assert not (set(r.percorso[1:-1]) & ztl)
            tipi = {t for x, y in zip(r.percorso, r.percorso[1:-1]) for w, _, t in adj[x] if w == y}
            assert "living_street" not in tipi


def istanza_piccola(n=6, seed=0) -> IstanzaCSP:
    rng = random.Random(seed)
    clienti = [f"c{i}" for i in range(n)]
    veicoli = ["g1", "g2", "p1"]
    pos = {c: (rng.uniform(0, 5), rng.uniform(0, 5)) for c in clienti}
    km = {(a, b): ((pos[a][0] - pos[b][0]) ** 2 + (pos[a][1] - pos[b][1]) ** 2) ** 0.5
          for i, a in enumerate(clienti) for b in clienti[i + 1:]}
    domini = {c: veicoli if i % 3 else ["p1"] for i, c in enumerate(clienti)}
    finestre = {}
    for c in clienti:
        s = rng.choice([480, 600, 720])
        for v in veicoli:
            finestre[(v, c)] = [(s, s + 120)]
    return IstanzaCSP(clienti, veicoli, domini, finestre, {c: 15 for c in clienti},
                      km, {c: 3.0 for c in clienti}, turno_min=540)


def ottimo_esaustivo(ist):
    migliore = float("inf")
    for valori in product(*(ist.domini[c] for c in ist.clienti)):
        ass = dict(zip(ist.clienti, valori))
        if violazioni_hard(ist, ass) == 0:
            migliore = min(migliore, costo_assegnamento(ist, ass))
    return migliore


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_branch_and_bound_esatto(seed):
    ist = istanza_piccola(seed=seed)
    sol = branch_and_bound(ist)
    assert sol.ottima and sol.violazioni == 0
    assert sol.costo == pytest.approx(ottimo_esaustivo(ist))


def test_gac_non_perde_soluzioni():
    ist = istanza_piccola(seed=3)
    dom, _ = gac(ist, ist.domini)
    sol = branch_and_bound(ist)
    assert all(sol.assegnamento[c] in dom[c] for c in ist.clienti)


def test_simulated_annealing_ammissibile_e_vicino():
    ist = istanza_piccola(seed=4)
    opt = branch_and_bound(ist).costo
    sa = simulated_annealing(ist, seed=0)
    assert sa.violazioni == 0
    assert sa.costo >= opt - 1e-9
    assert sa.costo <= opt * 1.2


def test_branch_and_bound_senza_gac_stesso_ottimo():
    ist = istanza_piccola(seed=6)
    assert branch_and_bound(ist, usa_gac=False).costo == pytest.approx(branch_and_bound(ist).costo)


def test_simulated_annealing_costo_incrementale_coerente():
    # con pochi passi la soluzione migliore e' spesso l'ultima accettata: il costo
    # riportato deve coincidere con quello ricalcolato da zero
    for seed in range(5):
        ist = istanza_piccola(n=8, seed=seed)
        for passi in (1, 10, 200):
            sa = simulated_annealing(ist, seed=seed, iterazioni=passi)
            assert sa.costo == pytest.approx(costo_assegnamento(ist, sa.assegnamento))
            assert sa.violazioni == violazioni_hard(ist, sa.assegnamento)


def test_compatibilita_simmetrica():
    ist = istanza_piccola(seed=5)
    for a in ist.clienti:
        for b in ist.clienti:
            if a != b:
                assert compatibili(ist, "g1", a, b) == compatibili(ist, "g1", b, a)
