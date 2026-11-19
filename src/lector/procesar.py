"""
Punto de entrada único: recibe un archivo, decide cómo leerlo, valida y devuelve
un registro listo para guardarse como JSON en raw/extraidos/.
"""
from datetime import date, datetime, timezone
from pathlib import PurePosixPath

from .extraccion import categorizar, leer_imagen, leer_pdf, leer_xml

UMBRAL_CONFIANZA = 60.0    # confianza media de Tesseract por debajo de esto = rechazo
TOLERANCIA_TOTAL = 0.05    # pesos de diferencia permitidos entre subtotal + IVA y total
VERSION_LECTOR = "0.1.0"


def _tipo(nombre: str) -> str:
    ext = PurePosixPath(nombre).suffix.lower()
    if ext == ".xml":
        return "cfdi_xml"
    if ext == ".pdf":
        return "factura_pdf"
    if ext in (".jpg", ".jpeg", ".png"):
        return "imagen"
    return "desconocido"


def validar(r: dict) -> list[str]:
    """Reglas de calidad. Cada problema encontrado se agrega como motivo de rechazo."""
    motivos = []
    for campo in ("rfc_emisor", "fecha_emision", "total"):
        if r.get(campo) in (None, ""):
            motivos.append(f"falta_{campo}")
    if r.get("confianza", 100) < UMBRAL_CONFIANZA:
        motivos.append("baja_confianza_ocr")
    if None not in (r.get("subtotal"), r.get("iva"), r.get("total")):
        if abs(r["subtotal"] + r["iva"] - r["total"]) > TOLERANCIA_TOTAL:
            motivos.append("totales_no_cuadran")
    if r.get("fecha_emision") and r["fecha_emision"] > date.today().isoformat():
        motivos.append("fecha_futura")
    return motivos


def procesar_documento(contenido: bytes, llave_s3: str) -> dict:
    """
    llave_s3 sigue el patrón raw/documentos/<id_usuario>/<anio>/<mes>/<id_documento>.<ext>
    """
    partes = PurePosixPath(llave_s3).parts
    id_usuario = partes[-4] if len(partes) >= 4 else None
    id_documento = PurePosixPath(llave_s3).stem
    tipo = _tipo(llave_s3)

    base = {"id_documento": id_documento, "id_usuario": id_usuario, "archivo_origen": llave_s3,
            "tipo_archivo": tipo, "tamano_bytes": len(contenido)}
    try:
        if tipo == "cfdi_xml":
            campos = leer_xml(contenido)
        elif tipo == "factura_pdf":
            campos = leer_pdf(contenido)
        elif tipo == "imagen":
            campos = leer_imagen(contenido)
        else:
            raise ValueError("formato no soportado")
    except Exception as e:  # archivo corrupto o ilegible
        campos = {"metodo_lectura": "error", "confianza": 0.0, "error": str(e)[:200]}

    registro = {**base, **campos}
    registro["categoria"] = categorizar(registro.get("nombre_emisor"))
    motivos = validar(registro) if campos.get("metodo_lectura") != "error" else ["archivo_ilegible"]
    registro["estatus"] = "rechazado" if motivos else "procesado"
    registro["motivo_rechazo"] = ";".join(motivos) or None
    registro["fecha_procesamiento"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    registro["version_lector"] = VERSION_LECTOR
    return registro
