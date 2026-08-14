"""
Interfaccia Python per la Knowledge Base Prolog.
Punto unico di contatto tra Python e il motore Prolog (janus_swi).
"""

import sys
import os
from pathlib import Path
from typing import List, Dict, Optional

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from src.config import KB_PL, setup_swipl_env

# Setup SWI-Prolog environment portabile
setup_swipl_env()


class KnowledgeBase:
    """Interfaccia unica Python <-> Prolog per la KB logistica (singleton)."""

    _instance = None
    _initialized = False

    def __new__(cls) -> "KnowledgeBase":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        """Inizializza la connessione Prolog e carica la KB (una sola volta)."""
        if KnowledgeBase._initialized:
            return
        import janus_swi as janus
        self._janus = janus

        # Cambia directory a kb/ per risolvere i consult relativi
        kb_dir = KB_PL.parent
        self._original_cwd = os.getcwd()
        os.chdir(str(kb_dir))
        janus.consult(str(KB_PL).replace("\\", "/"))
        KnowledgeBase._initialized = True

    def accesso_consentito(self, veicolo: str, nodo: str,
                           ora: int, minuto: int,
                           giorno: int, mese: int) -> bool:
        """Verifica se un veicolo puo' attraversare un nodo in un dato momento.

        Args:
            veicolo: ID del veicolo (es. 'v_spr_01')
            nodo: ID del nodo (es. 'n12345')
            ora: Ora (0-23)
            minuto: Minuto (0-59)
            giorno: Giorno del mese (1-31)
            mese: Mese (1-12)

        Returns:
            True se l'accesso e' consentito, False altrimenti.
        """
        query = f"accesso_ztl_consentito({veicolo}, {nodo}, {ora}, {minuto}, {giorno}, {mese})"
        result = list(self._janus.query(query))
        return len(result) > 0

    def furgone_idoneo(self, veicolo: str, cliente: str,
                       ora: int, minuto: int,
                       giorno: int, mese: int) -> bool:
        """Verifica se un furgone e' idoneo a servire un cliente.

        Args:
            veicolo: ID del veicolo (es. 'v_spr_01')
            cliente: ID del cliente (es. 'c_983810')
            ora: Ora (0-23)
            minuto: Minuto (0-59)
            giorno: Giorno del mese
            mese: Mese

        Returns:
            True se il furgone e' idoneo.
        """
        query = f"furgone_idoneo({veicolo}, {cliente}, {ora}, {minuto}, {giorno}, {mese})"
        result = list(self._janus.query(query))
        return len(result) > 0

    def veicoli_per_cliente(self, cliente: str,
                           ora: int, minuto: int,
                           giorno: int, mese: int) -> List[str]:
        """Trova tutti i veicoli idonei per un dato cliente/momento.

        Returns:
            Lista di ID veicolo idonei.
        """
        query = f"veicoli_idonei_per_cliente({cliente}, {ora}, {minuto}, {giorno}, {mese}, Lista)"
        result = list(self._janus.query(query))
        if result:
            return result[0].get("Lista", [])
        return []

    def clienti_per_veicolo(self, veicolo: str,
                            ora: int, minuto: int,
                            giorno: int, mese: int) -> List[str]:
        """Trova tutti i clienti servibili da un dato veicolo/momento.

        Returns:
            Lista di ID cliente servibili.
        """
        query = f"clienti_servibili_da({veicolo}, {ora}, {minuto}, {giorno}, {mese}, Lista)"
        result = list(self._janus.query(query))
        if result:
            return result[0].get("Lista", [])
        return []

    def in_ztl(self, nodo: str) -> bool:
        """Verifica se un nodo e' nella zona ZTL."""
        result = list(self._janus.query(f"in_ztl({nodo})"))
        return len(result) > 0

    def get_clienti(self) -> List[Dict[str, str]]:
        """Restituisce tutti i clienti con nodo e orario."""
        result = list(self._janus.query("cliente(C, Nodo, Orario)"))
        return [{"codice": r["C"], "nodo": r["Nodo"], "orario": str(r["Orario"])}
                for r in result]

    def get_furgoni(self) -> List[Dict]:
        """Restituisce tutti i furgoni con le loro caratteristiche."""
        result = list(self._janus.query("furgone(ID, Cap, Vol, Frigo)"))
        return [{"id": r["ID"], "capacita_kg": r["Cap"],
                 "volume_m3": r["Vol"], "cella_frigo": str(r["Frigo"])}
                for r in result]

    def ha_permesso_ztl(self, veicolo: str) -> bool:
        """Verifica se un veicolo ha il permesso ZTL permanente."""
        result = list(self._janus.query(f"permesso_ztl({veicolo})"))
        return len(result) > 0

    def clienti_in_ztl(self) -> List[str]:
        """Restituisce i codici dei clienti il cui nodo e' in ZTL."""
        result = list(self._janus.query("clienti_in_ztl(Lista)"))
        if result:
            return result[0].get("Lista", [])
        return []

    def nodo_cliente(self, cliente: str) -> Optional[str]:
        """Restituisce il nodo associato a un cliente."""
        result = list(self._janus.query(f"cliente({cliente}, Nodo, _)"))
        if result:
            return result[0]["Nodo"]
        return None


if __name__ == "__main__":
    print("[INFO] Inizializzazione Knowledge Base...")
    kb = KnowledgeBase()

    print("[OK] KB caricata.")
    print(f"  Furgoni: {len(kb.get_furgoni())}")
    print(f"  Clienti: {len(kb.get_clienti())}")
    print(f"  Clienti in ZTL: {len(kb.clienti_in_ztl())}")

    # Test scenario: giorno feriale ore 10
    print("\n[TEST] Scenario feriale ore 10:00, giorno 15 giugno")
    veicoli = kb.veicoli_per_cliente("c_983810", 10, 0, 15, 6)
    print(f"  Veicoli per c_983810: {veicoli}")

    print("\n[TEST] Scenario San Nicola ore 10:00, 7 maggio")
    veicoli_sn = kb.veicoli_per_cliente("c_983810", 10, 0, 7, 5)
    print(f"  Veicoli per c_983810 (San Nicola): {veicoli_sn}")

    print("\n[OK] Tutti i test dell'interfaccia completati.")
