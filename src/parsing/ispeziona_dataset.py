"""
Ispezione dei dati di partenza.

Legge il file Excel e l'estratto OSM in dataset/ e produce
dataset/SCHEMA_REALE.md: fogli, colonne, valori mancanti, tipi di strada,
riquadro geografico. Serve a verificare i dati prima del parsing.
"""

import os
import sys
from pathlib import Path
import xml.etree.ElementTree as ET
import openpyxl

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from src.config import DATASET_DIR  # noqa: E402


def ispeziona_excel(path: Path) -> dict:
    """Ispeziona ogni foglio dell'Excel: colonne, tipi, righe, missing, esempi."""
    wb = openpyxl.load_workbook(str(path), data_only=True)
    report = {}

    for nome_foglio in wb.sheetnames:
        ws = wb[nome_foglio]
        righe = list(ws.iter_rows(values_only=True))
        if not righe:
            report[nome_foglio] = {"colonne": [], "n_righe": 0, "nota": "Foglio vuoto"}
            continue

        header = righe[0]
        dati = righe[1:]

        # Analisi per colonna
        colonne_info = []
        for i, col_name in enumerate(header):
            valori = [r[i] for r in dati if r[i] is not None]
            missing = sum(1 for r in dati if r[i] is None)
            esempi = valori[:5]
            tipi_unici = list(set(type(v).__name__ for v in valori[:20]))
            valori_unici_count = len(set(str(v) for v in valori))

            colonne_info.append({
                "nome": col_name,
                "n_validi": len(valori),
                "n_missing": missing,
                "tipi_python": tipi_unici,
                "n_valori_unici": valori_unici_count,
                "esempi": [str(v) for v in esempi],
            })

        report[nome_foglio] = {
            "colonne": colonne_info,
            "n_righe": len(dati),
            "n_colonne": len(header),
        }

    wb.close()
    return report


def ispeziona_xml(path: Path) -> dict:
    """Ispeziona struttura XML: tag, attributi, conteggi, bounding box geo."""
    file_size_mb = os.path.getsize(path) / (1024 * 1024)

    tree = ET.parse(str(path))
    root = tree.getroot()

    # Strip namespace se presente
    tag_root = root.tag
    ns = ""
    if "}" in tag_root:
        ns = tag_root.split("}")[0] + "}"
        tag_root = tag_root.split("}")[1]

    # Analisi figli diretti
    figli_diretti = {}
    for figlio in root:
        tag = figlio.tag.replace(ns, "") if ns else figlio.tag
        if tag not in figli_diretti:
            figli_diretti[tag] = {"count": 0, "attrib_esempio": None, "sotto_tag_esempio": []}
        figli_diretti[tag]["count"] += 1
        if figli_diretti[tag]["attrib_esempio"] is None:
            figli_diretti[tag]["attrib_esempio"] = dict(figlio.attrib)
            # Primi sotto-tag
            sub_tags = []
            for sub in figlio:
                sub_tag = sub.tag.replace(ns, "") if ns else sub.tag
                sub_tags.append({"tag": sub_tag, "attrib": dict(sub.attrib), "text": sub.text})
                if len(sub_tags) >= 5:
                    break
            figli_diretti[tag]["sotto_tag_esempio"] = sub_tags

    # Bounding box geografico (cerca nodi con lat/lon)
    lats, lons = [], []
    node_count = 0
    way_count = 0
    relation_count = 0

    for elem in root.iter():
        tag = elem.tag.replace(ns, "") if ns else elem.tag
        if tag == "node":
            node_count += 1
            lat = elem.get("lat")
            lon = elem.get("lon")
            if lat and lon:
                try:
                    lats.append(float(lat))
                    lons.append(float(lon))
                except ValueError:
                    pass
        elif tag == "way":
            way_count += 1
        elif tag == "relation":
            relation_count += 1

    # Analisi tag highway nelle way
    highway_types = {}
    for way in root.iter("{http://www.openstreetmap.org/osm/0.6}way" if ns else "way"):
        for tag in way:
            tag_name = tag.tag.replace(ns, "") if ns else tag.tag
            if tag_name == "tag" and tag.get("k") == "highway":
                hw_type = tag.get("v", "unknown")
                highway_types[hw_type] = highway_types.get(hw_type, 0) + 1

    bbox = None
    if lats and lons:
        bbox = {
            "lat_min": min(lats),
            "lat_max": max(lats),
            "lon_min": min(lons),
            "lon_max": max(lons),
        }

    return {
        "file_size_mb": round(file_size_mb, 2),
        "tag_root": tag_root,
        "namespace": ns if ns else None,
        "figli_diretti": figli_diretti,
        "conteggio_totale": {
            "nodi": node_count,
            "way": way_count,
            "relazioni": relation_count,
        },
        "bbox_geografico": bbox,
        "highway_types": highway_types,
    }


def scrivi_report(schema_excel: dict, schema_xml: dict, output_path: Path) -> None:
    """Scrive il report SCHEMA_REALE.md."""
    lines = ["# SCHEMA REALE DEI DATASET\n"]
    lines.append("*Generato da `src/parsing/ispeziona_dataset.py`*\n\n")

    # --- EXCEL ---
    lines.append("## 1. File Excel\n\n")

    for nome_foglio, info in schema_excel.items():
        lines.append(f"### Foglio: `{nome_foglio}`\n\n")
        if info.get("nota"):
            lines.append(f"Nota: {info['nota']}\n\n")
            continue

        lines.append(f"- **Righe dati**: {info['n_righe']}\n")
        lines.append(f"- **Colonne**: {info['n_colonne']}\n\n")
        lines.append("| # | Colonna | Validi | Missing | Tipi | Val. Unici | Esempi |\n")
        lines.append("|---|---------|--------|---------|------|------------|--------|\n")
        for i, col in enumerate(info["colonne"]):
            esempi_str = ", ".join(col["esempi"][:3])
            tipi_str = ", ".join(col["tipi_python"])
            lines.append(
                f"| {i+1} | `{col['nome']}` | {col['n_validi']} | {col['n_missing']} | "
                f"{tipi_str} | {col['n_valori_unici']} | {esempi_str} |\n"
            )
        lines.append("\n")

    # --- XML ---
    lines.append("## 2. File XML (Grafo Stradale)\n\n")
    lines.append(f"- **Dimensione**: {schema_xml['file_size_mb']} MB\n")
    lines.append(f"- **Tag root**: `{schema_xml['tag_root']}`\n")
    if schema_xml["namespace"]:
        lines.append(f"- **Namespace**: `{schema_xml['namespace']}`\n")
    lines.append(f"- **Nodi**: {schema_xml['conteggio_totale']['nodi']}\n")
    lines.append(f"- **Way**: {schema_xml['conteggio_totale']['way']}\n")
    lines.append(f"- **Relazioni**: {schema_xml['conteggio_totale']['relazioni']}\n\n")

    if schema_xml["bbox_geografico"]:
        bb = schema_xml["bbox_geografico"]
        lines.append("### Bounding Box Geografico\n\n")
        lines.append("| | Min | Max |\n")
        lines.append("|---|-----|-----|\n")
        lines.append(f"| Latitudine | {bb['lat_min']:.6f} | {bb['lat_max']:.6f} |\n")
        lines.append(f"| Longitudine | {bb['lon_min']:.6f} | {bb['lon_max']:.6f} |\n\n")

    if schema_xml["highway_types"]:
        lines.append("### Tipi di Strada (`highway` tag)\n\n")
        lines.append("| Tipo | Conteggio |\n")
        lines.append("|------|-----------|\n")
        for hw_type, count in sorted(schema_xml["highway_types"].items(), key=lambda x: -x[1]):
            lines.append(f"| `{hw_type}` | {count} |\n")
        lines.append("\n")

    lines.append("### Struttura XML (primi livelli)\n\n")
    for tag, info in schema_xml["figli_diretti"].items():
        lines.append(f"#### Tag `<{tag}>` — {info['count']} occorrenze\n\n")
        if info["attrib_esempio"]:
            lines.append(f"Attributi esempio: `{info['attrib_esempio']}`\n\n")
        if info["sotto_tag_esempio"]:
            lines.append("Sotto-tag esempio:\n")
            for st in info["sotto_tag_esempio"]:
                lines.append(f"- `<{st['tag']}>` attrib=`{st['attrib']}`")
                if st["text"]:
                    lines.append(f" text=`{st['text']}`")
                lines.append("\n")
            lines.append("\n")

    output_path.write_text("".join(lines), encoding="utf-8")
    print(f"[OK] Report scritto in {output_path}")


if __name__ == "__main__":
    xlsx_files = list(DATASET_DIR.glob("*.xlsx"))
    xml_files = list(DATASET_DIR.glob("*.xml"))

    if not xlsx_files:
        print("ERRORE: Nessun file .xlsx trovato in dataset/")
        sys.exit(1)
    if not xml_files:
        print("ERRORE: Nessun file .xml trovato in dataset/")
        sys.exit(1)

    xlsx_path = xlsx_files[0]
    xml_path = xml_files[0]

    print(f"[EXCEL] Ispezione: {xlsx_path.name}")
    schema_excel = ispeziona_excel(xlsx_path)
    for foglio, info in schema_excel.items():
        print(f"  Foglio '{foglio}': {info.get('n_righe', 0)} righe, {info.get('n_colonne', 0)} colonne")

    print(f"\n[XML] Ispezione: {xml_path.name}")
    schema_xml = ispeziona_xml(xml_path)
    print(f"  Nodi: {schema_xml['conteggio_totale']['nodi']}")
    print(f"  Way: {schema_xml['conteggio_totale']['way']}")
    if schema_xml["bbox_geografico"]:
        bb = schema_xml["bbox_geografico"]
        print(f"  Bbox: lat[{bb['lat_min']:.4f}, {bb['lat_max']:.4f}] lon[{bb['lon_min']:.4f}, {bb['lon_max']:.4f}]")
    if schema_xml["highway_types"]:
        print(f"  Highway types: {dict(sorted(schema_xml['highway_types'].items(), key=lambda x: -x[1]))}")

    output_path = DATASET_DIR / "SCHEMA_REALE.md"
    scrivi_report(schema_excel, schema_xml, output_path)
