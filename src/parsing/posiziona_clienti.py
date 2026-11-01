"""
Posizionamento dei clienti sulla mappa stradale di Bari.

Gli indirizzi del dataset sono fittizi (es. "Via Roma, 190" ripetuta in citta'
diverse, ragioni sociali "Cliente Azienda NNN SRL"): la geocodifica con
Nominatim restituiva punti fuori area, poi agganciati ai bordi della mappa
(33 clienti di Bari finivano su soli 11 nodi).

Si adotta quindi una geolocalizzazione SINTETICA ma controllata:
- solo i clienti con Citta == Bari vengono posizionati (la mappa copre Bari);
- ogni cliente viene assegnato a un nodo stradale reale della sua macrozona
  (rettangoli in config.MACROZONE_BARI), scelto tra i nodi della componente
  fortemente connessa che stanno su strade adatte alla consegna;
- la scelta e' pseudo-casuale ma riproducibile (seed = codice cliente).

Output: dataset/clienti_posizione.csv (Codice_Cliente, Macrozona, nodo, lat, lon)
"""
import sys
import pickle
import random
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from src.config import GRAFO_PICKLE, POSIZIONI_CLIENTI_CSV, MACROZONE_BARI, HIGHWAY_CONSEGNA
from src.parsing.excel_to_prolog import carica_clienti


def nodi_candidati(adj: dict, coords: dict, rettangolo: tuple) -> list:
    """Nodi dentro il rettangolo con almeno un arco uscente di tipo adatto alla consegna."""
    lat_min, lat_max, lon_min, lon_max = rettangolo
    return sorted(
        n for n, (lat, lon) in coords.items()
        if lat_min <= lat <= lat_max and lon_min <= lon <= lon_max
        and any(tipo in HIGHWAY_CONSEGNA for _, _, tipo in adj[n])
    )


def posiziona() -> pd.DataFrame:
    with open(GRAFO_PICKLE, "rb") as f:
        g = pickle.load(f)
    adj, coords = g["adj"], g["coords"]

    clienti = carica_clienti()
    bari = clienti[clienti["Citta"] == "Bari"]
    candidati = {mz: nodi_candidati(adj, coords, r) for mz, r in MACROZONE_BARI.items()}

    righe, usati = [], set()
    for _, r in bari.iterrows():
        rng = random.Random(int(r["Codice_Cliente"]))
        disponibili = [n for n in candidati[r["Macrozona"]] if n not in usati]
        nodo = rng.choice(disponibili)
        usati.add(nodo)
        lat, lon = coords[nodo]
        righe.append({"Codice_Cliente": r["Codice_Cliente"], "Macrozona": r["Macrozona"],
                      "nodo": nodo, "lat": lat, "lon": lon})
    df = pd.DataFrame(righe)
    df.to_csv(POSIZIONI_CLIENTI_CSV, index=False)
    return df


if __name__ == "__main__":
    df = posiziona()
    print(f"[OK] {len(df)} clienti di Bari posizionati in {POSIZIONI_CLIENTI_CSV.name}")
    print(df.groupby("Macrozona").size())
