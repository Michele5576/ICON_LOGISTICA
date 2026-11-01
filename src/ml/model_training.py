"""
Apprendimento supervisionato: confronto di modelli con CV annidata ripetuta.

Task
  R) regressione dei minuti di scarico extra (consegne completate)
  C) classificazione della mancata consegna (classe positiva rara, ~6%)

Protocollo di valutazione
  - CV esterna: K_ESTERNO fold raggruppati per DATA (tutte le consegne di uno
    stesso giorno stanno nello stesso fold: si valuta su giorni mai visti),
    ripetuta N_RIPETIZIONI_CV volte rimescolando l'assegnazione giorni -> fold;
  - CV interna (GridSearchCV, K_INTERNO fold raggruppati per data) per la scelta
    degli iperparametri, eseguita solo sui dati di training del fold esterno;
  - risultati: media +- deviazione standard sui K_ESTERNO * N_RIPETIZIONI_CV test set.

Modelli (cap. 7 del programma): baseline costante, lineare regolarizzato
(Ridge / regressione logistica L2), albero di decisione, Random Forest
(bagging), Gradient Boosting.
Nel task C i falsi negativi (cliente assente non previsto) costano piu' dei
falsi positivi: dove il modello lo consente, gli errori sulla classe rara
sono pesati in proporzione inversa alla sua frequenza (class_weight='balanced').
"""
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import joblib
import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.dummy import DummyClassifier, DummyRegressor
from sklearn.ensemble import (GradientBoostingClassifier, GradientBoostingRegressor,
                              RandomForestClassifier, RandomForestRegressor)
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import (f1_score, mean_absolute_error, mean_squared_error,
                             precision_score, recall_score, roc_auc_score)
from sklearn.model_selection import GridSearchCV, GroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier, DecisionTreeRegressor

from src.config import K_ESTERNO, K_INTERNO, MODELS_DIR, N_RIPETIZIONI_CV, RANDOM_STATE
from src.ml.data_cleaning import (FEATURE_CONTESTO, FEATURE_OPERATIVE, FEATURE_PIANIFICAZIONE,
                                  prepara_dataset_ml)

RS = RANDOM_STATE


def modelli_regressione() -> dict:
    return {
        "Baseline (media)": (DummyRegressor(strategy="mean"), {}),
        "Ridge": (Pipeline([("sc", StandardScaler()), ("m", Ridge())]),
                  {"m__alpha": [0.1, 1, 10, 100]}),
        "Albero di decisione": (DecisionTreeRegressor(random_state=RS),
                                {"max_depth": [3, 5, 8], "min_samples_leaf": [5, 20]}),
        "Random Forest": (RandomForestRegressor(n_estimators=200, random_state=RS, n_jobs=-1),
                          {"max_depth": [5, 10, None], "min_samples_leaf": [1, 5]}),
        "Gradient Boosting": (GradientBoostingRegressor(random_state=RS),
                              {"n_estimators": [100, 200], "learning_rate": [0.05, 0.1],
                               "max_depth": [2, 3]}),
    }


def modelli_classificazione() -> dict:
    return {
        "Baseline (stratificata)": (DummyClassifier(strategy="stratified", random_state=RS), {}),
        "Regressione logistica": (Pipeline([("sc", StandardScaler()),
                                            ("m", LogisticRegression(class_weight="balanced",
                                                                     max_iter=2000))]),
                                  {"m__C": [0.01, 0.1, 1, 10]}),
        "Albero di decisione": (DecisionTreeClassifier(class_weight="balanced", random_state=RS),
                                {"max_depth": [3, 5, 8], "min_samples_leaf": [5, 20]}),
        "Random Forest": (RandomForestClassifier(n_estimators=200, class_weight="balanced",
                                                 random_state=RS, n_jobs=-1),
                          {"max_depth": [5, 10, None], "min_samples_leaf": [1, 5]}),
        "Gradient Boosting": (GradientBoostingClassifier(random_state=RS),
                              {"n_estimators": [100, 200], "learning_rate": [0.05, 0.1],
                               "max_depth": [2, 3]}),
    }


def metriche_regressione(modello, X, y) -> dict:
    p = modello.predict(X)
    return {"MAE": mean_absolute_error(y, p),
            "RMSE": float(np.sqrt(mean_squared_error(y, p)))}


def metriche_classificazione(modello, X, y) -> dict:
    p = modello.predict(X)
    return {"Precision": precision_score(y, p, zero_division=0),
            "Recall": recall_score(y, p, zero_division=0),
            "F1": f1_score(y, p, zero_division=0),
            "AUC": roc_auc_score(y, modello.predict_proba(X)[:, 1])}


def fold_raggruppati(gruppi: np.ndarray, k: int, seed: int):
    """Partizione dei GIORNI in k fold, con assegnazione casuale dipendente dal seed."""
    giorni = np.unique(gruppi)
    perm = np.random.RandomState(seed).permutation(len(giorni))
    fold_di = {g: i % k for g, i in zip(giorni, perm)}
    f = np.array([fold_di[g] for g in gruppi])
    for i in range(k):
        yield np.where(f != i)[0], np.where(f == i)[0]


def cv_annidata(modelli: dict, X: pd.DataFrame, y: np.ndarray, gruppi: np.ndarray,
                metriche, scoring: str) -> tuple[pd.DataFrame, dict]:
    """Restituisce (risultati per fold, iperparametri scelti per modello)."""
    righe, scelte = [], {nome: [] for nome in modelli}
    for rip in range(N_RIPETIZIONI_CV):
        for fold, (tr, te) in enumerate(fold_raggruppati(gruppi, K_ESTERNO, RS + rip)):
            for nome, (stimatore, griglia) in modelli.items():
                m = clone(stimatore)
                if griglia:
                    m = GridSearchCV(m, griglia, cv=GroupKFold(n_splits=K_INTERNO),
                                     scoring=scoring, n_jobs=-1)
                    m.fit(X.iloc[tr], y[tr], groups=gruppi[tr])
                    scelte[nome].append(str(m.best_params_))
                else:
                    m.fit(X.iloc[tr], y[tr])
                righe.append({"modello": nome, "ripetizione": rip, "fold": fold,
                              **metriche(m, X.iloc[te], y[te])})
    return pd.DataFrame(righe), scelte


def tabella(risultati: pd.DataFrame, ordine: list) -> str:
    """Tabella markdown 'media +- dev.std' per ogni metrica."""
    metriche = [c for c in risultati.columns if c not in ("modello", "ripetizione", "fold")]
    agg = risultati.groupby("modello")[metriche].agg(["mean", "std"])
    righe = ["| Modello | " + " | ".join(metriche) + " |",
             "|---|" + "---|" * len(metriche)]
    for nome in ordine:
        celle = [f"{agg.loc[nome, (m, 'mean')]:.3f} ± {agg.loc[nome, (m, 'std')]:.3f}" for m in metriche]
        righe.append(f"| {nome} | " + " | ".join(celle) + " |")
    return "\n".join(righe)


def iperparametri_frequenti(scelte: dict) -> str:
    righe = []
    for nome, lista in scelte.items():
        if lista:
            valori, conteggi = np.unique(lista, return_counts=True)
            i = int(np.argmax(conteggi))
            righe.append(f"- {nome}: {valori[i]} (scelto in {conteggi[i]}/{len(lista)} fold)")
    return "\n".join(righe)


def addestra_finale(stimatore, griglia, X, y, gruppi, scoring):
    m = clone(stimatore)
    if griglia:
        m = GridSearchCV(m, griglia, cv=GroupKFold(n_splits=K_INTERNO), scoring=scoring, n_jobs=-1)
        m.fit(X, y, groups=gruppi)
        return m.best_estimator_, m.best_params_
    return m.fit(X, y), {}


def train_and_evaluate() -> None:
    t0 = time.time()
    df = prepara_dataset_ml()
    gruppi_tutti = df["Data"].astype(str).to_numpy()
    report = ["# Report apprendimento supervisionato", "",
              f"CV annidata: esterna {K_ESTERNO} fold raggruppati per data x {N_RIPETIZIONI_CV} "
              f"ripetizioni ({K_ESTERNO * N_RIPETIZIONI_CV} test set), interna {K_INTERNO} fold.", ""]

    # ---------------- R) regressione minuti di scarico extra ----------------
    comp = df[df["mancata"] == 0].reset_index(drop=True)
    Xr, yr, gr = comp[FEATURE_PIANIFICAZIONE], comp["extra_scarico"].to_numpy(), comp["Data"].astype(str).to_numpy()
    mod_r = modelli_regressione()
    ris_r, scelte_r = cv_annidata(mod_r, Xr, yr, gr, metriche_regressione, "neg_mean_absolute_error")
    report += ["## R) Regressione: minuti di scarico extra", "",
               f"{len(comp)} consegne completate, feature di pianificazione ({len(FEATURE_PIANIFICAZIONE)}).", "",
               tabella(ris_r, list(mod_r)), "", "Iperparametri piu' scelti:", iperparametri_frequenti(scelte_r), ""]

    # ---------------- C) classificazione mancata consegna ----------------
    Xc, yc = df[FEATURE_PIANIFICAZIONE], df["mancata"].to_numpy()
    mod_c = modelli_classificazione()
    ris_c, scelte_c = cv_annidata(mod_c, Xc, yc, gruppi_tutti, metriche_classificazione, "f1")
    report += ["## C) Classificazione: mancata consegna", "",
               f"{len(df)} consegne, positivi {yc.sum()} ({yc.mean():.1%}).", "",
               tabella(ris_c, list(mod_c)), "", "Iperparametri piu' scelti:", iperparametri_frequenti(scelte_c), ""]

    # ---------------- scelta dei modelli finali ----------------
    media_mae = ris_r.groupby("modello")["MAE"].mean().drop("Baseline (media)")
    media_f1 = ris_c.groupby("modello")["F1"].mean().drop("Baseline (stratificata)")
    best_r, best_c = media_mae.idxmin(), media_f1.idxmax()

    # ---------------- ablazione sui gruppi di feature (modello migliore) ----------------
    insiemi = {"solo contesto": FEATURE_CONTESTO,
               "storico + contesto (pianificazione)": FEATURE_PIANIFICAZIONE,
               "pianificazione + operative": FEATURE_PIANIFICAZIONE + FEATURE_OPERATIVE}
    abl_r, abl_c = [], []
    for nome_ins, feat in insiemi.items():
        r, _ = cv_annidata({nome_ins: mod_r[best_r]}, comp[feat], yr, gr, metriche_regressione,
                           "neg_mean_absolute_error")
        c, _ = cv_annidata({nome_ins: mod_c[best_c]}, df[feat], yc, gruppi_tutti, metriche_classificazione, "f1")
        abl_r.append(r)
        abl_c.append(c)
    report += ["## Ablazione sui gruppi di feature", "",
               f"Regressione ({best_r}):", "", tabella(pd.concat(abl_r), list(insiemi)), "",
               f"Classificazione ({best_c}):", "", tabella(pd.concat(abl_c), list(insiemi)), ""]

    # ---------------- addestramento finale su tutti i dati ----------------
    modello_r, par_r = addestra_finale(*mod_r[best_r], Xr, yr, gr, "neg_mean_absolute_error")
    modello_c, par_c = addestra_finale(*mod_c[best_c], Xc, yc, gruppi_tutti, "f1")
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump({"modello": modello_r, "feature": FEATURE_PIANIFICAZIONE, "nome": best_r},
                MODELS_DIR / "regressore_scarico.pkl")
    joblib.dump({"modello": modello_c, "feature": FEATURE_PIANIFICAZIONE, "nome": best_c},
                MODELS_DIR / "classificatore_mancata.pkl")
    report += ["## Modelli finali", "",
               f"- Regressione: {best_r} {par_r}",
               f"- Classificazione: {best_c} {par_c}", ""]

    ris_r.to_csv(MODELS_DIR / "cv_regressione.csv", index=False)
    ris_c.to_csv(MODELS_DIR / "cv_classificazione.csv", index=False)
    report.append(f"Tempo totale: {time.time() - t0:.0f} s")
    (MODELS_DIR / "report_training.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print("\n".join(report))


def carica_modelli() -> tuple[dict, dict]:
    reg = MODELS_DIR / "regressore_scarico.pkl"
    cla = MODELS_DIR / "classificatore_mancata.pkl"
    if not reg.exists() or not cla.exists():
        raise FileNotFoundError("Modelli non trovati: eseguire src/ml/model_training.py")
    return joblib.load(reg), joblib.load(cla)


if __name__ == "__main__":
    train_and_evaluate()
