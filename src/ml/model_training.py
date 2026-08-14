"""
Training of ML models to predict client behavior profiles.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import numpy as np
import pandas as pd
import joblib
from sklearn.model_selection import StratifiedKFold, GridSearchCV
from sklearn.ensemble import RandomForestClassifier
from sklearn.neighbors import KNeighborsClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.metrics import accuracy_score, f1_score
import warnings

from src.config import RANDOM_STATE, MODELS_DIR
from src.ml.data_cleaning import prepara_dataset_ml

def train_and_evaluate():
    """
    Train and evaluate models using nested cross-validation.
    Returns the best model trained on all data.
    """
    print("[INFO] Loading dataset...")
    X, y, df_completo = prepara_dataset_ml()

    # Drop classes with fewer than 5 samples to avoid StratifiedKFold errors
    class_counts = y.value_counts()
    rare_classes = class_counts[class_counts < 5].index
    if len(rare_classes) > 0:
        print(f"[WARNING] Classes with fewer than 5 samples found: {rare_classes.tolist()}. Dropping them.")
        mask = ~y.isin(rare_classes)
        X = X[mask]
        y = y[mask]
    
    # Outer and inner CV
    outer_cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=RANDOM_STATE)
    inner_cv = StratifiedKFold(n_splits=3, shuffle=True, random_state=RANDOM_STATE)
    
    # Models and parameters
    # Note: KNN benefits from scaling, so we put it in a pipeline
    models = {
        'RF': (
            RandomForestClassifier(class_weight='balanced', random_state=RANDOM_STATE),
            {
                'n_estimators': [50, 100, 200],
                'max_depth': [3, 5, None]
            }
        ),
        'KNN': (
            Pipeline([
                ('scaler', StandardScaler()),
                ('knn', KNeighborsClassifier())
            ]),
            {
                'knn__n_neighbors': [3, 5, 7, 11],
                'knn__weights': ['uniform', 'distance']
            }
        )
    }
    
    results = {
        'RF': {'acc': [], 'macro_f1': [], 'weighted_f1': []},
        'KNN': {'acc': [], 'macro_f1': [], 'weighted_f1': []}
    }
    
    print("[INFO] Starting nested cross-validation...")
    X_arr = X.values
    y_arr = y.values
    
    for fold_idx, (train_ix, test_ix) in enumerate(outer_cv.split(X_arr, y_arr)):
        X_train, X_test = X_arr[train_ix], X_arr[test_ix]
        y_train, y_test = y_arr[train_ix], y_arr[test_ix]
        
        for name, (model, param_grid) in models.items():
            grid = GridSearchCV(
                estimator=model,
                param_grid=param_grid,
                cv=inner_cv,
                scoring='f1_macro',
                n_jobs=-1
            )
            
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                grid.fit(X_train, y_train)
                
            best_model = grid.best_estimator_
            y_pred = best_model.predict(X_test)
            
            acc = accuracy_score(y_test, y_pred)
            mac_f1 = f1_score(y_test, y_pred, average='macro')
            w_f1 = f1_score(y_test, y_pred, average='weighted')
            
            results[name]['acc'].append(acc)
            results[name]['macro_f1'].append(mac_f1)
            results[name]['weighted_f1'].append(w_f1)
            
    # Calculate statistics
    table_lines = []
    table_lines.append("| Modello | Accuracy | Macro-F1 | Weighted-F1 |")
    table_lines.append("|---------|----------|----------|-------------|")
    
    best_model_name = None
    best_macro_f1 = -1.0
    
    for name in models.keys():
        mean_acc = np.mean(results[name]['acc'])
        std_acc = np.std(results[name]['acc'])
        
        mean_mac = np.mean(results[name]['macro_f1'])
        std_mac = np.std(results[name]['macro_f1'])
        
        mean_w = np.mean(results[name]['weighted_f1'])
        std_w = np.std(results[name]['weighted_f1'])
        
        line = f"| {name:<7} | {mean_acc:.2f}+/-{std_acc:.2f} | {mean_mac:.2f}+/-{std_mac:.2f} | {mean_w:.2f}+/-{std_w:.2f} |"
        table_lines.append(line)
        
        if mean_mac > best_macro_f1:
            best_macro_f1 = mean_mac
            best_model_name = name
            
    table_str = "\n".join(table_lines)
    print("\n[INFO] Comparison Table:")
    print(table_str)
    print(f"\n[INFO] Best model selected: {best_model_name}")
    
    # Retrain best model on all data
    best_base_model, best_param_grid = models[best_model_name]
    grid_all = GridSearchCV(
        estimator=best_base_model,
        param_grid=best_param_grid,
        cv=outer_cv,
        scoring='f1_macro',
        n_jobs=-1
    )
    
    print(f"[INFO] Retraining {best_model_name} on all data...")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        grid_all.fit(X_arr, y_arr)
    
    final_best_model = grid_all.best_estimator_
    final_best_model.feature_names_in_ = X.columns.tolist()  # Save feature names for reference
    
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    model_path = MODELS_DIR / "classificatore_profili.pkl"
    report_path = MODELS_DIR / "report_training.txt"
    
    joblib.dump(final_best_model, model_path)
    print(f"[OK] Best model saved to {model_path}")
    
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("Training Report\n")
        f.write("===============\n\n")
        f.write(table_str)
        f.write(f"\n\nBest Model: {best_model_name}\n")
        f.write(f"Best Hyperparameters: {grid_all.best_params_}\n")
        
    print(f"[OK] Training report saved to {report_path}")

def carica_modello():
    """
    Load the saved sklearn model.
    """
    model_path = MODELS_DIR / "classificatore_profili.pkl"
    if not model_path.exists():
        raise FileNotFoundError(f"[ERROR] Model file not found at {model_path}")
    return joblib.load(model_path)

def predici_profilo(modello, features_dict: dict) -> str:
    """
    Predict a single client profile using a features dictionary.
    
    Args:
        modello: The sklearn model returned by carica_modello()
        features_dict: A dictionary containing the client's features.
            
    Returns:
        The predicted profile class (str).
    """
    feature_names = getattr(modello, "feature_names_in_", None)
    
    if feature_names is not None:
        x_input = []
        for f in feature_names:
            if f not in features_dict:
                raise ValueError(f"Feature missing in input: {f}")
            x_input.append(features_dict[f])
    else:
        # Fallback if feature names are not available
        x_input = list(features_dict.values())
        
    x_input_arr = np.array([x_input])
    
    # Avoid warning for feature names not matching
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        pred = modello.predict(x_input_arr)
        
    return str(pred[0])

if __name__ == "__main__":
    train_and_evaluate()
