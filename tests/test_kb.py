"""Test della Knowledge Base Prolog tramite janus_swi."""
import sys
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import setup_swipl_env, KB_PL

# Setup SWI-Prolog environment
setup_swipl_env()

import janus_swi as janus

# Change to kb dir so consult paths in knowledge_base.pl resolve correctly
KB_DIR = KB_PL.parent
os.chdir(str(KB_DIR))
janus.consult(str(KB_PL).replace("\\", "/"))

print("=== TEST 1: Furgoni ===")
furgoni = list(janus.query("furgone(ID, Cap, Vol, Frigo)"))
for r in furgoni:
    print(f"  {r['ID']}: cap={r['Cap']}kg, vol={r['Vol']}m3, frigo={r['Frigo']}")
assert len(furgoni) == 5, f"Attesi 5 furgoni, trovati {len(furgoni)}"

print("\n=== TEST 2: Permesso ZTL ===")
permessi = list(janus.query("permesso_ztl(V)"))
for r in permessi:
    print(f"  {r['V']} ha permesso ZTL")
assert len(permessi) == 1, f"Atteso 1 permesso, trovati {len(permessi)}"
assert permessi[0]["V"] == "v_cit_05"

print("\n=== TEST 3: Primi 5 clienti ===")
clienti = list(janus.query("cliente(C, Nodo, Orario)"))
for r in clienti[:5]:
    print(f"  {r['C']}: nodo={r['Nodo']}, orario={r['Orario']}")
assert len(clienti) == 100, f"Attesi 100 clienti, trovati {len(clienti)}"

print("\n=== TEST 4: ZTL orario attivo (10:00) ===")
result = list(janus.query("in_orario_ztl(10, 0)"))
print(f"  In orario ZTL alle 10:00? {len(result) > 0}")
assert len(result) > 0, "10:00 dovrebbe essere in orario ZTL"

print("\n=== TEST 5: Fuori orario ZTL (22:00) ===")
result = list(janus.query("in_orario_ztl(22, 0)"))
print(f"  In orario ZTL alle 22:00? {len(result) > 0}")
assert len(result) == 0, "22:00 dovrebbe essere fuori orario ZTL"

print("\n=== TEST 6: Accesso ZTL ===")
ztl_nodes = list(janus.query("in_ztl(N)"))
print(f"  Nodi in ZTL: {len(ztl_nodes)}")
assert len(ztl_nodes) > 0

test_node = ztl_nodes[0]["N"]
# v_spr_01 (no permesso) in orario ZTL -> bloccato
result = list(janus.query(f"accesso_ztl_consentito(v_spr_01, {test_node}, 10, 0, 15, 6)"))
print(f"  v_spr_01 ZTL ore 10:00 feriale: accesso={len(result) > 0} (atteso: False)")
assert len(result) == 0, "v_spr_01 NON ha permesso ZTL"

# v_cit_05 (con permesso) in orario ZTL -> consentito
result = list(janus.query(f"accesso_ztl_consentito(v_cit_05, {test_node}, 10, 0, 15, 6)"))
print(f"  v_cit_05 ZTL ore 10:00 feriale: accesso={len(result) > 0} (atteso: True)")
assert len(result) > 0, "v_cit_05 HA permesso ZTL"

# v_spr_01 fuori orario ZTL -> consentito
result = list(janus.query(f"accesso_ztl_consentito(v_spr_01, {test_node}, 22, 0, 15, 6)"))
print(f"  v_spr_01 ZTL ore 22:00 feriale: accesso={len(result) > 0} (atteso: True)")
assert len(result) > 0, "Fuori orario ZTL, accesso consentito a tutti"

print("\n=== TEST 7: San Nicola (7 maggio) ===")
# v_spr_01 durante San Nicola -> bloccato (ZTL 24h e no permesso)
result = list(janus.query(f"accesso_ztl_consentito(v_spr_01, {test_node}, 10, 0, 7, 5)"))
print(f"  v_spr_01 ZTL San Nicola: accesso={len(result) > 0} (atteso: False)")
assert len(result) == 0, "San Nicola: v_spr_01 bloccato"

# v_cit_05 durante San Nicola -> consentito (ha permesso)
result = list(janus.query(f"accesso_ztl_consentito(v_cit_05, {test_node}, 10, 0, 7, 5)"))
print(f"  v_cit_05 ZTL San Nicola: accesso={len(result) > 0} (atteso: True)")
assert len(result) > 0, "San Nicola: v_cit_05 con permesso puo entrare"

print("\n=== TEST 8: Idoneita composta ===")
result = list(janus.query("furgone_idoneo(v_cit_05, C, 10, 0, 7, 5)"))
print(f"  v_cit_05 durante San Nicola ore 10: clienti servibili = {len(result)}")
result_all = list(janus.query("furgone_idoneo(v_spr_01, C, 22, 0, 15, 6)"))
print(f"  v_spr_01 ore 22 feriale: clienti servibili = {len(result_all)}")

print("\n[OK] Tutti i test della Knowledge Base superati!")
