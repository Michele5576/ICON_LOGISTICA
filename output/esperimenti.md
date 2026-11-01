# Esperimenti

## E1. Knowledge Base

- knowledge_base.pl: 39 predicati, 58 regole, 118 fatti
- Fatti generati: flotta.pl 5, clienti.pl 233, ztl_nodi.pl 2152, previsioni.pl 66
- Violazioni dei vincoli d'integrita': nessuna

| Query | Inferenze |
|---|---|
| tipo_giorno(data(7,5,2027), T) | 11 |
| veicoli_idonei(cliente ZTL, feriale) | 1628 |
| idoneo(V, C, feriale) per tutti V, C | 4348 |
| finestra_effettiva(V, C, evento, I, F) | 10499 |
| dimostra(idoneo(...)) (albero di prova) | 1645 |
| violazione(X) (tutti i vincoli) | 492 |

## E2. Ricerca su grafo: A* vs LCFS

196 coppie origine-destinazione (meta' tra clienti/deposito, meta' casuali).

| Profilo | Algoritmo | Nodi espansi | Tempo (ms) | Costo (min) |
|---|---|---|---|---|
| senza vincoli | A* | 8594.10 ± 7261.49 | 22.38 ± 19.18 | 7.28 ± 3.90 |
| senza vincoli | LCFS | 14543.05 ± 10208.00 | 19.62 ± 14.57 | 7.28 ± 3.90 |
| senza vincoli | costi diversi A*/LCFS | 0 |  |  |
| senza vincoli | nodi A* / nodi LCFS | 0.59 |  |  |
| furgone grande (KB) + evita ZTL | A* | 7801.28 ± 6455.87 | 20.43 ± 17.23 | 7.69 ± 4.04 |
| furgone grande (KB) + evita ZTL | LCFS | 13295.57 ± 9252.28 | 17.97 ± 13.19 | 7.69 ± 4.04 |
| furgone grande (KB) + evita ZTL | costi diversi A*/LCFS | 0 |  |  |
| furgone grande (KB) + evita ZTL | nodi A* / nodi LCFS | 0.59 |  |  |

Fattore di tortuosita' (distanza stradale / linea d'aria, coppie > 300 m): mediana 1.43, media 1.53 ± 0.38 su 196 coppie.

## E3. CSP sulle giornate reali

26 giornate dello storico; clienti di Bari per giornata: 12.46 ± 4.25 (min 2, max 18). Timeout B&B 10 s: 'chiuso' = ricerca completata, quindi soluzione ottima dimostrata.
Valori rimossi da GAC prima della ricerca: 0.00 ± 0.00.

| Algoritmo | Costo | Nodi | Tempo (s) | Esito |
|---|---|---|---|---|
| B&B (GAC) | 78.06 ± 22.78 | 158643.58 ± 106019.41 | 6.78 ± 4.42 | 10/26 chiusi |
| B&B (GAC) + limite iniziale da SA | 75.85 ± 20.49 | 145482.62 ± 102671.94 | 6.89 ± 4.53 | 10/26 chiusi |
| Simulated Annealing (5 seed) | 75.92 ± 20.54 | 20000 mosse | 0.20 ± 0.04 | 130/130 ammissibili; gap 0.08 ± 0.47 % |

## E4. Scalabilita' del CSP

Sottoinsiemi casuali dei 33 clienti di Bari, data feriale; B&B con limite iniziale da SA, timeout 10 s.

| Clienti | Istanze | B&B tempo (s) | B&B nodi | B&B chiusi | SA tempo (s) | SA (media 3 seed) - B&B, costo (%) |
|---|---|---|---|---|---|---|
| 8 | 5 | 0.12 ± 0.15 | 5044.40 ± 6187.97 | 5/5 | 0.17 ± 0.01 | 0.00 ± 0.00 |
| 12 | 5 | 8.15 ± 2.64 | 214417.60 ± 68550.94 | 2/5 | 0.20 ± 0.01 | -0.00 ± 0.00 |
| 16 | 5 | 10.00 ± 0.00 | 202335.20 ± 13650.91 | 0/5 | 0.23 ± 0.00 | 0.00 ± 0.00 |
| 20 | 5 | 10.00 ± 0.00 | 140707.00 ± 9992.60 | 0/5 | 0.27 ± 0.00 | -0.00 ± 0.00 |
| 25 | 5 | 10.00 ± 0.00 | 98178.40 ± 2202.63 | 0/5 | 0.32 ± 0.00 | 0.00 ± 0.00 |
| 33 | 1 | 10.00 ± 0.00 | 67079.00 ± 0.00 | 0/1 | 0.41 ± 0.00 | 0.00 ± 0.00 |

## E5. Taratura del Simulated Annealing

6 giornate x 3 seed, 20000 mosse; gap dal costo di riferimento del B&B (ottimo dimostrato in 3/6 giornate).

| T iniziale | alfa | Gap (%) | Volte al riferimento | Prove |
|---|---|---|---|---|
| 5.0 | 0.999 | 0.10 ± 0.28 | 15 | 18 |
| 5.0 | 0.9995 | 0.10 ± 0.28 | 15 | 18 |
| 5.0 | 0.9999 | 0.00 ± 0.00 | 18 | 18 |
| 50.0 | 0.999 | 0.36 ± 0.74 | 13 | 18 |
| 50.0 | 0.9995 | 0.09 ± 0.26 | 16 | 18 |
| 50.0 | 0.9999 | 2.23 ± 2.92 | 9 | 18 |
| 500.0 | 0.999 | 0.34 ± 0.75 | 13 | 18 |
| 500.0 | 0.9995 | 0.19 ± 0.32 | 11 | 18 |
| 500.0 | 0.9999 | 4.44 ± 5.62 | 7 | 18 |

## E6. Scenari sulle giornate reali

Gli ordini di ciascuna delle giornate storiche sono ripianificati come se cadessero in date diverse.

| Scenario | Clienti non servibili | Veicoli usati | km totali (A*) | Consegne in ritardo | Giri oltre turno | Transiti ZTL obbligati |
|---|---|---|---|---|---|---|
| reale (data storica) | 0.00 ± 0.00 | 3.46 ± 0.97 | 51.07 ± 13.28 | 0.00 ± 0.00 | 0.00 ± 0.00 | 0.00 ± 0.00 |
| festivo (domenica) | 0.00 ± 0.00 | 3.46 ± 0.97 | 51.07 ± 13.28 | 0.00 ± 0.00 | 0.00 ± 0.00 | 0.00 ± 0.00 |
| evento (7 maggio) | 1.54 ± 1.18 | 3.08 ± 0.96 | 45.59 ± 13.48 | 0.00 ± 0.00 | 0.00 ± 0.00 | 0.00 ± 0.00 |

Tempo totale: 1015 s
