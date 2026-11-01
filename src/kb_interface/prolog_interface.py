"""
Interfaccia Python per la Knowledge Base Prolog.
Punto unico di contatto tra Python e il motore Prolog (PySwip -> SWI-Prolog).
Gli altri moduli non scrivono query Prolog: usano i metodi di questa classe.
"""

import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from src.config import KB_PL, PREVISIONI_PL, setup_swipl_env

setup_swipl_env()
from pyswip import Prolog  # noqa: E402  (richiede SWI_HOME_DIR impostata)


def data_prolog(giorno: int, mese: int, anno: int) -> str:
    return f"data({giorno}, {mese}, {anno})"


class KnowledgeBase:
    """Interfaccia unica Python <-> Prolog per la KB logistica (singleton)."""

    _instance = None

    def __new__(cls) -> "KnowledgeBase":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._prolog = Prolog()
            cls._instance._prolog.consult(str(KB_PL).replace("\\", "/"))
        return cls._instance

    # --- primitive ---------------------------------------------------------
    def _tutte(self, query: str) -> List[dict]:
        return list(self._prolog.query(query))

    def _vera(self, query: str) -> bool:
        return bool(list(self._prolog.query(query, maxresult=1)))

    # --- fatti -------------------------------------------------------------
    def veicoli(self) -> List[Dict]:
        """Veicoli con capacita' e classe derivata dalla KB."""
        return [{"id": str(r["V"]), "capacita_kg": r["Cap"], "classe": str(r["C"])}
                for r in self._tutte("veicolo(V, _, Cap, _, _, _, _), classe_veicolo(V, C)")]

    def clienti_servibili(self) -> List[str]:
        return [str(r["C"]) for r in self._tutte("servibile(C)")]

    def nodo_cliente(self, cliente: str) -> Optional[str]:
        r = self._tutte(f"ubicazione({cliente}, N)")
        return str(r[0]["N"]) if r else None

    def clienti_in_ztl(self) -> List[str]:
        return [str(r["C"]) for r in self._tutte("cliente_in_ztl(C)")]

    # --- ragionamento --------------------------------------------------------
    def tipo_giorno(self, g: int, m: int, a: int) -> str:
        return str(self._tutte(f"tipo_giorno({data_prolog(g, m, a)}, T)")[0]["T"])

    def veicoli_idonei(self, cliente: str, g: int, m: int, a: int) -> List[str]:
        r = self._tutte(f"veicoli_idonei({cliente}, {data_prolog(g, m, a)}, L)")
        return [str(v) for v in r[0]["L"]] if r else []

    def finestre_effettive(self, veicolo: str, cliente: str,
                           g: int, m: int, a: int) -> List[Tuple[int, int]]:
        """Intervalli (min) in cui il veicolo puo' servire il cliente quel giorno."""
        q = f"finestra_effettiva({veicolo}, {cliente}, {data_prolog(g, m, a)}, I, F)"
        return sorted({(r["I"], r["F"]) for r in self._tutte(q)})

    def accesso_ztl(self, veicolo: str, g: int, m: int, a: int, minuto: int) -> bool:
        return self._vera(f"accesso_ztl({veicolo}, {data_prolog(g, m, a)}, {minuto})")

    def profilo_stradale(self, veicolo: str) -> Tuple[Dict[str, float], set]:
        """Velocita' per tipo di strada e tipi vietati per il veicolo (usati da A*)."""
        vel = {str(r["T"]): float(r["K"]) for r in self._tutte(f"velocita({veicolo}, T, K)")}
        vietate = {str(r["T"]) for r in self._tutte(f"vietata({veicolo}, T)")}
        return vel, vietate

    def durata_servizio(self, cliente: str) -> int:
        return int(round(self._tutte(f"durata_servizio({cliente}, M)")[0]["M"]))

    def richiede_preavviso(self, cliente: str) -> bool:
        return self._vera(f"richiede_preavviso({cliente})")

    def perche_non_idoneo(self, veicolo: str, cliente: str, g: int, m: int, a: int) -> List[str]:
        q = f"perche_non_idoneo({veicolo}, {cliente}, {data_prolog(g, m, a)}, M)"
        return sorted({str(r["M"]) for r in self._tutte(q)})

    def spiega(self, goal: str) -> Optional[str]:
        """Albero di prova del goal, come stringa (debugging a livello di conoscenza)."""
        r = self._tutte(f"dimostra({goal}, P), with_output_to(string(S), print(P))")
        return str(r[0]["S"]) if r else None

    def violazioni(self) -> List[str]:
        return [str(r["X"]) for r in self._tutte("violazione(X)")]

    # --- conoscenza appresa --------------------------------------------------
    def carica_previsioni(self, scarico: Dict[str, int], prob_mancata: Dict[str, float]) -> None:
        """Sostituisce nella KB i fatti prodotti dal modulo ML."""
        self._tutte("retractall(scarico_previsto(_, _))")
        self._tutte("retractall(prob_mancata(_, _))")
        for c, m in scarico.items():
            self._prolog.assertz(f"scarico_previsto({c}, {int(m)})")
        for c, p in prob_mancata.items():
            self._prolog.assertz(f"prob_mancata({c}, {float(p):.4f})")

    def dimensione_kb(self) -> Dict[str, int]:
        """Predicati, fatti e regole definiti in knowledge_base.pl (esclusi i fatti generati)."""
        q = ("source_file(H, F), sub_atom(F, _, _, 0, 'knowledge_base.pl'), "
             "predicate_property(H, number_of_clauses(N)), predicate_property(H, number_of_rules(R))")
        righe = self._tutte(q)
        regole = sum(r["R"] for r in righe)
        return {"predicati": len(righe), "regole": regole,
                "fatti": sum(r["N"] for r in righe) - regole}

    def statistiche_query(self, goal: str) -> int:
        """Numero di inferenze logiche necessarie per dimostrare tutte le soluzioni del goal."""
        r = self._tutte(f"statistics(inferences, I0), forall({goal}, true), "
                        f"statistics(inferences, I1), N is I1 - I0")
        return int(r[0]["N"])


def salva_previsioni_pl(scarico: Dict[str, int], prob_mancata: Dict[str, float]) -> None:
    """Scrive le previsioni ML come fatti in kb/previsioni.pl (caricato dalla KB)."""
    righe = ["% Fatti generati dal modulo ML (src/ml/model_training.py)",
             "% scarico_previsto(Cliente, Minuti).  prob_mancata(Cliente, Probabilita)."]
    righe += [f"scarico_previsto({c}, {int(m)})." for c, m in sorted(scarico.items())]
    righe += [f"prob_mancata({c}, {p:.4f})." for c, p in sorted(prob_mancata.items())]
    PREVISIONI_PL.write_text("\n".join(righe) + "\n", encoding="utf-8")


if __name__ == "__main__":
    kb = KnowledgeBase()
    print(f"Veicoli: {kb.veicoli()}")
    print(f"Clienti servibili: {len(kb.clienti_servibili())}, in ZTL: {kb.clienti_in_ztl()}")
    print(f"Violazioni d'integrita': {kb.violazioni()}")
    for d in [(15, 6, 2026), (2, 6, 2026), (7, 5, 2026)]:
        print(d, kb.tipo_giorno(*d))
