"""
Lectores por tipo de documento. Todos devuelven un diccionario con los mismos campos.

  - XML (CFDI): se lee directo, sin OCR -> exacto y gratis
  - PDF digital: el texto ya viene dentro del archivo (pdfplumber)
  - Foto o escaneo: OpenCV limpia la imagen y Tesseract lee el texto
"""
import re
import xml.etree.ElementTree as ET
from datetime import datetime

import cv2
import numpy as np
import pytesseract

from .preprocesamiento import preparar_para_ocr

RE_RFC = re.compile(r"\b([A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3})\b")
RE_UUID = re.compile(r"\b([0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12})\b", re.I)
RE_FECHA = re.compile(r"\b(\d{2})[/-](\d{2})[/-](\d{4})\b")
RE_MONTO = r"\$?\s*([\d,]+\.\d{2})"

CATEGORIAS = {  # palabra clave en el nombre del comercio -> categoría de gasto
    "ABARROTES": "Supermercado", "SUPER": "Supermercado", "FARMACIA": "Salud",
    "GASOLINERA": "Transporte", "RESTAURANTE": "Alimentos", "CAFETERIA": "Alimentos",
    "PAPELERIA": "Oficina", "FERRETERIA": "Hogar", "SERVICIOS": "Servicios",
}


def categorizar(nombre_emisor: str | None) -> str:
    nombre = (nombre_emisor or "").upper()
    return next((cat for clave, cat in CATEGORIAS.items() if clave in nombre), "Otros")


def _monto(texto: str, etiqueta: str) -> float | None:
    # ^ evita que "TOTAL" haga match dentro de "SUBTOTAL"; [^\w\n]* tolera basura como "- " o "| "
    # (?![A-Z]) = la etiqueta termina ahí; [^\n$]*? salta cosas como "16%" hasta llegar al monto
    m = re.search(rf"^[^\w\n]*{etiqueta}(?![A-Z])[^\n$]*?{RE_MONTO}", texto, re.M | re.I)
    return float(m.group(1).replace(",", "")) if m else None


# Confusiones típicas del OCR entre letras y números
A_LETRA = str.maketrans("0125678", "OIZSGTB")
A_NUMERO = str.maketrans("OQDIlLZSGTB", "00011125678")


def corregir_rfc(candidato: str) -> str | None:
    """
    Un RFC tiene 3-4 letras + 6 dígitos (fecha) + 3 de homoclave. Si el OCR leyó '6AS960415V3A',
    sabemos que las primeras posiciones deben ser letras, así que '6' -> 'G'.
    La homoclave mezcla letras y números, así que ahí no se puede corregir (I vs 1, Q vs 0).
    """
    c = re.sub(r"[^A-Z0-9Ñ&]", "", candidato.upper())
    for n_letras in (3, 4):
        if len(c) == n_letras + 9:
            letras, fecha, homo = c[:n_letras], c[n_letras:n_letras + 6], c[n_letras + 6:]
            rfc = letras.translate(A_LETRA) + fecha.translate(A_NUMERO) + homo
            if RE_RFC.fullmatch(rfc):
                return rfc
    return None


def buscar_rfcs(texto: str) -> list[str]:
    rfcs = []
    for m in re.finditer(r"RFC[^\n:]*:\s*([A-Z0-9Ñ&]{12,13})", texto, re.I):  # primero, los que tienen etiqueta
        if (rfc := corregir_rfc(m.group(1))) and rfc not in rfcs:
            rfcs.append(rfc)
    for rfc in RE_RFC.findall(texto.upper()):
        if rfc not in rfcs:
            rfcs.append(rfc)
    return rfcs


def _parece_nombre(linea: str) -> bool:
    """Al menos 2 palabras en mayúsculas de 2+ letras y casi puras letras (descarta ruido del borde)."""
    palabras = re.findall(r"\b[A-ZÑÁÉÍÓÚ]{2,}\b", linea)
    letras = sum(ch.isalpha() or ch == " " for ch in linea)
    return len(palabras) >= 2 and letras / max(len(linea), 1) > 0.85 and not re.search(r"RFC|FECHA|TICKET", linea, re.I)


def nombre_comercio(lineas: list[str]) -> str | None:
    """En tickets y facturas el nombre del comercio va justo arriba del RFC."""
    limpias = [re.sub(r"^[^\wÑ]+|[^\wÑ.]+$", "", l) for l in lineas]
    idx_rfc = next((i for i, l in enumerate(limpias) if re.search(r"\bRFC\b", l, re.I)), None)
    if idx_rfc and _parece_nombre(limpias[idx_rfc - 1]):
        return limpias[idx_rfc - 1]
    return next((l for l in limpias[:6] if _parece_nombre(l)), None)


def campos_desde_texto(texto: str) -> dict:
    """Saca los campos de interés del texto plano que devolvió el OCR o el PDF."""
    lineas = [l.strip() for l in texto.splitlines() if l.strip()]
    rfcs = buscar_rfcs(texto)
    fecha = None
    if (m := RE_FECHA.search(texto)):
        try:
            fecha = datetime.strptime("/".join(m.groups()), "%d/%m/%Y").date().isoformat()
        except ValueError:
            pass
    uuid = RE_UUID.search(texto)
    subtotal, iva, total = _monto(texto, "SUBTOTAL"), _monto(texto, "IVA"), _monto(texto, "TOTAL")
    total_inferido = False
    if total is None and subtotal is not None and iva is not None:
        # el OCR no leyó el total pero sí sus partes: se calcula y se marca para revisión
        total, total_inferido = round(subtotal + iva, 2), True
    return {
        "nombre_emisor": nombre_comercio(lineas),
        "rfc_emisor": rfcs[0] if rfcs else None,
        "rfc_receptor": rfcs[1] if len(rfcs) > 1 else None,
        "fecha_emision": fecha,
        "subtotal": subtotal, "iva": iva, "total": total, "total_inferido": total_inferido,
        "uuid_cfdi": uuid.group(1).upper() if uuid else None,
    }


def leer_xml(contenido: bytes) -> dict:
    raiz = ET.fromstring(contenido)

    def buscar(etiqueta):  # ignora el namespace (cfdi:, tfd:)
        return next((e for e in raiz.iter() if e.tag.split("}")[-1] == etiqueta), None)

    emisor, receptor, timbre, impuestos = buscar("Emisor"), buscar("Receptor"), buscar("TimbreFiscalDigital"), buscar("Impuestos")
    return {
        "nombre_emisor": emisor.get("Nombre") if emisor is not None else None,
        "rfc_emisor": emisor.get("Rfc") if emisor is not None else None,
        "rfc_receptor": receptor.get("Rfc") if receptor is not None else None,
        "fecha_emision": (raiz.get("Fecha") or "")[:10] or None,
        "subtotal": float(raiz.get("SubTotal")) if raiz.get("SubTotal") else None,
        "iva": float(impuestos.get("TotalImpuestosTrasladados")) if impuestos is not None else None,
        "total": float(raiz.get("Total")) if raiz.get("Total") else None,
        "uuid_cfdi": timbre.get("UUID").upper() if timbre is not None else None,
        "metodo_lectura": "xml", "confianza": 100.0,
    }


def ocr_imagen(img: np.ndarray) -> dict:
    limpia, metricas = preparar_para_ocr(img)
    datos = pytesseract.image_to_data(limpia, lang="spa", config="--psm 4", output_type=pytesseract.Output.DICT)
    confs = [float(c) for c, t in zip(datos["conf"], datos["text"]) if t.strip() and float(c) >= 0]
    texto = pytesseract.image_to_string(limpia, lang="spa", config="--psm 4")
    campos = campos_desde_texto(texto)
    campos.update(metodo_lectura="tesseract", confianza=round(sum(confs) / len(confs), 1) if confs else 0.0,
                  nitidez=metricas["nitidez"])
    return campos


def leer_imagen(contenido: bytes) -> dict:
    img = cv2.imdecode(np.frombuffer(contenido, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("no se pudo abrir la imagen")
    return ocr_imagen(img)


def leer_pdf(contenido: bytes) -> dict:
    import io
    import pdfplumber
    with pdfplumber.open(io.BytesIO(contenido)) as pdf:
        texto = "\n".join((p.extract_text() or "") for p in pdf.pages)
    if len(texto.strip()) > 30:  # PDF digital: ya trae texto, no hace falta OCR
        campos = campos_desde_texto(texto)
        campos.update(metodo_lectura="pdf_texto", confianza=100.0)
        return campos
    # PDF escaneado: es una imagen dentro de un PDF -> se renderiza y pasa por OCR
    import pypdfium2 as pdfium
    pagina = pdfium.PdfDocument(contenido)[0]
    img = np.array(pagina.render(scale=2).to_pil().convert("L"))
    campos = ocr_imagen(img)
    campos["metodo_lectura"] = "tesseract_pdf"
    return campos
