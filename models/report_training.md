# Report apprendimento supervisionato

CV annidata: esterna 5 fold raggruppati per data x 3 ripetizioni (15 test set), interna 3 fold.

## R) Regressione: minuti di scarico extra

1309 consegne completate, feature di pianificazione (12).

| Modello | MAE | RMSE |
|---|---|---|
| Baseline (media) | 6.910 ± 0.337 | 9.141 ± 0.710 |
| Ridge | 2.709 ± 0.439 | 4.646 ± 1.154 |
| Albero di decisione | 2.070 ± 0.466 | 4.464 ± 1.101 |
| Random Forest | 2.009 ± 0.473 | 4.338 ± 1.151 |
| Gradient Boosting | 2.086 ± 0.489 | 4.285 ± 1.185 |

Iperparametri piu' scelti:
- Ridge: {'m__alpha': 0.1} (scelto in 12/15 fold)
- Albero di decisione: {'max_depth': 3, 'min_samples_leaf': 20} (scelto in 8/15 fold)
- Random Forest: {'max_depth': 5, 'min_samples_leaf': 1} (scelto in 9/15 fold)
- Gradient Boosting: {'learning_rate': 0.05, 'max_depth': 2, 'n_estimators': 100} (scelto in 5/15 fold)

## C) Classificazione: mancata consegna

1393 consegne, positivi 84 (6.0%).

| Modello | Precision | Recall | F1 | AUC |
|---|---|---|---|---|
| Baseline (stratificata) | 0.052 ± 0.058 | 0.058 ± 0.077 | 0.053 ± 0.063 | 0.499 ± 0.039 |
| Regressione logistica | 0.421 ± 0.082 | 0.870 ± 0.108 | 0.561 ± 0.074 | 0.937 ± 0.019 |
| Albero di decisione | 0.341 ± 0.112 | 0.900 ± 0.114 | 0.478 ± 0.114 | 0.901 ± 0.049 |
| Random Forest | 0.386 ± 0.072 | 0.908 ± 0.103 | 0.536 ± 0.071 | 0.949 ± 0.013 |
| Gradient Boosting | 0.424 ± 0.163 | 0.313 ± 0.129 | 0.338 ± 0.094 | 0.934 ± 0.030 |

Iperparametri piu' scelti:
- Regressione logistica: {'m__C': 0.01} (scelto in 14/15 fold)
- Albero di decisione: {'max_depth': 3, 'min_samples_leaf': 5} (scelto in 6/15 fold)
- Random Forest: {'max_depth': 10, 'min_samples_leaf': 5} (scelto in 5/15 fold)
- Gradient Boosting: {'learning_rate': 0.1, 'max_depth': 2, 'n_estimators': 200} (scelto in 5/15 fold)

## Ablazione sui gruppi di feature

Regressione (Random Forest):

| Modello | MAE | RMSE |
|---|---|---|
| solo contesto | 4.165 ± 0.383 | 7.191 ± 0.603 |
| storico + contesto (pianificazione) | 2.009 ± 0.473 | 4.338 ± 1.151 |
| pianificazione + operative | 2.016 ± 0.461 | 4.347 ± 1.107 |

Classificazione (Regressione logistica):

| Modello | Precision | Recall | F1 | AUC |
|---|---|---|---|---|
| solo contesto | 0.070 ± 0.015 | 0.574 ± 0.125 | 0.124 ± 0.024 | 0.622 ± 0.062 |
| storico + contesto (pianificazione) | 0.421 ± 0.082 | 0.870 ± 0.108 | 0.561 ± 0.074 | 0.937 ± 0.019 |
| pianificazione + operative | 0.415 ± 0.074 | 0.866 ± 0.120 | 0.555 ± 0.072 | 0.932 ± 0.024 |

## Modelli finali

- Regressione: Random Forest {'max_depth': 5, 'min_samples_leaf': 1}
- Classificazione: Regressione logistica {'m__C': 0.01}

Tempo totale: 118 s
