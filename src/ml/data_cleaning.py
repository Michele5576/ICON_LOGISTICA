"""
Costruzione del dataset di apprendimento a partire dallo storico consegne.

Unita' di analisi: la singola consegna (riga dello storico, 1393 esempi).
Due task:
  - regressione:     extra_scarico = Tempo_Scarico_Effettivo - Tempo_Scarico_Previsto (min),
                     solo sulle consegne completate;
  - classificazione: mancata = 1 se Esito_Consegna != 'Completata'.

Assenza di leakage: le feature "storiche" di un cliente per la consegna del
giorno d sono calcolate SOLO sulle consegne dei giorni < d (finestra espandente),
cioe' con l'informazione effettivamente disponibile al momento della
pianificazione. Le stime sono smussate con pseudoconteggi verso la media
globale, anch'essa calcolata solo sul passato (utile per i clienti con poco storico).

Le feature "operative" (ora di arrivo, posizione nel giro, km) sono note solo
a giro effettuato: sono tenute a parte e usate solo per l'esperimento di ablazione.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd

from src.config import ML_DATASET_CSV
from src.parsing.excel_to_prolog import carica_storico, carica_clienti, hhmm_in_minuti

PSEUDOCONTEGGI = 2  # peso (in "consegne virtuali") della media globale nello smussamento

FEATURE_STORICHE = ["n_consegne_prec", "extra_medio_prec", "extra_max_prec",
                    "freq_ritardo_prec", "freq_mancate_prec"]
FEATURE_CONTESTO = ["giorno_settimana", "inizio_finestra", "ampiezza_finestra",
                    "mz_bari", "mz_puglia_nord", "mz_puglia_sud", "mz_basilicata"]
FEATURE_OPERATIVE = ["ora_arrivo", "sequenza_visita", "distanza_km", "veicolo_compatto"]
FEATURE_PIANIFICAZIONE = FEATURE_STORICHE + FEATURE_CONTESTO

# Raggruppamento delle 9 macrozone in 4 aree (evita 9 colonne one-hot quasi vuote)
AREA_MACROZONA = {
    "Bari Citta": "mz_bari", "Bari Nord": "mz_bari", "Bari Sud": "mz_bari",
    "Foggia": "mz_puglia_nord",
    "Lecce Nord (Versante Adriatico)": "mz_puglia_sud", "Lecce Sud (Versante Ionio)": "mz_puglia_sud",
    "Taranto": "mz_puglia_sud",
    "Matera": "mz_basilicata", "Potenza": "mz_basilicata",
}


def _media_smussata(somma: float, n: int, prior: float) -> float:
    return (somma + PSEUDOCONTEGGI * prior) / (n + PSEUDOCONTEGGI)


def feature_storiche(storico: pd.DataFrame, clienti: list, prima_di: pd.Timestamp) -> pd.DataFrame:
    """
    Feature storiche dei clienti calcolate sulle consegne con Data < prima_di.
    Usata sia per costruire il dataset sia per le previsioni in pianificazione.
    """
    passato = storico[storico["Data"] < prima_di]
    completate = passato[passato["mancata"] == 0]
    prior_extra = completate["extra_scarico"].mean() if len(completate) else 0.0
    prior_rit = (completate["extra_scarico"] > 0).mean() if len(completate) else 0.0
    prior_manc = passato["mancata"].mean() if len(passato) else 0.0

    righe = []
    for c in clienti:
        p = passato[passato["Codice_Cliente"] == c]
        pc = p[p["mancata"] == 0]
        n, nc = len(p), len(pc)
        righe.append({
            "Codice_Cliente": c,
            "n_consegne_prec": n,
            "extra_medio_prec": _media_smussata(pc["extra_scarico"].sum(), nc, prior_extra),
            "extra_max_prec": pc["extra_scarico"].max() if nc else 0.0,
            "freq_ritardo_prec": _media_smussata((pc["extra_scarico"] > 0).sum(), nc, prior_rit),
            "freq_mancate_prec": _media_smussata(p["mancata"].sum(), n, prior_manc),
        })
    return pd.DataFrame(righe)


def feature_contesto(df: pd.DataFrame) -> pd.DataFrame:
    """Feature note in pianificazione: giorno, finestra richiesta, area geografica."""
    out = pd.DataFrame(index=df.index)
    out["giorno_settimana"] = df["Data"].dt.day_of_week
    finestre = df["Orario_Consegna_Richiesto"].str.split("-")
    out["inizio_finestra"] = finestre.str[0].map(hhmm_in_minuti)
    out["ampiezza_finestra"] = finestre.str[1].map(hhmm_in_minuti) - out["inizio_finestra"]
    for area in ["mz_bari", "mz_puglia_nord", "mz_puglia_sud", "mz_basilicata"]:
        out[area] = (df["Macrozona"].map(AREA_MACROZONA) == area).astype(int)
    return out


def carica_storico_arricchito() -> pd.DataFrame:
    storico = carica_storico()
    storico["Data"] = pd.to_datetime(storico["Data"])
    storico["extra_scarico"] = storico["Tempo_Scarico_Effettivo_min"] - storico["Tempo_Scarico_Previsto_min"]
    storico["mancata"] = (storico["Esito_Consegna"] != "Completata").astype(int)
    clienti = carica_clienti()[["Codice_Cliente", "Orario_Consegna_Richiesto"]]
    return storico.merge(clienti, on="Codice_Cliente", how="left")


def prepara_dataset_ml(salva: bool = True) -> pd.DataFrame:
    """Dataset completo: una riga per consegna con feature, target e data (per i gruppi della CV)."""
    storico = carica_storico_arricchito()

    blocchi = []
    for giorno, df_g in storico.groupby("Data"):
        fs = feature_storiche(storico, df_g["Codice_Cliente"].unique(), giorno)
        blocchi.append(df_g.merge(fs, on="Codice_Cliente", how="left"))
    df = pd.concat(blocchi).sort_index()

    df = pd.concat([df, feature_contesto(df)], axis=1)
    df["ora_arrivo"] = df["Ora_Arrivo_Effettiva"].map(hhmm_in_minuti)
    df["sequenza_visita"] = df["Sequenza_Visita"]
    df["distanza_km"] = df["Distanza_Stimata_km"]
    df["veicolo_compatto"] = (df["ID_Veicolo"] == "V-CIT-05").astype(int)

    colonne = (["Data", "Codice_Cliente"] + FEATURE_PIANIFICAZIONE + FEATURE_OPERATIVE
               + ["extra_scarico", "mancata"])
    df = df[colonne].reset_index(drop=True)

    assert not df[FEATURE_PIANIFICAZIONE + FEATURE_OPERATIVE].isna().any().any(), "NaN nelle feature"
    if salva:
        df.to_csv(ML_DATASET_CSV, index=False)
    return df


if __name__ == "__main__":
    df = prepara_dataset_ml()
    print(f"[OK] Dataset ML: {df.shape[0]} consegne, salvato in {ML_DATASET_CSV.name}")
    print(f"  mancate consegne: {df['mancata'].sum()} ({df['mancata'].mean():.1%})")
    comp = df[df["mancata"] == 0]
    print(f"  extra scarico (completate): media {comp['extra_scarico'].mean():.2f}, "
          f"dev.std {comp['extra_scarico'].std():.2f}")
    print(df[FEATURE_PIANIFICAZIONE].describe().T[["mean", "std", "min", "max"]])
