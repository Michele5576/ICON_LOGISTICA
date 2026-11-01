"""
Lettura del dataset Excel e generazione dei fatti Prolog di flotta e clienti.

Fatti generati:
  kb/flotta.pl   veicolo(Id, Modello, CapacitaKg, VolumeM3, CellaFrigo, Alimentazione, Anno).
  kb/clienti.pl  cliente(Id, Citta, Macrozona).
                 finestra(Id, InizioMin, FineMin).     % minuti dalla mezzanotte
                 ubicazione(Id, Nodo).                 % solo clienti nell'area della mappa

Nessuna regola di dominio viene codificata qui (es. chi ha il permesso ZTL):
le regole stanno nella KB, Python produce solo fatti.
"""
import sys
import re
import unicodedata
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from src.config import (EXCEL_PATH, FOGLIO_FLOTTA, FOGLIO_CLIENTI, FOGLIO_STORICO,
                        FLOTTA_PL, CLIENTI_PL, POSIZIONI_CLIENTI_CSV)


def atomo(s: str) -> str:
    """Converte una stringa in un atomo Prolog valido (minuscolo, senza accenti/spazi)."""
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")
    return s if s and s[0].isalpha() else f"x_{s}"


def id_cliente(codice) -> str:
    """Codice cliente numerico -> atomo Prolog (es. 983810 -> c_983810)."""
    return f"c_{codice}"


def id_veicolo(codice: str) -> str:
    """ID veicolo -> atomo Prolog (es. V-SPR-01 -> v_spr_01)."""
    return atomo(codice)


def normalizza_macrozona(m: str) -> str:
    """'Bari Città' -> 'Bari Citta' (chiave usata in config.MACROZONE_BARI)."""
    return unicodedata.normalize("NFKD", str(m)).encode("ascii", "ignore").decode()


def hhmm_in_minuti(s: str) -> int:
    h, m = str(s).strip().split(":")[:2]
    return int(h) * 60 + int(m)


def carica_flotta() -> pd.DataFrame:
    return pd.read_excel(EXCEL_PATH, sheet_name=FOGLIO_FLOTTA)


def carica_clienti() -> pd.DataFrame:
    df = pd.read_excel(EXCEL_PATH, sheet_name=FOGLIO_CLIENTI, dtype={"Codice_Cliente": str, "CAP": str})
    df["Macrozona"] = df["Macrozona"].map(normalizza_macrozona)
    return df


def carica_storico() -> pd.DataFrame:
    df = pd.read_excel(EXCEL_PATH, sheet_name=FOGLIO_STORICO, dtype={"Codice_Cliente": str})
    df["Macrozona"] = df["Macrozona"].map(normalizza_macrozona)
    return df


def genera_flotta_prolog(df: pd.DataFrame) -> None:
    righe = ["% Fatti generati da src/parsing/excel_to_prolog.py",
             "% veicolo(Id, Modello, CapacitaKg, VolumeM3, CellaFrigo, Alimentazione, AnnoImmatricolazione)."]
    for _, r in df.iterrows():
        vol = float(r["Volume_Carico_m3"])
        vol = int(vol) if vol.is_integer() else vol
        frigo = "si" if str(r["Cella_Frigo"]).strip().upper() == "SI" else "no"
        righe.append(f"veicolo({id_veicolo(r['ID_Veicolo'])}, {atomo(r['Modello'])}, "
                     f"{int(r['Capacita_Carico_kg'])}, {vol}, {frigo}, "
                     f"{atomo(r['Alimentazione'])}, {int(r['Anno_Immatricolazione'])}).")
    FLOTTA_PL.write_text("\n".join(righe) + "\n", encoding="utf-8")
    print(f"[OK] {FLOTTA_PL.name}: {len(df)} veicoli")


def genera_clienti_prolog(df: pd.DataFrame) -> None:
    posizioni = {}
    if POSIZIONI_CLIENTI_CSV.exists():
        pos = pd.read_csv(POSIZIONI_CLIENTI_CSV, dtype={"Codice_Cliente": str})
        posizioni = dict(zip(pos["Codice_Cliente"], pos["nodo"]))
    else:
        print("[WARNING] clienti_posizione.csv assente: eseguire prima posiziona_clienti.py")

    righe = ["% Fatti generati da src/parsing/excel_to_prolog.py",
             "% cliente(Id, Citta, Macrozona).  finestra(Id, InizioMin, FineMin).  ubicazione(Id, Nodo).",
             "% Dinamici: nuovi clienti possono essere aggiunti alla KB a runtime (assertz).",
             ":- dynamic cliente/3, finestra/3, ubicazione/2."]
    for _, r in df.iterrows():
        c = id_cliente(r["Codice_Cliente"])
        righe.append(f"cliente({c}, {atomo(r['Citta'])}, {atomo(r['Macrozona'])}).")
    for _, r in df.iterrows():
        inizio, fine = r["Orario_Consegna_Richiesto"].split("-")
        righe.append(f"finestra({id_cliente(r['Codice_Cliente'])}, {hhmm_in_minuti(inizio)}, {hhmm_in_minuti(fine)}).")
    for cod, nodo in posizioni.items():
        righe.append(f"ubicazione({id_cliente(cod)}, {nodo}).")
    CLIENTI_PL.write_text("\n".join(righe) + "\n", encoding="utf-8")
    print(f"[OK] {CLIENTI_PL.name}: {len(df)} clienti, {len(posizioni)} con ubicazione sulla mappa")


if __name__ == "__main__":
    genera_flotta_prolog(carica_flotta())
    genera_clienti_prolog(carica_clienti())
