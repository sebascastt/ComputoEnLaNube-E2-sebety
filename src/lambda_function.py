"""
Función Lambda de ingesta. Se dispara de forma ASÍNCRONA cuando cae un archivo en
s3://<bucket>/raw/documentos/...

Flujo:
  1. Descarga el archivo que disparó el evento
  2. Lo lee (XML, PDF o foto con OpenCV + Tesseract) y valida
  3. Escribe el resultado en raw/extraidos/fecha_carga=AAAA-MM-DD/<id>.json
     Si se rechaza, además deja una copia en rechazados/ para avisar al usuario

Si algo truena, Lambda reintenta 2 veces por su cuenta (invocación asíncrona) y
después manda el evento a la cola de errores (DLQ) configurada.
"""
import json
import os
import urllib.parse

import boto3

from lector import procesar_documento

s3 = boto3.client("s3")
PREFIJO_SALIDA = os.environ.get("PREFIJO_SALIDA", "raw/extraidos")
PREFIJO_RECHAZOS = os.environ.get("PREFIJO_RECHAZOS", "rechazados")


def handler(event, context):
    resultados = []
    for record in event.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]
        llave = urllib.parse.unquote_plus(record["s3"]["object"]["key"])
        if llave.endswith("/"):
            # La consola crea "carpetas" como objetos vacíos que terminan en "/": no son documentos
            print(json.dumps({"llave": llave, "estatus": "ignorado", "motivo": "marcador_de_carpeta"}))
            continue
        contenido = s3.get_object(Bucket=bucket, Key=llave)["Body"].read()

        reg = procesar_documento(contenido, llave)
        cuerpo = json.dumps(reg, ensure_ascii=False).encode("utf-8")
        destino = f"{PREFIJO_SALIDA}/fecha_carga={reg['fecha_procesamiento'][:10]}/{reg['id_documento']}.json"
        s3.put_object(Bucket=bucket, Key=destino, Body=cuerpo, ContentType="application/json")
        if reg["estatus"] == "rechazado":
            s3.put_object(Bucket=bucket, Key=f"{PREFIJO_RECHAZOS}/{reg['id_documento']}.json", Body=cuerpo,
                          ContentType="application/json")

        # este print queda en CloudWatch Logs: sirve como evidencia y para depurar
        print(json.dumps({"llave": llave, "estatus": reg["estatus"], "motivo": reg["motivo_rechazo"],
                          "metodo": reg.get("metodo_lectura"), "confianza": reg.get("confianza")}))
        resultados.append({"llave": llave, "estatus": reg["estatus"]})
    return {"procesados": len(resultados), "resultados": resultados}
