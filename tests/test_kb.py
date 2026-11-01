"""Test della Knowledge Base Prolog (via PySwip). Eseguire con: pytest tests/"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest

from src.config import INIZIO_TURNO_MIN, TURNO_MIN
from src.kb_interface.prolog_interface import KnowledgeBase

FERIALE = (1, 7, 2026)     # mercoledi'
FESTIVO = (2, 6, 2026)     # Festa della Repubblica
DOMENICA = (5, 7, 2026)
EVENTO = (7, 5, 2027)      # corteo storico di San Nicola


@pytest.fixture(scope="module")
def kb():
    return KnowledgeBase()


@pytest.fixture(scope="module")
def cliente_ztl(kb):
    return kb.clienti_in_ztl()[0]


def test_integrita(kb):
    assert kb.violazioni() == []


def test_classificazione_e_ereditarieta(kb):
    classi = {v["id"]: v["classe"] for v in kb.veicoli()}
    assert classi["v_cit_05"] == "furgone_compatto"
    assert all(classi[f"v_spr_0{i}"] == "furgone_grande" for i in range(1, 5))
    # is_a ricorsiva: un furgone e' anche un veicolo commerciale e un veicolo
    assert kb._vera("istanza(v_spr_01, veicolo_commerciale)")
    assert kb._vera("istanza(v_spr_01, veicolo)")
    assert not kb._vera("istanza(v_spr_01, furgone_compatto)")


def test_permesso_derivato(kb):
    assert kb._vera("permesso_ztl(v_cit_05)")
    assert not kb._vera("permesso_ztl(v_spr_01)")


def test_default_ed_eccezioni_velocita(kb):
    vel_grande, vietate_grande = kb.profilo_stradale("v_spr_01")
    vel_compatto, vietate_compatto = kb.profilo_stradale("v_cit_05")
    assert vel_compatto["residential"] == 30 and vel_grande["residential"] == 25  # eccezione
    assert vel_compatto["primary"] == vel_grande["primary"] == 50                 # default
    assert vietate_grande == {"living_street"} and vietate_compatto == set()


def test_tipo_giorno_con_priorita(kb):
    assert kb.tipo_giorno(*FERIALE) == "feriale"
    assert kb.tipo_giorno(*FESTIVO) == "festivo"
    assert kb.tipo_giorno(*DOMENICA) == "festivo"
    assert kb.tipo_giorno(*EVENTO) == "evento"   # l'evento prevale anche se cade di domenica/festivo


def test_accesso_ztl(kb):
    assert not kb.accesso_ztl("v_spr_01", *FERIALE, 600)   # 10:00, ZTL attiva, senza permesso
    assert kb.accesso_ztl("v_spr_01", *FERIALE, 1260)      # 21:00, ZTL non attiva
    assert kb.accesso_ztl("v_cit_05", *FERIALE, 600)       # con permesso
    assert kb.accesso_ztl("v_cit_05", *EVENTO, 480)        # evento, fascia carico/scarico
    assert not kb.accesso_ztl("v_cit_05", *EVENTO, 700)    # evento, permesso sospeso


def test_finestre_effettive(kb, cliente_ztl):
    i, f = kb._tutte(f"finestra({cliente_ztl}, I, F)")[0].values()
    for v in ("v_cit_05", "v_spr_01"):
        for a, b in kb.finestre_effettive(v, cliente_ztl, *FERIALE):
            assert max(i, INIZIO_TURNO_MIN) <= a < b <= min(f, INIZIO_TURNO_MIN + TURNO_MIN)


def test_idoneita_e_spiegazioni(kb, cliente_ztl):
    assert "v_cit_05" in kb.veicoli_idonei(cliente_ztl, *FERIALE)
    assert "v_spr_01" not in kb.veicoli_idonei(cliente_ztl, *FERIALE)
    assert "ztl_senza_permesso" in kb.perche_non_idoneo("v_spr_01", cliente_ztl, *FERIALE)
    if not kb.veicoli_idonei(cliente_ztl, *EVENTO):
        assert "permesso_sospeso_per_evento" in kb.perche_non_idoneo("v_cit_05", cliente_ztl, *EVENTO)
    albero = kb.spiega(f"idoneo(v_cit_05, {cliente_ztl}, data(1, 7, 2026))")
    assert "permesso_ztl(v_cit_05)" in albero and "tipo_giorno" in albero


def test_motivo_finestra_fuori_turno(kb):
    # cliente fittizio in ZTL con finestra serale: nessun veicolo lo puo' servire
    nodo_ztl = kb._tutte("in_ztl(N)")[0]["N"]
    fatti = [f"ubicazione(c_test, {nodo_ztl})", "finestra(c_test, 1080, 1200)", "cliente(c_test, bari, bari_citta)"]
    for f in fatti:
        kb._prolog.assertz(f)
    try:
        assert kb.veicoli_idonei("c_test", *FERIALE) == []
        for v in ("v_cit_05", "v_spr_01"):
            assert kb.perche_non_idoneo(v, "c_test", *FERIALE) == ["finestra_fuori_turno"]
    finally:
        for f in fatti:
            kb._tutte(f"retract({f})")


def test_turno_coerente_con_config(kb):
    r = kb._tutte("turno_lavoro(I, F)")[0]
    assert (r["I"], r["F"] - r["I"]) == (INIZIO_TURNO_MIN, TURNO_MIN)


def test_previsioni_ml_nella_kb(kb):
    c = kb.clienti_servibili()[0]
    kb.carica_previsioni({c: 27}, {c: 0.8})
    assert kb.durata_servizio(c) == 27
    assert kb.richiede_preavviso(c)
    kb.carica_previsioni({}, {c: 0.1})
    assert kb.durata_servizio(c) == 10       # default in assenza di previsione
    assert not kb.richiede_preavviso(c)


def test_vincolo_integrita_rileva_errori(kb):
    kb._prolog.assertz("prob_mancata(c_test, 1.5)")
    try:
        assert "probabilita_non_valida(c_test)" in kb.violazioni()
    finally:
        kb._tutte("retract(prob_mancata(c_test, 1.5))")
