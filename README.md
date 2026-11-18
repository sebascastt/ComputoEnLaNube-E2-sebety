# ComputoEnLaNube-E2-sebety

**Cómputo en la Nube · Entrega 2**
Beatriz León Hernández (0304701) · Sebastián Castillo Femenías (0243380)

El usuario sube la foto de un ticket, una factura en PDF o el XML de un CFDI. El sistema lee los datos (comercio, RFC, fecha, subtotal, IVA y total), los valida y los deja listos para analizar en un lago de datos en S3, consultable con Athena.

## Arquitectura

```
 Usuario (app web)
     │  sube foto / PDF / XML
     ▼
 S3  raw/documentos/<usuario>/<anio>/<mes>/<id>.<ext>          ← zona RAW (original, sin tocar)
     │  evento ObjectCreated (asíncrono)
     ▼
 Lambda (contenedor con OpenCV + Tesseract)
     │  XML → lectura directa · PDF digital → pdfplumber · foto/escaneo → OpenCV + Tesseract
     │  valida: RFC, fecha, total, subtotal + IVA = total, confianza del OCR
     ├──► S3 raw/extraidos/fecha_carga=AAAA-MM-DD/<id>.json     ← zona RAW (dato extraído)
     └──► S3 rechazados/<id>.json  (si no pasó la validación)
     │
     ▼  job programado (diario o mensual)
 Glue (Spark): JSON → Parquet, quita datos personales, marca duplicados
     ▼
 S3  curated/comprobantes/anio=AAAA/mes=MM/*.parquet           ← zona CURATED
     ▼
 Athena (SQL) ──► S3 athena-results/                           ← resultados de consultas
     ▼
 Reportes al usuario: gasto por mes, por categoría, IVA acreditable
```

**Región:** us-east-2 (Ohio) · **Bucket:** `e2-facturas-sebety`

## Estructura del repositorio

| Carpeta / archivo | Qué contiene |
|---|---|
| `src/generar_datos.py` | Genera tickets, facturas PDF y CFDI XML **ficticios** (nada de datos reales) |
| `src/lector/` | El lector: `preprocesamiento.py` (OpenCV), `extraccion.py` (Tesseract, XML, PDF), `procesar.py` (validaciones) |
| `src/lambda_function.py` | Handler de Lambda que conecta el lector con S3 |
| `src/procesar_local.py` | Corre el lector en tu computadora y mide la precisión |
| `src/curar_local.py` | Misma lógica que el job de Glue, en pandas, para probar sin costo |
| `lambda/` | Dockerfile y dependencias de la imagen de Lambda, evento de prueba |
| `glue/raw_a_curated.py` | Job de Glue (raw → curated en Parquet particionado) |
| `athena/` | Creación de tablas y las 3 consultas de la entrega |
| `infra/lifecycle.json` | Reglas de ciclo de vida de S3 (tiering y limpieza) |
| `docs/` | Parte funcional: checklist de la entrega, ADRs, roles, guía de despliegue |
| `evidencias/` | Capturas y bytes de Athena |

## Cómo correrlo en local (sin gastar en AWS)

Requisitos: Python 3.11+ y Tesseract con el idioma español (`tesseract-ocr` y `tesseract-ocr-spa`; en Windows, el instalador de UB Mannheim marcando "Spanish").

```bash
pip install -r requirements.txt

python src/generar_datos.py --salida datos_simulados --meses 3 --docs-por-mes 40   # 1. datos ficticios
python src/procesar_local.py --datos datos_simulados                              # 2. lo que hará Lambda
python src/curar_local.py --datos datos_simulados                                 # 3. lo que hará Glue
```

Resultado de referencia (121 documentos, 3 meses):

| Tipo de documento | n | Total correcto | Fecha correcta | RFC correcto | Rechazados |
|---|---:|---:|---:|---:|---:|
| CFDI XML | 25 | 100% | 100% | 100% | 0 |
| Factura PDF digital | 13 | 100% | 100% | 100% | 0 |
| Factura PDF escaneada | 6 | 100% | 100% | 100% | 0 |
| Ticket (foto) | 77 | 95% | 94% | 88% | 5 |

- Las 5 fotos borrosas a propósito se rechazaron todas (baja confianza del OCR).
- 4 de 116 documentos aceptados tienen un error, siempre en la homoclave del RFC: el OCR confunde `I` con `1` y `Q` con `0`. Esa es la razón para tener a Textract como plan B (ver ADR de procesamiento).
- Tiempo: unos 0.8 s por documento.

Para desplegar en AWS, sigan `docs/guia_despliegue.md`.

## Política de costos (resumen)

| Zona | Formato | Vida | Regla |
|---|---|---|---|
| `raw/documentos/` | PNG, JPG, PDF, XML | 5 años (obligación del SAT) | Standard → Standard-IA (30 d) → Glacier Instant Retrieval (90 d) → Deep Archive (365 d) → se borra (1,830 d) |
| `raw/extraidos/` | JSON | 1 año | Se borra a los 365 días (ya vive en curated) |
| `rechazados/` | JSON | 90 días | Se borra a los 90 días |
| `curated/comprobantes/` | Parquet (snappy), partición anio/mes | Mientras el cliente esté activo | Standard; pesa muy poco |
| `athena-results/` | CSV | 7 días | Se borra a los 7 días |
