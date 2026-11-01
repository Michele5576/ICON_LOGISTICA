"""
Esperimenti di valutazione dei moduli di ragionamento e ricerca.
Produce output/esperimenti.md con tabelle "media ± dev. std".

  E1  KB: dimensione, inferenze per query, vincoli d'integrita'
  E2  Ricerca su grafo: A* vs LCFS (nodi espansi, tempo, ottimalita'),
      stima empirica del fattore di tortuosita'
  E3  CSP sulle 26 giornate reali (clienti di Bari serviti quel giorno):
      Branch and Bound (con e senza limite iniziale) vs Simulated Annealing
  E4  Scalabilita' del CSP al crescere del numero di clienti
  E5  Taratura dei parametri del Simulated Annealing
  E6  Scenari: le stesse giornate pianificate come feriale / festivo / evento

Uso: python src/esperimenti.py                (richiede modelli ML gia' addestrati)
     python src/esperimenti.py --sezioni E1   (riesegue solo le sezioni indicate)
"""
import argparse
import sys
import random
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from src.config import KB_DIR, OUTPUT_DIR, RANDOM_STATE
from src.csp.assignment import branch_and_bound, costruisci_istanza, risolvi, simulated_annealing
from src.main import Pianificatore
from src.ml.data_cleaning import carica_storico_arricchito
from src.ml.previsione import prevedi
from src.search.a_star import ProfiloVeicolo, a_star, haversine, lcfs

N_SEED_SA = 5


def ms(serie) -> str:
    return f"{np.nanmean(serie):.2f} ± {np.nanstd(serie):.2f}"


def tabella(intestazione: list, righe: list) -> str:
    out = ["| " + " | ".join(intestazione) + " |", "|" + "---|" * len(intestazione)]
    out += ["| " + " | ".join(str(x) for x in r) + " |" for r in righe]
    return "\n".join(out)


# ---------------------------------------------------------------------------
def e1_kb(p: Pianificatore) -> str:
    kb = p.kb
    dim = kb.dimensione_kb()
    fatti_generati = {f: sum(1 for r in (KB_DIR / f).read_text(encoding="utf-8").splitlines()
                             if r and not r.startswith(("%", ":-")))
                      for f in ["flotta.pl", "clienti.pl", "ztl_nodi.pl", "previsioni.pl"]}
    c_ztl = kb.clienti_in_ztl()[0]
    query = {
        "tipo_giorno(data(7,5,2027), T)": "tipo_giorno(data(7,5,2027), _)",
        "veicoli_idonei(cliente ZTL, feriale)": f"veicoli_idonei({c_ztl}, data(1,7,2026), _)",
        "idoneo(V, C, feriale) per tutti V, C": "idoneo(_, _, data(1,7,2026))",
        "finestra_effettiva(V, C, evento, I, F)": "finestra_effettiva(_, _, data(7,5,2027), _, _)",
        "dimostra(idoneo(...)) (albero di prova)": f"dimostra(idoneo(v_cit_05, {c_ztl}, data(1,7,2026)), _)",
        "violazione(X) (tutti i vincoli)": "violazione(_)",
    }
    righe = [[q, kb.statistiche_query(goal)] for q, goal in query.items()]
    return "\n".join([
        "## E1. Knowledge Base", "",
        f"- knowledge_base.pl: {dim['predicati']} predicati, {dim['regole']} regole, {dim['fatti']} fatti",
        "- Fatti generati: " + ", ".join(f"{f} {n}" for f, n in fatti_generati.items()),
        f"- Violazioni dei vincoli d'integrita': {kb.violazioni() or 'nessuna'}", "",
        tabella(["Query", "Inferenze"], righe), ""])


# ---------------------------------------------------------------------------
def e2_ricerca(p: Pianificatore, n_coppie: int = 200) -> tuple[str, float]:
    adj, coords, ztl = p.grafo
    rng = random.Random(RANDOM_STATE)
    punti = [p.kb.nodo_cliente(c) for c in p.kb.clienti_servibili()] + [p.nodo_deposito]
    nodi = sorted(coords)
    coppie = [(rng.choice(punti), rng.choice(punti)) for _ in range(n_coppie // 2)]
    coppie += [(rng.choice(nodi), rng.choice(nodi)) for _ in range(n_coppie - len(coppie))]
    coppie = [(a, b) for a, b in coppie if a != b]

    profili = {"senza vincoli": ProfiloVeicolo(),
               "furgone grande (KB) + evita ZTL": ProfiloVeicolo(*p.kb.profilo_stradale("v_spr_01"), evita_ztl=True)}
    righe, rapporti = [], []
    for nome, prof in profili.items():
        stat = {"A*": ([], [], []), "LCFS": ([], [], [])}
        diversi = 0
        for a, b in coppie:
            ra_t = time.perf_counter(); ra = a_star(a, b, adj, coords, prof, ztl); ra_t = time.perf_counter() - ra_t
            rl_t = time.perf_counter(); rl = lcfs(a, b, adj, coords, prof, ztl); rl_t = time.perf_counter() - rl_t
            if ra.percorso is None:
                continue
            diversi += abs(ra.tempo_ore - rl.tempo_ore) > 1e-9
            for k, r, t in (("A*", ra, ra_t), ("LCFS", rl, rl_t)):
                stat[k][0].append(r.nodi_espansi)
                stat[k][1].append(t * 1000)
                stat[k][2].append(r.tempo_ore * 60)
            if nome == "senza vincoli":
                linea = haversine(*coords[a], *coords[b])
                if linea > 0.3:
                    rapporti.append(ra.distanza_km / linea)
        for k in ("A*", "LCFS"):
            righe.append([nome, k, ms(stat[k][0]), ms(stat[k][1]), ms(stat[k][2])])
        righe.append([nome, "costi diversi A*/LCFS", diversi, "", ""])
        ratio = np.mean(stat["A*"][0]) / np.mean(stat["LCFS"][0])
        righe.append([nome, "nodi A* / nodi LCFS", f"{ratio:.2f}", "", ""])
    tort = float(np.median(rapporti))
    testo = "\n".join([
        "## E2. Ricerca su grafo: A* vs LCFS", "",
        f"{len(coppie)} coppie origine-destinazione (meta' tra clienti/deposito, meta' casuali).", "",
        tabella(["Profilo", "Algoritmo", "Nodi espansi", "Tempo (ms)", "Costo (min)"], righe), "",
        f"Fattore di tortuosita' (distanza stradale / linea d'aria, coppie > 300 m): mediana {tort:.2f}, "
        f"media {np.mean(rapporti):.2f} ± {np.std(rapporti):.2f} su {len(rapporti)} coppie.", ""])
    return testo, tort


# ---------------------------------------------------------------------------
def giornate_storiche(p: Pianificatore) -> list:
    storico = carica_storico_arricchito()
    serviti = set(p.kb.clienti_servibili())
    out = []
    for data, df in storico.groupby("Data"):
        codici = sorted({c for c in df["Codice_Cliente"] if f"c_{c}" in serviti})
        if codici:
            out.append((data, codici))
    return out


def e3_csp(p: Pianificatore, giornate: list, timeout: float = 10.0) -> str:
    puro, misto, sa_r, gap = [], [], [], []
    for data, codici in giornate:
        scarico, pm = prevedi(codici, data)
        p.kb.carica_previsioni(scarico, pm)
        ist, _ = costruisci_istanza(p.kb, [f"c_{c}" for c in codici], data.day, data.month, data.year,
                                    p.coords_clienti, p.coord_deposito)
        bb = branch_and_bound(ist, timeout=timeout)
        sas = [simulated_annealing(ist, seed=s) for s in range(N_SEED_SA)]
        bb_sa = branch_and_bound(ist, timeout=timeout, iniziale=sas[0])
        if bb is None:  # nessuna soluzione completa trovata entro il timeout
            puro.append((len(ist.clienti), np.nan, np.nan, timeout, False, 0))
            riferimento = bb_sa.costo
        else:
            puro.append((len(ist.clienti), bb.costo, bb.nodi, bb.tempo_s, bb.ottima, bb.valori_rimossi_gac))
            riferimento = min(bb.costo, bb_sa.costo)
        misto.append((bb_sa.costo, bb_sa.nodi, bb_sa.tempo_s + sas[0].tempo_s, bb_sa.ottima))
        for s in sas:
            sa_r.append((s.costo, s.tempo_s, s.violazioni == 0))
            gap.append(100 * (s.costo - riferimento) / riferimento)
    bb, mi, sa = (np.array(x, dtype=float) for x in (puro, misto, sa_r))
    righe = [
        ["B&B (GAC)", ms(bb[:, 1]), ms(bb[:, 2]), ms(bb[:, 3]), f"{int(bb[:, 4].sum())}/{len(bb)} chiusi"],
        ["B&B (GAC) + limite iniziale da SA", ms(mi[:, 0]), ms(mi[:, 1]), ms(mi[:, 2]),
         f"{int(mi[:, 3].sum())}/{len(mi)} chiusi"],
        [f"Simulated Annealing ({N_SEED_SA} seed)", ms(sa[:, 0]), "20000 mosse", ms(sa[:, 1]),
         f"{int(sa[:, 2].sum())}/{len(sa)} ammissibili; gap {ms(gap)} %"],
    ]
    return "\n".join([
        "## E3. CSP sulle giornate reali", "",
        f"{len(giornate)} giornate dello storico; clienti di Bari per giornata: {ms(bb[:, 0])} "
        f"(min {int(bb[:, 0].min())}, max {int(bb[:, 0].max())}). Timeout B&B {timeout:.0f} s: "
        "'chiuso' = ricerca completata, quindi soluzione ottima dimostrata.",
        f"Valori rimossi da GAC prima della ricerca: {ms(bb[:, 5])}.", "",
        tabella(["Algoritmo", "Costo", "Nodi", "Tempo (s)", "Esito"], righe), ""])


def e4_scalabilita(p: Pianificatore, data=pd.Timestamp("2026-07-01"), timeout: float = 10.0) -> str:
    tutti = [c[2:] for c in p.kb.clienti_servibili()]
    scarico, pm = prevedi(tutti, data)
    p.kb.carica_previsioni(scarico, pm)
    rng = random.Random(RANDOM_STATE)
    righe = []
    for n in (8, 12, 16, 20, 25, 33):
        res = []
        for k in range(5 if n < 33 else 1):
            codici = rng.sample(tutti, n)
            ist, _ = costruisci_istanza(p.kb, [f"c_{c}" for c in codici], data.day, data.month, data.year,
                                        p.coords_clienti, p.coord_deposito)
            sas = [simulated_annealing(ist, seed=s) for s in range(3)]
            bb = branch_and_bound(ist, timeout=timeout, iniziale=sas[0])
            res.append((bb.tempo_s, bb.nodi, bb.ottima, bb.costo,
                        np.mean([s.costo for s in sas]), np.mean([s.tempo_s for s in sas])))
        r = np.array(res, dtype=float)
        delta = 100 * (r[:, 4] - r[:, 3]) / r[:, 3]
        righe.append([n, len(r), ms(r[:, 0]), ms(r[:, 1]), f"{int(r[:, 2].sum())}/{len(r)}",
                      ms(r[:, 5]), ms(delta)])
    return "\n".join([
        "## E4. Scalabilita' del CSP", "",
        f"Sottoinsiemi casuali dei 33 clienti di Bari, data feriale; B&B con limite iniziale da SA, "
        f"timeout {timeout:.0f} s.", "",
        tabella(["Clienti", "Istanze", "B&B tempo (s)", "B&B nodi", "B&B chiusi", "SA tempo (s)",
                 "SA (media 3 seed) - B&B, costo (%)"], righe), ""])


def e5_taratura_sa(p: Pianificatore, giornate: list) -> str:
    campione = giornate[::5]
    istanze = []
    for data, codici in campione:
        scarico, pm = prevedi(codici, data)
        p.kb.carica_previsioni(scarico, pm)
        ist, _ = costruisci_istanza(p.kb, [f"c_{c}" for c in codici], data.day, data.month, data.year,
                                    p.coords_clienti, p.coord_deposito)
        bb = branch_and_bound(ist, timeout=10.0, iniziale=simulated_annealing(ist, iterazioni=50000))
        istanze.append((ist, bb.costo, bb.ottima))
    righe = []
    for t0 in (5.0, 50.0, 500.0):
        for alfa in (0.999, 0.9995, 0.9999):
            gaps = [100 * (simulated_annealing(ist, seed=s, t_iniziale=t0, alfa=alfa).costo - rif) / rif
                    for ist, rif, _ in istanze for s in range(3)]
            righe.append([t0, alfa, ms(gaps), sum(g < 1e-6 for g in gaps), len(gaps)])
    chiusi = sum(1 for _, _, ottima in istanze if ottima)
    return "\n".join([
        "## E5. Taratura del Simulated Annealing", "",
        f"{len(istanze)} giornate x 3 seed, 20000 mosse; gap dal costo di riferimento del B&B "
        f"(ottimo dimostrato in {chiusi}/{len(istanze)} giornate).", "",
        tabella(["T iniziale", "alfa", "Gap (%)", "Volte al riferimento", "Prove"], righe), ""])


def e6_scenari(p: Pianificatore, giornate: list) -> str:
    date = {"reale (data storica)": None, "festivo (domenica)": pd.Timestamp("2026-07-05"),
            "evento (7 maggio)": pd.Timestamp("2027-05-07")}
    righe = []
    for nome, d_fissa in date.items():
        metriche = {k: [] for k in ("esclusi", "veicoli_usati", "km", "ritardi", "fuori_turno", "transiti_ztl")}
        for data, codici in giornate:
            d = data if d_fissa is None else d_fissa
            scarico, pm = prevedi(codici, data)  # previsioni con lo storico disponibile in quella giornata
            p.kb.carica_previsioni(scarico, pm)
            r = p.pianifica(d, codici, previsioni=False,
                            risolutore=lambda ist: risolvi(ist, timeout=5.0))
            r["esclusi"] = len(r["esclusi"])
            for k in metriche:
                metriche[k].append(r[k])
        righe.append([nome] + [ms(v) for v in metriche.values()])
    return "\n".join([
        "## E6. Scenari sulle giornate reali", "",
        "Gli ordini di ciascuna delle giornate storiche sono ripianificati come se cadessero in date diverse.", "",
        tabella(["Scenario", "Clienti non servibili", "Veicoli usati", "km totali (A*)",
                 "Consegne in ritardo", "Giri oltre turno", "Transiti ZTL obbligati"], righe), ""])


def aggiorna_sezione(testo_file: str, nome: str, nuova: str) -> str:
    """Sostituisce nel report la sezione '## <nome>.' (fino alla sezione successiva)."""
    inizio = testo_file.index(f"## {nome}.")
    fine = testo_file.find("\n## ", inizio + 1)
    if fine == -1:
        fine = testo_file.find("\nTempo totale", inizio)
    return testo_file[:inizio] + nuova.rstrip("\n") + "\n" + testo_file[fine:]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sezioni", nargs="*", help="esegue solo queste sezioni (es. E1 E2) "
                                                    "e le sostituisce in output/esperimenti.md")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    report = OUTPUT_DIR / "esperimenti.md"
    t0 = time.time()
    p = Pianificatore()
    giornate = giornate_storiche(p)
    esperimenti = [("E1", lambda: e1_kb(p)), ("E2", lambda: e2_ricerca(p)[0]),
                   ("E3", lambda: e3_csp(p, giornate)), ("E4", lambda: e4_scalabilita(p)),
                   ("E5", lambda: e5_taratura_sa(p, giornate)), ("E6", lambda: e6_scenari(p, giornate))]

    if args.sezioni:
        testo = report.read_text(encoding="utf-8")
        for nome, fn in esperimenti:
            if nome in args.sezioni:
                print(f"[INFO] {nome}...", flush=True)
                testo = aggiorna_sezione(testo, nome, fn())
        report.write_text(testo, encoding="utf-8")
        print(f"[OK] Sezioni {' '.join(args.sezioni)} aggiornate in {report}")
        return

    sezioni = ["# Esperimenti", ""]
    for nome, fn in esperimenti:
        print(f"[INFO] {nome}...", flush=True)
        testo = fn()
        print(testo, flush=True)
        sezioni.append(testo)
        report.write_text("\n".join(sezioni) + "\n", encoding="utf-8")
    sezioni.append(f"Tempo totale: {time.time() - t0:.0f} s")
    report.write_text("\n".join(sezioni) + "\n", encoding="utf-8")
    print(f"[OK] Risultati in {report}")


if __name__ == "__main__":
    main()
