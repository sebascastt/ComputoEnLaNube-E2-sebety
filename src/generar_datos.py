"""
Generador de datos simulados para el proyecto de digitalización de facturas/tickets.

Crea documentos FICTICIOS (no se usan datos reales por privacidad, LFPDPPP):
  - Tickets "fotografiados" con celular (PNG con rotación, ruido y desenfoque)
  - Facturas en PDF (algunas digitales con texto, otras escaneadas como imagen)
  - Facturas electrónicas CFDI 4.0 en XML

La estructura de carpetas imita las llaves (keys) que tendrán en S3:
  raw/documentos/<id_usuario>/<anio>/<mes>/<id_documento>.<ext>

Además guarda esperado.csv con los valores reales de cada documento, para
medir qué tan bien lee el sistema (precisión del OCR).

Uso:
  python src/generar_datos.py --salida datos_simulados --meses 3 --docs-por-mes 40
"""
import argparse
import csv
import io
import random
import string
import uuid
from datetime import date, timedelta
from pathlib import Path

import cv2
import numpy as np
from faker import Faker
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

FUENTE_MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
FUENTE_MONO_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"

# Comercios inventados, con su categoría de gasto y productos típicos
COMERCIOS = [
    ("ABARROTES LA ESPERANZA", "Supermercado", ["LECHE 1L", "PAN BLANCO", "HUEVO 12PZ", "ARROZ 1KG", "FRIJOL 1KG", "CAFE 200G"]),
    ("SUPER MERCADO DEL VALLE", "Supermercado", ["ACEITE 1L", "AZUCAR 1KG", "ATUN LATA", "PAPEL HIGIENICO", "JABON", "YOGURT"]),
    ("FARMACIA SAN RAFAEL", "Salud", ["PARACETAMOL", "VITAMINA C", "GASAS", "ALCOHOL 250ML", "CUBREBOCAS"]),
    ("GASOLINERA EL PINAR", "Transporte", ["MAGNA LITROS", "PREMIUM LITROS", "ADITIVO"]),
    ("RESTAURANTE LOS ARCOS", "Alimentos", ["COMIDA CORRIDA", "AGUA FRESCA", "CAFE AMERICANO", "POSTRE"]),
    ("CAFETERIA AROMA", "Alimentos", ["CAPUCCINO", "PAN DULCE", "SANDWICH", "TE CHAI"]),
    ("PAPELERIA EL LAPIZ", "Oficina", ["CUADERNO", "PLUMAS 3PZ", "IMPRESIONES", "FOLDER", "MEMORIA USB"]),
    ("FERRETERIA DEL CENTRO", "Hogar", ["TORNILLOS", "FOCO LED", "CINTA AISLANTE", "PINTURA 1L"]),
    ("SERVICIOS DIGITALES NUBE SA", "Servicios", ["HOSPEDAJE WEB", "DOMINIO .MX", "SOPORTE MENSUAL"]),
]

USOS_CFDI = ["G01", "G03", "D01"]


def rfc_persona_moral(nombre: str, rng: random.Random) -> str:
    letras = "".join(c for c in nombre if c.isalpha())[:3].upper().ljust(3, "X")
    fecha = f"{rng.randint(90, 99):02d}{rng.randint(1, 12):02d}{rng.randint(1, 28):02d}"
    homoclave = "".join(rng.choices(string.ascii_uppercase + string.digits, k=3))
    return letras + fecha + homoclave


def rfc_persona_fisica(nombre: str, apellido: str, rng: random.Random) -> str:
    letras = (apellido[:2] + nombre[:1] + rng.choice(string.ascii_uppercase)).upper()
    letras = "".join(c if c.isalpha() else "X" for c in letras)
    fecha = f"{rng.randint(80, 99):02d}{rng.randint(1, 12):02d}{rng.randint(1, 28):02d}"
    homoclave = "".join(rng.choices(string.ascii_uppercase + string.digits, k=3))
    return letras + fecha + homoclave


def generar_conceptos(productos, rng):
    conceptos = []
    for prod in rng.sample(productos, k=rng.randint(1, min(4, len(productos)))):
        cantidad = rng.randint(1, 3)
        precio = round(rng.uniform(15, 450), 2)
        conceptos.append({"descripcion": prod, "cantidad": cantidad,
                          "precio_unitario": precio, "importe": round(cantidad * precio, 2)})
    subtotal = round(sum(c["importe"] for c in conceptos), 2)
    iva = round(subtotal * 0.16, 2)
    return conceptos, subtotal, iva, round(subtotal + iva, 2)


# ---------------------------------------------------------------- tickets (foto)
def dibujar_ticket(doc) -> Image.Image:
    fuente = ImageFont.truetype(FUENTE_MONO, 22)
    fuente_b = ImageFont.truetype(FUENTE_MONO_BOLD, 24)
    ancho = 34  # caracteres por línea, como una impresora térmica
    lineas = [
        (doc["nombre_emisor"].center(ancho), fuente_b),
        (f"RFC: {doc['rfc_emisor']}".center(ancho), fuente),
        (doc["direccion"][:ancho].center(ancho), fuente),
        ("", fuente),
        (f"FECHA: {doc['fecha'].strftime('%d/%m/%Y')}  HORA: {doc['hora']}", fuente),
        (f"TICKET: {doc['folio']}", fuente),
        ("-" * ancho, fuente),
    ]
    for c in doc["conceptos"]:
        izq = f"{c['cantidad']} {c['descripcion']}"[:22]
        der = f"${c['importe']:,.2f}"
        lineas.append((izq + der.rjust(ancho - len(izq)), fuente))
    lineas += [
        ("-" * ancho, fuente),
        ("SUBTOTAL" + f"${doc['subtotal']:,.2f}".rjust(ancho - 8), fuente),
        ("IVA 16%" + f"${doc['iva']:,.2f}".rjust(ancho - 7), fuente),
        ("TOTAL" + f"${doc['total']:,.2f}".rjust(ancho - 5), fuente_b),
        ("", fuente),
        ("GRACIAS POR SU COMPRA".center(ancho), fuente),
        ("FACTURE DENTRO DEL MES".center(ancho), fuente),
    ]
    alto = 60 + 34 * len(lineas)
    img = Image.new("L", (520, alto), color=250)
    d = ImageDraw.Draw(img)
    y = 30
    for texto, f in lineas:
        d.text((20, y), texto, font=f, fill=25)
        y += 34
    return img


def simular_foto(img: Image.Image, rng: random.Random, calidad: str) -> np.ndarray:
    """Convierte el ticket 'perfecto' en algo parecido a una foto de celular."""
    arr = np.array(img)
    # papel térmico un poco desvanecido
    arr = (arr * 0.85 + 30).astype(np.uint8) if rng.random() < 0.3 else arr
    # fondo (la mesa) alrededor del ticket
    fondo = np.full((arr.shape[0] + 160, arr.shape[1] + 160), rng.randint(90, 140), np.uint8)
    fondo[80:80 + arr.shape[0], 80:80 + arr.shape[1]] = arr
    # rotación ligera (la foto no sale derecha)
    angulo = rng.uniform(-4, 4)
    h, w = fondo.shape
    M = cv2.getRotationMatrix2D((w / 2, h / 2), angulo, 1.0)
    fondo = cv2.warpAffine(fondo, M, (w, h), borderValue=int(fondo[0, 0]))
    # iluminación desigual
    grad = np.tile(np.linspace(rng.uniform(0.8, 1.0), 1.0, w), (h, 1))
    fondo = np.clip(fondo * grad, 0, 255).astype(np.uint8)
    # ruido de sensor
    ruido = np.random.default_rng(rng.randint(0, 10**6)).normal(0, 8, fondo.shape)
    fondo = np.clip(fondo + ruido, 0, 255).astype(np.uint8)
    # desenfoque: normal o "foto movida"
    k = 3 if calidad == "buena" else 15
    fondo = cv2.GaussianBlur(fondo, (k, k), 0)
    return fondo


# ---------------------------------------------------------------- facturas PDF
def dibujar_factura_pdf(doc) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    y = 740
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, y, doc["nombre_emisor"]); y -= 20
    c.setFont("Helvetica", 10)
    c.drawString(50, y, f"RFC: {doc['rfc_emisor']}"); y -= 15
    c.drawString(50, y, f"FACTURA  Folio fiscal (UUID): {doc['uuid']}"); y -= 15
    c.drawString(50, y, f"FECHA: {doc['fecha'].strftime('%d/%m/%Y')}"); y -= 15
    c.drawString(50, y, f"Receptor: {doc['nombre_receptor']}  RFC receptor: {doc['rfc_receptor']}"); y -= 30
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, y, "CANT  DESCRIPCION"); c.drawRightString(560, y, "IMPORTE"); y -= 15
    c.setFont("Helvetica", 10)
    for con in doc["conceptos"]:
        c.drawString(50, y, f"{con['cantidad']}     {con['descripcion']}")
        c.drawRightString(560, y, f"${con['importe']:,.2f}"); y -= 15
    y -= 15
    for etiqueta, valor in (("SUBTOTAL", doc["subtotal"]), ("IVA 16%", doc["iva"]), ("TOTAL", doc["total"])):
        c.drawString(400, y, etiqueta); c.drawRightString(560, y, f"${valor:,.2f}"); y -= 15
    c.showPage(); c.save()
    return buf.getvalue()


def escanear_pdf(pdf_bytes: bytes, rng: random.Random) -> bytes:
    """Simula un PDF escaneado: la página es una imagen, sin texto seleccionable."""
    import pypdfium2 as pdfium
    pagina = pdfium.PdfDocument(pdf_bytes)[0]
    img = pagina.render(scale=2).to_pil().convert("L")
    arr = np.array(img).astype(np.float32)
    arr += np.random.default_rng(rng.randint(0, 10**6)).normal(0, 6, arr.shape)
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).rotate(rng.uniform(-1.5, 1.5), fillcolor=255)
    out = io.BytesIO()
    img.save(out, format="PDF", resolution=144)
    return out.getvalue()


# ---------------------------------------------------------------- CFDI XML
def generar_cfdi_xml(doc) -> str:
    conceptos = "\n".join(
        f'    <cfdi:Concepto ClaveProdServ="01010101" Cantidad="{c["cantidad"]}" ClaveUnidad="H87" '
        f'Descripcion="{c["descripcion"]}" ValorUnitario="{c["precio_unitario"]:.2f}" '
        f'Importe="{c["importe"]:.2f}" ObjetoImp="02"/>'
        for c in doc["conceptos"])
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" xmlns:tfd="http://www.sat.gob.mx/TimbreFiscalDigital"
  Version="4.0" Serie="A" Folio="{doc['folio']}" Fecha="{doc['fecha'].isoformat()}T{doc['hora']}:00"
  SubTotal="{doc['subtotal']:.2f}" Moneda="MXN" Total="{doc['total']:.2f}" TipoDeComprobante="I"
  MetodoPago="PUE" FormaPago="04" LugarExpedicion="06000" Exportacion="01">
  <cfdi:Emisor Rfc="{doc['rfc_emisor']}" Nombre="{doc['nombre_emisor']}" RegimenFiscal="601"/>
  <cfdi:Receptor Rfc="{doc['rfc_receptor']}" Nombre="{doc['nombre_receptor']}" UsoCFDI="{doc['uso_cfdi']}"
    DomicilioFiscalReceptor="06000" RegimenFiscalReceptor="612"/>
  <cfdi:Conceptos>
{conceptos}
  </cfdi:Conceptos>
  <cfdi:Impuestos TotalImpuestosTrasladados="{doc['iva']:.2f}"/>
  <cfdi:Complemento>
    <tfd:TimbreFiscalDigital Version="1.1" UUID="{doc['uuid']}" FechaTimbrado="{doc['fecha'].isoformat()}T{doc['hora']}:30"/>
  </cfdi:Complemento>
</cfdi:Comprobante>
'''


# ---------------------------------------------------------------- principal
def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--salida", default="datos_simulados")
    p.add_argument("--meses", type=int, default=3, help="meses hacia atrás desde el mes actual")
    p.add_argument("--docs-por-mes", type=int, default=40)
    p.add_argument("--usuarios", type=int, default=5)
    p.add_argument("--semilla", type=int, default=42)
    a = p.parse_args()

    rng = random.Random(a.semilla)
    fake = Faker("es_MX"); Faker.seed(a.semilla)
    salida = Path(a.salida)
    base = salida / "raw" / "documentos"

    emisores = [{"nombre": n, "categoria": cat, "productos": prods,
                 "rfc": rfc_persona_moral(n, rng), "direccion": fake.street_address().upper()}
                for n, cat, prods in COMERCIOS]
    usuarios = []
    for i in range(1, a.usuarios + 1):
        nom, ape = fake.first_name(), fake.last_name()
        usuarios.append({"id": f"U{i:03d}", "nombre": f"{nom} {ape}".upper(),
                         "rfc": rfc_persona_fisica(nom, ape, rng)})

    hoy = date.today().replace(day=1)
    meses = []
    for k in range(a.meses, 0, -1):
        m = hoy
        for _ in range(k):
            m = (m - timedelta(days=1)).replace(day=1)
        meses.append(m)

    filas, xml_generados, contador = [], [], 0
    for inicio_mes in meses:
        fin_mes = (inicio_mes + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        for _ in range(a.docs_por_mes):
            contador += 1
            u, e = rng.choice(usuarios), rng.choice(emisores)
            conceptos, subtotal, iva, total = generar_conceptos(e["productos"], rng)
            doc = {
                "id_documento": f"D{contador:05d}", "id_usuario": u["id"],
                "nombre_emisor": e["nombre"], "rfc_emisor": e["rfc"], "direccion": e["direccion"],
                "categoria": e["categoria"], "nombre_receptor": u["nombre"], "rfc_receptor": u["rfc"],
                "fecha": inicio_mes + timedelta(days=rng.randint(0, (fin_mes - inicio_mes).days)),
                "hora": f"{rng.randint(8, 21):02d}:{rng.randint(0, 59):02d}",
                "folio": f"{rng.randint(1, 999999):06d}", "uuid": str(uuid.UUID(int=rng.getrandbits(128))).upper(),
                "uso_cfdi": rng.choice(USOS_CFDI), "conceptos": conceptos,
                "subtotal": subtotal, "iva": iva, "total": total,
            }
            r = rng.random()
            tipo = "ticket_foto" if r < 0.6 else ("cfdi_xml" if r < 0.85 else "factura_pdf")
            carpeta = base / u["id"] / f"{doc['fecha']:%Y}" / f"{doc['fecha']:%m}"
            carpeta.mkdir(parents=True, exist_ok=True)
            calidad = "buena"
            if tipo == "ticket_foto":
                calidad = "mala" if rng.random() < 0.07 else "buena"
                ruta = carpeta / f"{doc['id_documento']}.png"
                cv2.imwrite(str(ruta), simular_foto(dibujar_ticket(doc), rng, calidad))
                doc["uuid"] = ""  # los tickets no tienen folio fiscal
            elif tipo == "cfdi_xml":
                ruta = carpeta / f"{doc['id_documento']}.xml"
                ruta.write_text(generar_cfdi_xml(doc), encoding="utf-8")
                xml_generados.append((ruta, doc))
            else:
                pdf = dibujar_factura_pdf(doc)
                escaneado = rng.random() < 0.35
                if escaneado:
                    pdf, tipo = escanear_pdf(pdf, rng), "factura_pdf_escaneada"
                ruta = carpeta / f"{doc['id_documento']}.pdf"
                ruta.write_bytes(pdf)
            filas.append({"archivo": ruta.relative_to(salida).as_posix(), "tipo": tipo, "calidad": calidad,
                          "id_usuario": u["id"], "rfc_emisor": doc["rfc_emisor"], "nombre_emisor": doc["nombre_emisor"],
                          "fecha_emision": doc["fecha"].isoformat(), "subtotal": f"{subtotal:.2f}", "iva": f"{iva:.2f}",
                          "total": f"{total:.2f}", "uuid_cfdi": doc["uuid"], "categoria": doc["categoria"],
                          "duplicado": "no"})

    # Problema de calidad a propósito: el mismo CFDI subido dos veces (~5% de los XML)
    for ruta, doc in rng.sample(xml_generados, k=max(1, len(xml_generados) // 20)):
        contador += 1
        copia = ruta.with_name(f"D{contador:05d}.xml")
        copia.write_text(ruta.read_text(encoding="utf-8"), encoding="utf-8")
        fila = next(f for f in filas if f["archivo"] == ruta.relative_to(salida).as_posix()).copy()
        fila.update(archivo=copia.relative_to(salida).as_posix(), duplicado="si")
        filas.append(fila)

    with open(salida / "esperado.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0].keys()))
        w.writeheader(); w.writerows(filas)

    from collections import Counter
    print(f"Documentos generados: {len(filas)} en {salida}/raw/documentos")
    for t, n in Counter(f["tipo"] for f in filas).items():
        print(f"  {t:<24}{n}")
    print(f"  tickets con foto mala:  {sum(f['calidad'] == 'mala' for f in filas)}")
    print(f"  CFDI duplicados:        {sum(f['duplicado'] == 'si' for f in filas)}")


if __name__ == "__main__":
    main()
