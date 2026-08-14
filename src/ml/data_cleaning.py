import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd
import numpy as np

from src.config import DATASET_DIR
from src.parsing.excel_to_prolog import carica_storico

def prepara_dataset_ml() -> tuple[pd.DataFrame, pd.Series, pd.DataFrame]:
    """
    Carica lo storico consegne, calcola le feature aggregate per cliente,
    definisce il target 'profilo_comportamentale' e salva il dataset.
    Ritorna le feature (X), il target (y) e l'intero dataframe aggregato.
    """
    df_storico = carica_storico()
    
    # 2. Derivazione di nuove colonne
    df_storico['ritardo_min'] = df_storico['Tempo_Scarico_Effettivo_min'] - df_storico['Tempo_Scarico_Previsto_min']
    
    def time_to_float(t):
        if pd.isna(t):
            return np.nan
        t_str = str(t)
        # Prende in considerazione formato orario
        if ':' in t_str:
            h, m = map(int, t_str.split(':')[:2])
            return h + m / 60.0
        return np.nan

    df_storico['ora_arrivo_float'] = df_storico['Ora_Arrivo_Effettiva'].apply(time_to_float)
    
    df_storico['Data'] = pd.to_datetime(df_storico['Data'])
    df_storico['giorno_settimana'] = df_storico['Data'].dt.dayofweek
    
    def get_fascia(h):
        if pd.isna(h):
            return 'mattina'
        if h < 12:
            return 'mattina'
        elif h < 17:
            return 'pomeriggio'
        else:
            return 'sera'
            
    df_storico['fascia_oraria'] = df_storico['ora_arrivo_float'].apply(get_fascia)
    df_storico['consegna_fallita'] = (df_storico['Esito_Consegna'] != 'Completata').astype(int)
    
    # 3. Aggregazione per Codice_Cliente
    agg_funcs = {
        'ritardo_min': ['mean', 'std', 'max', lambda x: (x > 0).mean()],
        'consegna_fallita': ['count', 'mean'],
        'Macrozona': lambda x: x.mode()[0] if not x.empty else 'Ignota'
    }
    
    df_agg = df_storico.groupby('Codice_Cliente').agg(agg_funcs)
    
    # Appiattimento delle multi-colonne
    df_agg.columns = ['media_ritardo', 'std_ritardo', 'max_ritardo', 'pct_ritardo_positivo', 
                      'conteggio_consegne', 'pct_fallite', 'macrozona_principale']
    
    df_agg.reset_index(inplace=True)
    
    # Sostituzione di eventuali NaN nella deviazione standard (occorre per i count = 1)
    df_agg['std_ritardo'] = df_agg['std_ritardo'].fillna(0.0)
    
    # 4. Calcolo del TARGET
    # NB: nel dataset reale, pct_ritardo_positivo e' sempre 0.0 o 1.0
    # (ogni cliente e' o sempre puntuale o sempre in ritardo).
    # Quindi usiamo media_ritardo per discriminare i livelli di ritardo:
    #  - puntuale: nessun ritardo (pct_ritardo_positivo <= 0.3)
    #  - lieve_ritardo: ritardi moderati (media_ritardo <= 12)
    #  - recidivo: ritardi gravi (media_ritardo > 12)
    def calc_target(row):
        if row['pct_ritardo_positivo'] <= 0.3:
            return 'puntuale'
        elif row['media_ritardo'] <= 12:
            return 'lieve_ritardo'
        else:
            return 'recidivo'
            
    df_agg['profilo_comportamentale'] = df_agg.apply(calc_target, axis=1)
    
    # 5. Costruzione del DataFrame finale per il ML
    df_agg['macrozona_encoded'] = df_agg['macrozona_principale'].astype('category').cat.codes
    
    feature_cols = ['media_ritardo', 'std_ritardo', 'max_ritardo', 'pct_ritardo_positivo', 
                    'conteggio_consegne', 'pct_fallite', 'macrozona_encoded']
    
    X = df_agg[feature_cols].copy()
    y = df_agg['profilo_comportamentale'].copy()
    
    # 6. Salvataggio
    output_path = DATASET_DIR / "ml_dataset.csv"
    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    df_agg.to_csv(output_path, index=False)
    
    return X, y, df_agg

if __name__ == "__main__":
    X, y, df = prepara_dataset_ml()
    print("[INFO] Distribuzione classi Target:")
    print(y.value_counts())
    print(f"\n[INFO] Forma di df_completo: {df.shape}")
    print("[INFO] Numero di NaN in X:", X.isna().sum().sum())
    print("[OK] Dataset ML creato con successo in dataset/ml_dataset.csv")
