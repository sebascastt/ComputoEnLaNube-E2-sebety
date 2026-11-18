"""
Versión local (pandas) del job de Glue, con la MISMA lógica que glue/raw_a_curated.py.
Sirve para probar sin gastar y para ver el ahorro de Parquet frente a JSON.

Uso:
  python src/curar_local.py --datos datos_simulados
"""
import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd


def sha256(valor) -> str:
    return hashlib.sha256(str(valor or "").encode()).hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--datos", default="datos_simulados")
    a = p.parse_args()
    datos = Path(a.datos)
    archivos = list((datos / "raw" / "extraidos").rglob("*.json"))
    raw = pd.DataFrame([json.loads(f.read_text(encoding="utf-8")) for f in archivos])

    ok = raw[raw["estatus"] == "procesado"].copy()
    cur = pd.DataFrame({
        "id_documento": ok["id_documento"],
        "id_usuario_hash": ok["id_usuario"].map(sha256),
        "tipo_archivo": ok["tipo_archivo"],
        "metodo_lectura": ok["metodo_lectura"],
        "nombre_emisor": ok["nombre_emisor"],
        "rfc_emisor": ok["rfc_emisor"],
        "rfc_receptor_hash": ok["rfc_receptor"].map(sha256),
        "fecha_emision": pd.to_datetime(ok["fecha_emision"]).dt.date,
        "subtotal": ok["subtotal"].round(2),
        "iva": ok["iva"].round(2),
        "total": ok["total"].round(2),
        "total_inferido": ok["total_inferido"].fillna(False).astype(bool),
        "uuid_cfdi": ok["uuid_cfdi"].str.upper(),
        "categoria": ok["categoria"],
        "confianza_lectura": ok["confianza"].astype(float),
        "fecha_procesamiento": pd.to_datetime(ok["fecha_procesamiento"]),
        "archivo_origen": ok["archivo_origen"],
    })
    cur["anio"] = pd.to_datetime(cur["fecha_emision"]).dt.strftime("%Y")
    cur["mes"] = pd.to_datetime(cur["fecha_emision"]).dt.strftime("%m")
    cur = cur.sort_values(["fecha_procesamiento", "id_documento"])
    tiene_uuid = cur["uuid_cfdi"].notna() & (cur["uuid_cfdi"] != "")
    cur["es_duplicado"] = tiene_uuid & cur.duplicated("uuid_cfdi", keep="first")

    salida = datos / "curated" / "comprobantes"
    cur.to_parquet(salida, partition_cols=["anio", "mes"], compression="snappy", index=False,
                   existing_data_behavior="delete_matching")

    bytes_json = sum(f.stat().st_size for f in archivos)
    bytes_parquet = sum(f.stat().st_size for f in salida.rglob("*.parquet"))
    print(f"raw/extraidos:          {len(raw)} registros, {bytes_json / 1024:.1f} KB en JSON")
    print(f"curated/comprobantes:   {len(cur)} registros, {bytes_parquet / 1024:.1f} KB en Parquet")
    print(f"Particiones:            {sorted({f.parent.relative_to(salida).as_posix() for f in salida.rglob('*.parquet')})}")
    print(f"Duplicados marcados:    {int(cur['es_duplicado'].sum())}")


if __name__ == "__main__":
    main()
