"""
Uso dei modelli appresi in fase di pianificazione.

Per una data di pianificazione D, le feature dei clienti sono calcolate con
lo storico precedente a D (stesso codice usato per costruire il dataset),
poi i modelli finali stimano:
  - durata del servizio = scarico standard + minuti extra previsti;
  - probabilita' di mancata consegna.
Le stime vengono inserite nella KB come fatti scarico_previsto/2 e
prob_mancata/2, da cui la KB deriva durata_servizio/2 e richiede_preavviso/1.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from typing import Dict, List, Tuple

import pandas as pd

from src.config import TEMPO_SCARICO_BASE_MIN
from src.ml.data_cleaning import carica_storico_arricchito, feature_contesto, feature_storiche
from src.ml.model_training import carica_modelli
from src.parsing.excel_to_prolog import carica_clienti, id_cliente


def prevedi(codici: List[str], data: pd.Timestamp) -> Tuple[Dict[str, int], Dict[str, float]]:
    """codici: codici cliente numerici (stringhe). Restituisce dizionari indicizzati per atomo Prolog."""
    reg, cla = carica_modelli()
    storico = carica_storico_arricchito()
    anag = carica_clienti().set_index("Codice_Cliente")

    righe = pd.DataFrame({"Codice_Cliente": codici, "Data": data})
    righe["Orario_Consegna_Richiesto"] = righe["Codice_Cliente"].map(anag["Orario_Consegna_Richiesto"])
    righe["Macrozona"] = righe["Codice_Cliente"].map(anag["Macrozona"])
    X = feature_storiche(storico, codici, data).merge(
        pd.concat([righe[["Codice_Cliente"]], feature_contesto(righe)], axis=1), on="Codice_Cliente")

    extra = reg["modello"].predict(X[reg["feature"]])
    prob = cla["modello"].predict_proba(X[cla["feature"]])[:, 1]
    scarico = {id_cliente(c): int(round(TEMPO_SCARICO_BASE_MIN + max(0.0, e))) for c, e in zip(codici, extra)}
    p_manc = {id_cliente(c): float(p) for c, p in zip(codici, prob)}
    return scarico, p_manc


if __name__ == "__main__":
    from src.kb_interface.prolog_interface import salva_previsioni_pl

    clienti = carica_clienti()
    codici = clienti.loc[clienti["Citta"] == "Bari", "Codice_Cliente"].tolist()
    scarico, p = prevedi(codici, pd.Timestamp("2026-07-01"))
    salva_previsioni_pl(scarico, p)
    print(f"[OK] Previsioni per {len(codici)} clienti salvate in kb/previsioni.pl")
    for c in list(scarico)[:8]:
        print(f"  {c}: scarico {scarico[c]} min, P(mancata) = {p[c]:.2f}")
