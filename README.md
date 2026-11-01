# Logistica Flotta Furgoni Bari — KBS per ICon 2025/26

Sistema basato su conoscenza che pianifica le consegne giornaliere di una flotta di furgoni nella città di Bari, integrando:

| Modulo | Argomento del programma | File |
|---|---|---|
| Knowledge Base Prolog: tassonomie, default ed eccezioni, calendario/ZTL, finestre effettive, alberi di prova, vincoli d'integrità | Rappresentazione e ragionamento proposizionale e relazionale (capp. 4-5), Knowledge Graph e Ontologie (cap. 6) | `kb/knowledge_base.pl`, `src/kb_interface/` |
| Apprendimento supervisionato: durata dello scarico (regressione) e mancata consegna (classificazione), CV annidata ripetuta | Apprendimento supervisionato (cap. 7) | `src/ml/` |
| Assegnamento clienti → veicoli come CSP con vincoli flessibili: GAC, Branch and Bound con separazione dei domini, Simulated Annealing | Ragionamento con vincoli (cap. 3) | `src/csp/assignment.py` |
| Ordine di visita (DF Branch and Bound) e percorsi su grafo OSM orientato (A* vs LCFS) | Ricerca di soluzioni in spazi di stati (cap. 2) | `src/search/` |

Autore: Michele Barone, matricola 760395, m.barone23@studenti.uniba.it
Repository: https://github.com/Michele5576/ICON_LOGISTICA

## Requisiti

- Python ≥ 3.11
- [SWI-Prolog](https://www.swi-prolog.org/download/stable) ≥ 9 (su Windows viene cercato in `C:\Program Files\swipl`; altrimenti impostare `SWI_HOME_DIR`)

```bash
python -m venv .venv
.venv\Scripts\activate          # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
```

## Esecuzione

I file generati (fatti Prolog, grafo, modelli) sono già nel repository; per rigenerare tutto da zero:

```bash
python src/parsing/ispeziona_dataset.py   # analisi dei dati di partenza -> dataset/SCHEMA_REALE.md
python src/parsing/xml_to_prolog.py       # grafo stradale orientato -> kb/grafo.pl, kb/ztl_nodi.pl, kb/grafo_python.pkl
python src/parsing/posiziona_clienti.py   # posizione dei clienti di Bari -> dataset/clienti_posizione.csv
python src/parsing/excel_to_prolog.py     # flotta e clienti -> kb/flotta.pl, kb/clienti.pl
python src/ml/model_training.py           # CV annidata + modelli finali -> models/
python src/ml/previsione.py               # previsioni -> kb/previsioni.pl
```

Pianificazione e valutazione:

```bash
python src/main.py                        # confronto scenari feriale / festivo / evento -> output/piani_scenari.txt
python src/main.py --data 2026-07-01      # piano di una singola data -> output/piano_2026-07-01.txt
python src/esperimenti.py                 # tutti gli esperimenti -> output/esperimenti.md (~17 min)
pytest tests/                             # test di KB, ricerca e CSP
```

## Struttura

```
dataset/   dati di partenza (Excel, OSM) e derivati (ml_dataset.csv, clienti_posizione.csv)
kb/        knowledge_base.pl (regole) + fatti generati
src/
  parsing/       OSM -> grafo, Excel -> fatti, posizionamento clienti
  kb_interface/  unico punto di accesso Python <-> Prolog (PySwip)
  ml/            dataset senza leakage, addestramento e valutazione, previsioni
  csp/           assegnamento clienti -> veicoli
  search/        A*, LCFS, ordine di visita e simulazione dei giri
  main.py        pipeline end-to-end
  esperimenti.py valutazione
models/    modelli e report della CV (report_training.md)
output/    piani e risultati degli esperimenti
tests/     test pytest
```

## Note sui dati

- Gli indirizzi dei clienti nel dataset sono fittizi: i 33 clienti di Bari sono posizionati su nodi stradali reali della propria macrozona (`src/parsing/posiziona_clienti.py`, scelta riproducibile). I clienti fuori Bari restano nel dataset di apprendimento ma non vengono pianificati.
- La ZTL è approssimata con un rettangolo su Murat e Bari Vecchia (`src/config.py`).
