"""
Simula en tu computadora lo que hará Lambda en AWS, sin gastar nada:
lee cada archivo de raw/documentos/, lo procesa y escribe el JSON en raw/extraidos/.
Al final compara contra esperado.csv para medir la precisión de la lectura.

Uso:
  python src/procesar_local.py --datos datos_simulados
"""
import argparse
import csv
import json
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from lector import procesar_documento  # noqa: E402


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--datos", default="datos_simulados")
    a = p.parse_args()
    datos = Path(a.datos)
    archivos = sorted(f for f in (datos / "raw" / "documentos").rglob("*") if f.is_file())

    registros, inicio = [], time.time()
    for i, ruta in enumerate(archivos, 1):
        llave = ruta.relative_to(datos).as_posix()
        reg = procesar_documento(ruta.read_bytes(), llave)
        # misma partición que usará Lambda: por fecha de carga
        destino = datos / "raw" / "extraidos" / f"fecha_carga={reg['fecha_procesamiento'][:10]}"
        destino.mkdir(parents=True, exist_ok=True)
        (destino / f"{reg['id_documento']}.json").write_text(json.dumps(reg, ensure_ascii=False), encoding="utf-8")
        registros.append(reg)
        print(f"\r  procesados {i}/{len(archivos)}", end="", flush=True)
    seg = time.time() - inicio
    print(f"\n\nTiempo: {seg:.1f} s ({seg / len(archivos):.2f} s por documento)\n")

    # ---- comparación contra los valores reales
    esperado = {r["archivo"]: r for r in csv.DictReader(open(datos / "esperado.csv", encoding="utf-8"))}
    filas = []
    for reg in registros:
        e = esperado[reg["archivo_origen"]]
        filas.append({
            "tipo": e["tipo"], "calidad": e["calidad"], "estatus": reg["estatus"], "metodo": reg.get("metodo_lectura"),
            "total_ok": reg.get("total") is not None and abs(reg["total"] - float(e["total"])) < 0.01,
            "fecha_ok": reg.get("fecha_emision") == e["fecha_emision"],
            "rfc_ok": reg.get("rfc_emisor") == e["rfc_emisor"],
            "motivo": reg.get("motivo_rechazo"),
        })

    print(f"{'tipo de documento':<24}{'n':>4}{'total':>8}{'fecha':>8}{'RFC':>8}{'rechaz.':>9}")
    for tipo in sorted({f["tipo"] for f in filas}):
        g = [f for f in filas if f["tipo"] == tipo]
        pct = lambda k: f"{100 * sum(f[k] for f in g) / len(g):.0f}%"
        print(f"{tipo:<24}{len(g):>4}{pct('total_ok'):>8}{pct('fecha_ok'):>8}{pct('rfc_ok'):>8}"
              f"{sum(f['estatus'] == 'rechazado' for f in g):>9}")

    malas = [f for f in filas if f["calidad"] == "mala"]
    aceptados = [f for f in filas if f["estatus"] == "procesado"]
    errores_aceptados = [f for f in aceptados if not (f["total_ok"] and f["fecha_ok"] and f["rfc_ok"])]
    print(f"\nFotos malas rechazadas: {sum(f['estatus'] == 'rechazado' for f in malas)} de {len(malas)}")
    print(f"Documentos aceptados con algún campo mal: {len(errores_aceptados)} de {len(aceptados)}")
    print("Motivos de rechazo:", dict(Counter(m for f in filas if f["motivo"] for m in f["motivo"].split(";"))))


if __name__ == "__main__":
    main()
