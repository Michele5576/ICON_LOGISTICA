"""Test di integrazione della pipeline KB -> ML -> CSP -> ricerca. Eseguire con: pytest tests/"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd
import pytest

from src.config import INIZIO_TURNO_MIN
from src.main import FINE_TURNO_MIN, Pianificatore

GIORNO = pd.Timestamp("2026-06-15")


@pytest.fixture(scope="module")
def pianificatore():
    return Pianificatore()


@pytest.fixture(scope="module")
def clienti(pianificatore):
    return [c[2:] for c in pianificatore.kb.clienti_servibili()][:12]


def test_piano_rispetta_kb(pianificatore, clienti):
    kb = pianificatore.kb
    r = pianificatore.pianifica(GIORNO, clienti)
    sol = r["soluzione"]
    assert sol is not None and sol.violazioni == 0
    assert set(sol.assegnamento) | set(r["esclusi"]) == {f"c_{c}" for c in clienti}
    for c, v in sol.assegnamento.items():
        assert v in kb.veicoli_idonei(c, GIORNO.day, GIORNO.month, GIORNO.year)
    visitati = [t.cliente for g in r["giri"] for t in g.tappe]
    assert sorted(visitati) == sorted(sol.assegnamento)          # ogni cliente servito una volta
    for g in r["giri"]:
        assert g.partenza_min >= INIZIO_TURNO_MIN
        assert g.tappe[0].arrivo_min > g.partenza_min
        for t in g.tappe:
            assert t.inizio_servizio_min >= t.arrivo_min
            fin = r["istanza"].finestre[(g.veicolo, t.cliente)][0]
            assert t.inizio_servizio_min >= fin[0]               # nessun servizio prima della finestra
        assert g.rientro_min > g.tappe[-1].inizio_servizio_min
    assert r["fuori_turno"] == sum(1 for g in r["giri"] if g.rientro_min > FINE_TURNO_MIN)


def test_evento_esclude_clienti_ztl(pianificatore):
    kb = pianificatore.kb
    ztl = [c[2:] for c in kb.clienti_in_ztl()]
    r = pianificatore.pianifica(pd.Timestamp("2027-05-07"), ztl)
    for c, motivi in r["esclusi"].items():
        assert set(motivi) <= {"ztl_senza_permesso", "permesso_sospeso_per_evento"}
    if r["soluzione"]:
        for c in r["soluzione"].assegnamento:
            assert r["soluzione"].assegnamento[c] == "v_cit_05"     # solo il mezzo con permesso
