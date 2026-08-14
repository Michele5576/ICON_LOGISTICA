"""
main.py — Orchestratore End-to-End
Logistica Flotta Furgoni Bari

Pipeline: KB -> ML -> CSP -> A* -> Piano di Consegna
Confronto: Giorno feriale vs Corteo San Nicola
"""

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import (
    setup_swipl_env, DEPOSITO_LAT, DEPOSITO_LON,
    PENALITA_PROFILO, OUTPUT_DIR
)

# Setup SWI-Prolog PRIMA di importare moduli che usano janus
setup_swipl_env()

from src.kb_interface.prolog_interface import KnowledgeBase
from src.ml.model_training import carica_modello
from src.ml.data_cleaning import prepara_dataset_ml
from src.csp.assignment import risolvi_assegnamento, predici_profili_clienti
from src.search.a_star import carica_grafo, a_star, trova_nodo_vicino


def esegui_scenario(nome: str, ora: int, minuto: int,
                    giorno: int, mese: int) -> dict:
    """Esegue un intero scenario di consegna.

    Args:
        nome: Nome descrittivo dello scenario
        ora, minuto, giorno, mese: parametri temporali

    Returns:
        dict con risultati: assegnamento, percorsi, statistiche
    """
    print(f"\n{'='*60}")
    print(f"  SCENARIO: {nome}")
    print(f"  Orario: {ora}:{minuto:02d}, Data: {giorno}/{mese}")
    print(f"{'='*60}")

    t0 = time.time()

    # 1. Inizializza KB
    print("\n[FASE 1] Inizializzazione Knowledge Base...")
    kb = KnowledgeBase()
    clienti_kb = kb.get_clienti()
    furgoni_kb = kb.get_furgoni()
    clienti_ztl = kb.clienti_in_ztl()
    print(f"  Furgoni: {len(furgoni_kb)}")
    print(f"  Clienti: {len(clienti_kb)}")
    print(f"  Clienti in ZTL: {len(clienti_ztl)}")

    # 2. Predizione profili ML
    print("\n[FASE 2] Predizione profili comportamentali (ML)...")
    codici_clienti = [c["codice"] for c in clienti_kb]
    profili = predici_profili_clienti(codici_clienti)
    conteggio_profili = {}
    for p in profili.values():
        conteggio_profili[p] = conteggio_profili.get(p, 0) + 1
    print(f"  Distribuzione: {conteggio_profili}")

    # 3. Assegnamento CSP
    print("\n[FASE 3] Assegnamento clienti-veicoli (CSP)...")
    assegnamento = risolvi_assegnamento(
        codici_clienti, ora, minuto, giorno, mese, profili, kb=kb
    )
    if not assegnamento:
        print("[ERROR] CSP non ha trovato soluzione!")
        return {"errore": "CSP fallito"}

    tot_assegnati = sum(len(v) for v in assegnamento.values())
    print(f"  Clienti assegnati: {tot_assegnati}/{len(codici_clienti)}")
    for veicolo, clienti_list in assegnamento.items():
        print(f"    {veicolo}: {len(clienti_list)} clienti")

    # 4. Routing A*
    print("\n[FASE 4] Calcolo percorsi (A*)...")
    adj, coords, ztl_set = carica_grafo()
    deposito_nodo = trova_nodo_vicino(DEPOSITO_LAT, DEPOSITO_LON, coords)
    print(f"  Nodo deposito: {deposito_nodo}")

    # Per ciascun veicolo, calcola la distanza totale
    percorsi = {}
    distanza_totale = 0.0
    tempo_totale = 0.0
    nodi_irraggiungibili = 0

    for veicolo, clienti_list in assegnamento.items():
        # Il veicolo ha permesso ZTL?
        ha_permesso = kb.ha_permesso_ztl(veicolo)
        evita = not ha_permesso  # se non ha permesso, evita ZTL

        percorso_veicolo = []
        dist_veicolo = 0.0
        tempo_veicolo = 0.0
        nodo_corrente = deposito_nodo

        # Trova i nodi dei clienti
        nodi_clienti = []
        for c in clienti_list:
            nodo_c = kb.nodo_cliente(c)
            if nodo_c:
                nodi_clienti.append((c, nodo_c))

        # Routing sequenziale: deposito -> c1 -> c2 -> ... -> deposito
        for cliente_cod, nodo_dest in nodi_clienti:
            path, dist, tempo = a_star(
                nodo_corrente, nodo_dest, adj, coords, evita, ztl_set
            )
            if path is not None:
                percorso_veicolo.append({
                    "da": nodo_corrente, "a": nodo_dest,
                    "cliente": cliente_cod,
                    "distanza_km": round(dist, 3),
                    "tempo_ore": round(tempo, 4),
                    "nodi": len(path)
                })
                dist_veicolo += dist
                tempo_veicolo += tempo
                nodo_corrente = nodo_dest
            else:
                nodi_irraggiungibili += 1
                percorso_veicolo.append({
                    "da": nodo_corrente, "a": nodo_dest,
                    "cliente": cliente_cod,
                    "distanza_km": float("inf"),
                    "tempo_ore": float("inf"),
                    "nodi": 0
                })

        # Ritorno al deposito
        path_ritorno, dist_r, tempo_r = a_star(
            nodo_corrente, deposito_nodo, adj, coords, evita, ztl_set
        )
        if path_ritorno:
            dist_veicolo += dist_r
            tempo_veicolo += tempo_r

        percorsi[veicolo] = {
            "segmenti": percorso_veicolo,
            "distanza_totale_km": round(dist_veicolo, 3),
            "tempo_totale_ore": round(tempo_veicolo, 4),
            "evita_ztl": evita
        }
        distanza_totale += dist_veicolo
        tempo_totale += tempo_veicolo

    t_elapsed = time.time() - t0

    # 5. Riepilogo
    print(f"\n{'='*60}")
    print(f"  RIEPILOGO: {nome}")
    print(f"{'='*60}")
    print(f"  Distanza totale flotta: {distanza_totale:.2f} km")
    print(f"  Tempo totale flotta: {tempo_totale:.2f} ore ({tempo_totale*60:.1f} min)")
    print(f"  Clienti irraggiungibili: {nodi_irraggiungibili}")
    print(f"  Tempo di calcolo: {t_elapsed:.1f} secondi")

    for veicolo, info in percorsi.items():
        ztl_label = "(evita ZTL)" if info["evita_ztl"] else "(accesso ZTL)"
        n_clienti = len(assegnamento[veicolo])
        print(f"    {veicolo} {ztl_label}: {n_clienti} clienti, "
              f"{info['distanza_totale_km']:.2f} km, "
              f"{info['tempo_totale_ore']*60:.1f} min")

    return {
        "nome": nome,
        "assegnamento": assegnamento,
        "percorsi": percorsi,
        "distanza_totale_km": round(distanza_totale, 3),
        "tempo_totale_ore": round(tempo_totale, 4),
        "clienti_irraggiungibili": nodi_irraggiungibili,
        "tempo_calcolo_s": round(t_elapsed, 1),
        "profili": profili,
        "clienti_ztl": clienti_ztl
    }


def salva_report(risultati: list[dict]) -> None:
    """Salva il report di confronto scenari."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / "report_confronto.txt"

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("REPORT CONFRONTO SCENARI\n")
        f.write("=" * 60 + "\n\n")

        for r in risultati:
            f.write(f"Scenario: {r['nome']}\n")
            f.write(f"  Distanza totale: {r['distanza_totale_km']:.2f} km\n")
            f.write(f"  Tempo totale: {r['tempo_totale_ore']:.2f} ore "
                    f"({r['tempo_totale_ore']*60:.1f} min)\n")
            f.write(f"  Clienti irraggiungibili: {r['clienti_irraggiungibili']}\n")
            f.write(f"  Tempo di calcolo: {r['tempo_calcolo_s']:.1f} s\n")
            f.write(f"  Clienti in ZTL: {len(r.get('clienti_ztl', []))}\n\n")

            for veicolo, info in r["percorsi"].items():
                ztl_label = "(evita ZTL)" if info["evita_ztl"] else "(accesso ZTL)"
                n_clienti = len(r["assegnamento"][veicolo])
                f.write(f"    {veicolo} {ztl_label}: {n_clienti} clienti, "
                        f"{info['distanza_totale_km']:.2f} km, "
                        f"{info['tempo_totale_ore']*60:.1f} min\n")
            f.write("\n" + "-" * 60 + "\n\n")

        # Confronto
        if len(risultati) >= 2:
            r_feriale = risultati[0]
            r_sn = risultati[1]
            f.write("CONFRONTO\n")
            f.write(f"  Distanza feriale: {r_feriale['distanza_totale_km']:.2f} km\n")
            f.write(f"  Distanza San Nicola: {r_sn['distanza_totale_km']:.2f} km\n")
            delta_d = r_sn["distanza_totale_km"] - r_feriale["distanza_totale_km"]
            f.write(f"  Delta distanza: {delta_d:+.2f} km\n")
            delta_t = (r_sn["tempo_totale_ore"] - r_feriale["tempo_totale_ore"]) * 60
            f.write(f"  Delta tempo: {delta_t:+.1f} min\n")

    print(f"\n[OK] Report salvato in {output_path}")


if __name__ == "__main__":
    print("=" * 60)
    print("  LOGISTICA FLOTTA FURGONI BARI")
    print("  Pipeline: KB -> ML -> CSP -> A*")
    print("=" * 60)

    risultati = []

    # Scenario 1: Giorno feriale (15 giugno, ore 10:00)
    r1 = esegui_scenario("Giorno Feriale (15 Giugno, 10:00)", 10, 0, 15, 6)
    risultati.append(r1)

    # Scenario 2: Corteo San Nicola (7 maggio, ore 10:00)
    r2 = esegui_scenario("Corteo San Nicola (7 Maggio, 10:00)", 10, 0, 7, 5)
    risultati.append(r2)

    # Salva report di confronto
    salva_report(risultati)

    print("\n[OK] Esecuzione completata con successo!")
