"""
main.py — Orchestratore end-to-end
Logistica Flotta Furgoni Bari

Pipeline per una data di pianificazione:
  1. KB      tipo di giorno, veicoli idonei, finestre effettive, motivi di esclusione
  2. ML      durata del servizio e rischio di mancata consegna -> fatti nella KB
  3. CSP     assegnamento clienti -> veicoli (GAC + Branch and Bound, limite iniziale da Simulated Annealing)
  4. Ricerca ordine di visita (DF Branch and Bound) e percorsi con A*

Uso:
  python src/main.py                       # confronto feriale / festivo / evento
  python src/main.py --data 2026-07-01     # pianificazione di una singola data
"""
import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd

from src.config import (DEPOSITO_LAT, DEPOSITO_LON, INIZIO_TURNO_MIN, OUTPUT_DIR,
                        POSIZIONI_CLIENTI_CSV, TURNO_MIN)
from src.csp.assignment import costruisci_istanza, risolvi
from src.kb_interface.prolog_interface import KnowledgeBase
from src.ml.previsione import prevedi
from src.search.a_star import ProfiloVeicolo, carica_grafo, trova_nodo_vicino
from src.search.routing import ordina_visite, simula_giro

SCENARI = {
    "feriale": pd.Timestamp("2026-07-01"),   # mercoledi'
    "festivo": pd.Timestamp("2026-07-05"),   # domenica
    "evento": pd.Timestamp("2027-05-07"),    # corteo storico di San Nicola
}
FINE_TURNO_MIN = INIZIO_TURNO_MIN + TURNO_MIN


def hhmm(minuti: float) -> str:
    m = int(round(minuti))
    return f"{m // 60:02d}:{m % 60:02d}"


class Pianificatore:
    """Mantiene caricati KB e grafo tra una pianificazione e l'altra."""

    def __init__(self):
        self.kb = KnowledgeBase()
        self.grafo = carica_grafo()
        _, coords, _ = self.grafo
        pos = pd.read_csv(POSIZIONI_CLIENTI_CSV, dtype={"Codice_Cliente": str})
        self.coords_clienti = {f"c_{r.Codice_Cliente}": (r.lat, r.lon) for r in pos.itertuples()}
        self.nodo_deposito = trova_nodo_vicino(DEPOSITO_LAT, DEPOSITO_LON, coords)
        self.coord_deposito = coords[self.nodo_deposito]
        self.profili = {}
        for v in self.kb.veicoli():
            vel, vietate = self.kb.profilo_stradale(v["id"])
            self.profili[v["id"]] = ProfiloVeicolo(vel, vietate)

    def pianifica(self, data: pd.Timestamp, codici: list, previsioni: bool = True,
                  risolutore=risolvi) -> dict:
        t0 = time.perf_counter()
        kb = self.kb
        g, m, a = data.day, data.month, data.year
        clienti = [f"c_{c}" for c in codici]

        # 2. ML -> KB
        if previsioni:
            scarico, p_manc = prevedi(codici, data)
            kb.carica_previsioni(scarico, p_manc)

        # 1 + 3. KB -> CSP
        ist, esclusi = costruisci_istanza(kb, clienti, g, m, a, self.coords_clienti, self.coord_deposito)
        sol = risolutore(ist) if ist.clienti else None
        if sol is None:
            return {"data": data, "tipo_giorno": kb.tipo_giorno(g, m, a), "esclusi": esclusi,
                    "soluzione": None, "giri": [], "istanza": ist, "km": 0.0, "ritardi": 0,
                    "veicoli_usati": 0, "rientro_max": None, "fuori_turno": 0, "transiti_ztl": 0,
                    "preavvisi": [], "tempo_s": time.perf_counter() - t0}

        # 4. ricerca: ordine di visita + A*
        per_veicolo = {}
        for c, v in sol.assegnamento.items():
            per_veicolo.setdefault(v, []).append(c)
        giri = []
        for v, lista in sorted(per_veicolo.items()):
            fin = {c: ist.finestre[(v, c)][0] for c in lista}
            seq = ordina_visite(lista, fin, ist.servizio, self.coords_clienti, self.coord_deposito)
            nodi = {c: kb.nodo_cliente(c) for c in lista}
            giri.append(simula_giro(v, seq, kb, (g, m, a), fin, ist.servizio, nodi,
                                    self.nodo_deposito, self.grafo, self.profili[v]))

        ris = {"data": data, "tipo_giorno": kb.tipo_giorno(g, m, a), "esclusi": esclusi,
               "soluzione": sol, "giri": giri, "istanza": ist,
               "km": sum(gi.km_totali for gi in giri),
               "ritardi": sum(gi.ritardi for gi in giri),
               "veicoli_usati": len(giri),
               "rientro_max": max(gi.rientro_min for gi in giri),
               "fuori_turno": sum(1 for gi in giri if gi.rientro_min > FINE_TURNO_MIN),
               "transiti_ztl": sum(gi.transiti_ztl for gi in giri),
               "preavvisi": [c for c in ist.clienti if kb.richiede_preavviso(c)],
               "tempo_s": time.perf_counter() - t0}
        return ris


def stampa_piano(r: dict) -> str:
    sol = r["soluzione"]
    righe = [f"Data {r['data'].date()} ({r['tipo_giorno']})",
             f"  CSP: costo {sol.costo:.1f}, ottimo={sol.ottima}, nodi {sol.nodi}, "
             f"valori rimossi da GAC {sol.valori_rimossi_gac}, {sol.tempo_s:.2f} s"]
    for c, motivi in r["esclusi"].items():
        righe.append(f"  NON SERVIBILE {c}: {', '.join(motivi)}")
    for gi in r["giri"]:
        transiti = f", transiti obbligati in ZTL {gi.transiti_ztl}" if gi.transiti_ztl else ""
        righe.append(f"  {gi.veicolo}: {len(gi.tappe)} clienti, {gi.km_totali:.1f} km, "
                     f"partenza {hhmm(gi.partenza_min)}, rientro {hhmm(gi.rientro_min)}, "
                     f"ritardi {gi.ritardi}{transiti}")
        for t in gi.tappe:
            nota = f" RITARDO {t.ritardo_min:.0f} min" if t.ritardo_min > 0 else ""
            righe.append(f"     arrivo {hhmm(t.arrivo_min)}  servizio {hhmm(t.inizio_servizio_min)}  "
                         f"{t.cliente}{nota}")
    if r["preavvisi"]:
        righe.append(f"  Da preavvisare (rischio mancata consegna): {', '.join(r['preavvisi'])}")
    testo = "\n".join(righe)
    print(testo)
    return testo


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", help="data di pianificazione AAAA-MM-GG")
    args = parser.parse_args()

    p = Pianificatore()
    print(f"Violazioni d'integrita' della KB: {p.kb.violazioni() or 'nessuna'}")
    codici = [c[2:] for c in p.kb.clienti_servibili()]
    scenari = {"richiesta": pd.Timestamp(args.data)} if args.data else SCENARI

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    testo, riepilogo = [], []
    for nome, data in scenari.items():
        print(f"\n{'=' * 60}\nSCENARIO {nome.upper()}\n{'=' * 60}")
        r = p.pianifica(data, codici)
        if r["soluzione"] is None:
            print("  Nessun assegnamento possibile")
            continue
        testo.append(f"SCENARIO {nome}\n" + stampa_piano(r))
        riepilogo.append(f"| {nome} | {r['tipo_giorno']} | {len(r['istanza'].clienti)}/{len(codici)} | "
                         f"{r['veicoli_usati']} | {r['km']:.1f} | {r['ritardi']} | {hhmm(r['rientro_max'])} | "
                         f"{r['fuori_turno']} | {r['transiti_ztl']} |")

    tabella = ["| Scenario | Tipo giorno | Clienti serviti | Veicoli | km | Ritardi | Ultimo rientro | "
               "Giri oltre turno | Transiti ZTL obbligati |",
               "|---|---|---|---|---|---|---|---|---|"] + riepilogo
    print("\n" + "\n".join(tabella))
    file_out = OUTPUT_DIR / (f"piano_{args.data}.txt" if args.data else "piani_scenari.txt")
    file_out.write_text("\n\n".join(testo) + "\n\n" + "\n".join(tabella) + "\n", encoding="utf-8")
    print(f"\n[OK] Piani salvati in {file_out}")


if __name__ == "__main__":
    main()
