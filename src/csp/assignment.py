"""
Modulo per l'assegnamento dei clienti ai veicoli tramite CSP (OR-Tools CP-SAT).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import json
import math
from typing import Dict, List, Optional
from ortools.sat.python import cp_model

from src.config import (
    setup_swipl_env,
    DEPOSITO_LAT,
    DEPOSITO_LON,
    GEOCODING_CACHE,
    PENALITA_PROFILO,
    CSP_TIMEOUT_SECONDS,
    MAX_CLIENTI_PER_VEICOLO,
    PESO_MEDIO_CLIENTE_KG,
)

# Setup SWI-Prolog prima di importare la KB
setup_swipl_env()

from src.kb_interface.prolog_interface import KnowledgeBase
from src.ml.model_training import carica_modello, predici_profilo
from src.ml.data_cleaning import prepara_dataset_ml


def predici_profili_clienti(clienti: List[str]) -> Dict[str, str]:
    """Predice i profili comportamentali per una lista di clienti.

    Args:
        clienti: Lista di codici cliente (es. ['c_983810', 'c_996530', ...])

    Returns:
        Dizionario {codice_cliente: profilo} dove profilo e'
        'puntuale', 'lieve_ritardo' o 'recidivo'.
    """
    print("[INFO] Caricamento modello ML e dataset per la predizione...")
    modello = carica_modello()
    X, _, df_completo = prepara_dataset_ml()

    profili = {}
    for c in clienti:
        # Rimuove il prefisso 'c_' per cercare nel dataset
        c_code = c.replace("c_", "") if c.startswith("c_") else c
        try:
            c_code_int = int(c_code)
            mask = (df_completo["Codice_Cliente"] == c_code) | (
                df_completo["Codice_Cliente"] == c_code_int
            )
        except ValueError:
            mask = df_completo["Codice_Cliente"] == c_code

        row = df_completo[mask]

        if not row.empty:
            features = row.iloc[0][X.columns].to_dict()
            profili[c] = predici_profilo(modello, features)
        else:
            print(
                f"[WARNING] Cliente {c} non trovato nel dataset storico. "
                "Assumo 'puntuale'."
            )
            profili[c] = "puntuale"

    return profili


def risolvi_assegnamento(
    clienti_da_servire: List[str],
    ora: int,
    minuto: int,
    giorno: int,
    mese: int,
    profili: Optional[Dict[str, str]] = None,
    kb: Optional[KnowledgeBase] = None,
) -> Dict[str, List[str]]:
    """Risolve il problema di assegnamento clienti-veicoli tramite CP-SAT.

    Args:
        clienti_da_servire: Lista di codici cliente da assegnare.
        ora, minuto, giorno, mese: Parametri temporali dello scenario.
        profili: Dizionario profili ML (se None, calcola automaticamente).
        kb: Istanza KnowledgeBase (se None, ne crea una nuova).

    Returns:
        Dizionario {veicolo_id: [lista_clienti_assegnati]}.
    """
    if profili is None:
        profili = predici_profili_clienti(clienti_da_servire)

    if kb is None:
        print("[INFO] Inizializzazione Knowledge Base...")
        kb = KnowledgeBase()

    print("[INFO] Estrazione dati furgoni...")
    furgoni_kb = kb.get_furgoni()
    furgoni = [f["id"] for f in furgoni_kb]
    capacita_furgoni = {f["id"]: int(f["capacita_kg"]) for f in furgoni_kb}

    # Carica cache coordinate per calcolo distanza
    coords = {}
    if GEOCODING_CACHE.exists():
        with open(GEOCODING_CACHE, "r", encoding="utf-8") as f:
            coords = json.load(f)

    # --- Modello CP-SAT ---
    model = cp_model.CpModel()
    x = {}  # x[c][v] = variabile binaria

    print("[INFO] Creazione del modello CP-SAT...")
    print(
        f"  Clienti: {len(clienti_da_servire)}, "
        f"Veicoli: {len(furgoni)}, "
        f"Max per veicolo: {MAX_CLIENTI_PER_VEICOLO}"
    )

    veicoli_idonei_per_cliente = {}
    clienti_senza_veicolo = []

    for c in clienti_da_servire:
        x[c] = {}
        veicoli_idonei_per_cliente[c] = []
        for v in furgoni:
            if kb.furgone_idoneo(v, c, ora, minuto, giorno, mese):
                x[c][v] = model.NewBoolVar(f"x_{c}_{v}")
                veicoli_idonei_per_cliente[c].append(v)

        # Vincolo Hard 1: ogni cliente assegnato a esattamente 1 veicolo
        if not veicoli_idonei_per_cliente[c]:
            clienti_senza_veicolo.append(c)
        else:
            model.AddExactlyOne(
                x[c][v] for v in veicoli_idonei_per_cliente[c]
            )

    if clienti_senza_veicolo:
        print(
            f"[WARNING] {len(clienti_senza_veicolo)} clienti senza veicoli "
            f"idonei: {clienti_senza_veicolo[:5]}..."
        )

    # Vincolo Hard 2 e 3: limiti per veicolo
    for v in furgoni:
        clienti_assegnabili = [
            c
            for c in clienti_da_servire
            if v in veicoli_idonei_per_cliente.get(c, [])
        ]
        if not clienti_assegnabili:
            continue

        # Max clienti per veicolo
        model.Add(
            sum(x[c][v] for c in clienti_assegnabili) <= MAX_CLIENTI_PER_VEICOLO
        )

        # Max capacita' (kg)
        model.Add(
            sum(x[c][v] * PESO_MEDIO_CLIENTE_KG for c in clienti_assegnabili)
            <= capacita_furgoni[v]
        )

    # --- Obiettivo Soft: minimizzare penalita' + distanza ---
    objective_terms = []

    for c in clienti_da_servire:
        if c in clienti_senza_veicolo:
            continue

        c_raw = c.replace("c_", "")
        dist = 0
        if c_raw in coords and coords[c_raw] is not None:
            lat, lon = coords[c_raw]
            # Distanza euclidea scalata a intero (CP-SAT lavora con interi)
            dist = int(
                math.sqrt(
                    (lat - DEPOSITO_LAT) ** 2 + (lon - DEPOSITO_LON) ** 2
                )
                * 10000
            )

        profilo = profili.get(c, "puntuale")
        penalita = PENALITA_PROFILO.get(profilo, 0)

        # Costo = penalita' profilo (peso 1000x) + distanza
        cost_cliente = (penalita * 1000) + dist

        for v in veicoli_idonei_per_cliente[c]:
            objective_terms.append(x[c][v] * cost_cliente)

    if objective_terms:
        model.Minimize(sum(objective_terms))

    # --- Risoluzione ---
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = CSP_TIMEOUT_SECONDS
    print("[INFO] Avvio solver CP-SAT...")
    status = solver.Solve(model)

    assegnamento = {}
    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        status_name = solver.StatusName(status)
        print(f"[OK] Soluzione trovata! (Status: {status_name})")
        print(f"[INFO] Valore obiettivo: {solver.ObjectiveValue():.0f}")
        for v in furgoni:
            assegnamento[v] = []
            for c in clienti_da_servire:
                if (
                    v in veicoli_idonei_per_cliente.get(c, [])
                    and solver.Value(x[c][v])
                ):
                    assegnamento[v].append(c)

        # Stampa riassunto
        for v, clienti_assegnati in assegnamento.items():
            cap = capacita_furgoni[v]
            peso = len(clienti_assegnati) * PESO_MEDIO_CLIENTE_KG
            print(
                f"  [{v}] {len(clienti_assegnati)}/{MAX_CLIENTI_PER_VEICOLO} "
                f"clienti, {peso}/{cap} kg"
            )
    else:
        print(
            f"[ERROR] Nessuna soluzione trovata. "
            f"Status: {solver.StatusName(status)}"
        )

    return assegnamento


if __name__ == "__main__":
    print(
        "[INFO] Esecuzione test: 100 clienti, feriale ore 10:00, 15 giugno..."
    )
    kb_test = KnowledgeBase()
    tutti_clienti_kb = kb_test.get_clienti()
    tutti_clienti = [c["codice"] for c in tutti_clienti_kb]

    print(f"[INFO] Clienti totali: {len(tutti_clienti)}")
    risultato = risolvi_assegnamento(
        clienti_da_servire=tutti_clienti,
        ora=10,
        minuto=0,
        giorno=15,
        mese=6,
        kb=kb_test,
    )

    tot = sum(len(v) for v in risultato.values())
    print(f"\n[OK] Assegnati {tot}/{len(tutti_clienti)} clienti.")
