# E2_EQBeatrizSebastian · Digitalización de facturas y tickets en AWS

**Cómputo en la Nube · Entrega 2**
Beatriz León Hernández (0304701) · Sebastián Castillo Femenías (0243380)

El usuario sube la foto de un ticket, una factura en PDF o el XML de un CFDI. El sistema lee los datos (comercio, RFC, fecha, subtotal, IVA y total), los valida y los deja listos para analizar en un lago de datos en S3, consultable con Athena.

**Región:** us-east-2 (Ohio) · **Bucket:** `e2-facturas-sebety`

## Arquitectura

```
 Usuario
     │  sube foto / PDF / XML
     ▼
 S3  raw/documentos/<usuario>/<anio>/<mes>/<id>.<ext>          ← zona RAW (original, sin tocar)
     │  aviso de S3 (asíncrono)
     ▼
 Lambda lector-tickets (imagen de Docker en ECR: Python + OpenCV + Tesseract)
     │  XML → lectura directa · PDF digital → pdfplumber · foto/escaneo → OpenCV + Tesseract
     │  valida: RFC, fecha, total, subtotal + IVA = total, confianza del OCR
     ├──► S3 raw/extraidos/fecha_carga=AAAA-MM-DD/<id>.json     ← zona RAW (dato extraído)
     └──► S3 rechazados/<id>.json  (si no pasó la validación)
     │
     ▼  job e2-raw-a-curated
 Glue (Spark): JSON → Parquet, RFC del usuario en hash, marca de duplicados
     ▼
 S3  curated/comprobantes/anio=AAAA/mes=MM/*.parquet           ← zona CURATED
     ▼
 Athena (base facturas_db) ──► S3 athena-results/              ← resultados de consultas
     ▼
 Reportes: gasto por mes, por categoría, IVA acreditable, duplicados
```

## Estructura del repositorio

| Carpeta / archivo | Qué contiene |
|---|---|
| `src/lector/` | **Código real del lector, el que corre en AWS Lambda.** `preprocesamiento.py` (limpieza de imagen con OpenCV), `extraccion.py` (Tesseract, XML y PDF), `procesar.py` (validaciones) |
| `src/lambda_function.py` | **Código real de la Lambda:** recibe el aviso de S3, descarga el archivo, llama al lector y guarda el JSON |
| `src/procesar_local.py` | **Simulación local** de la Lambda: procesa los documentos en tu computadora y mide la precisión |
| `src/curar_local.py` | **Simulación local** del job de Glue (misma lógica, con pandas) |
| `src/generar_datos.py` | Generador de los documentos ficticios |
| `documentos_simulados/` | **Los 121 documentos ficticios que se suben directamente a AWS** (carpetas `U001` a `U005`) y `esperado.csv` con sus valores reales |
| `lambda/` | `Dockerfile` y dependencias de la imagen de la Lambda, y un evento de prueba |
| `script_glue/raw_a_curated.py` | Job de Glue: raw → curated en Parquet particionado por año y mes |
| `athena/` | `01_crear_tablas.sql` (base y tablas) y `02_consultas.sql` (las 3 consultas de la entrega) |
| `lifecycle/lifecycle.json` | Reglas de ciclo de vida de S3 (tiering y limpieza) |

### `src/`: qué corre en AWS y qué es simulación

- `src/lector/` y `src/lambda_function.py` **no son una simulación**: el `Dockerfile` los copia dentro de la imagen `lector-tickets`, que se publica en Amazon ECR y ejecuta la Lambda. Por eso los archivos `.py` no se ven en la consola de AWS: viajan dentro de la imagen.
- `src/procesar_local.py` y `src/curar_local.py` **sí son simulaciones locales** de la Lambda y de Glue. Sirven para probar todo en una computadora sin gastar en AWS.

### `documentos_simulados/`: lo que se sube a AWS

- 121 documentos **ficticios** (ningún dato personal real): 77 fotos de tickets, 13 facturas PDF digitales, 6 PDF escaneados y 25 CFDI XML, de 5 usuarios y 3 meses (agosto a octubre de 2026).
- Traen problemas de calidad a propósito: 5 fotos borrosas (deben rechazarse) y 1 CFDI duplicado (debe detectarse).
- **Cómo subirlos:** en S3, entrar a `raw/documentos/` → Cargar → **arrastrar las carpetas `U001` a `U005`** completas. No crear carpetas a mano (ver "Problemas encontrados").
- **`esperado.csv` no se sube:** es la "hoja de respuestas" para comparar contra lo que leyó la Lambda.

## Cómo correrlo en local (sin gastar en AWS)

Requisitos: Python 3.11+ y Tesseract con el idioma español (`tesseract-ocr` y `tesseract-ocr-spa`; en Windows, el instalador de UB Mannheim marcando "Spanish").

```bash
pip install -r requirements.txt

python src/generar_datos.py --salida datos_simulados --meses 3 --docs-por-mes 40   # 1. genera los documentos (misma semilla = mismos 121)
python src/procesar_local.py --datos datos_simulados                              # 2. simula la Lambda
python src/curar_local.py --datos datos_simulados                                 # 3. simula Glue
```

Resultado de la lectura (121 documentos):

| Tipo de documento | n | Total correcto | Fecha correcta | RFC correcto | Rechazados |
|---|---:|---:|---:|---:|---:|
| CFDI XML | 25 | 100% | 100% | 100% | 0 |
| Factura PDF digital | 13 | 100% | 100% | 100% | 0 |
| Factura PDF escaneada | 6 | 100% | 100% | 100% | 0 |
| Ticket (foto) | 77 | 95% | 94% | 88% | 5 |

Las 5 fotos borrosas se rechazaron todas. De 116 documentos aceptados, 4 tienen un error, siempre en la homoclave del RFC (el OCR confunde `I` con `1` y `Q` con `0`).

## Despliegue en AWS (resumen)

1. **Bucket** `e2-facturas-sebety` en us-east-2: cifrado SSE-S3, acceso público bloqueado, sin versionado. Carpetas `raw/documentos/`, `raw/extraidos/`, `curated/comprobantes/`, `athena-results/`, `rechazados/`.
2. **Ciclo de vida** (desde CloudShell):
   `aws s3api put-bucket-lifecycle-configuration --bucket e2-facturas-sebety --lifecycle-configuration file://lifecycle.json`
3. **Imagen de la Lambda**:
   - `docker build --platform linux/amd64 --provenance=false -t lector-tickets -f lambda/Dockerfile .`
   - Login en ECR con un token de CloudShell (`aws ecr get-login-password --region us-east-2`), luego `docker tag` y `docker push` al repositorio `lector-tickets`.
4. **Lambda** `lector-tickets` desde la imagen: x86_64, 1,024 MB, 1 minuto de tiempo límite. Desencadenador S3: eventos de creación de objetos con prefijo `raw/documentos/`.
5. **Glue**: job `e2-raw-a-curated` con `script_glue/raw_a_curated.py`, worker G.1X, 2 workers, parámetros `--RAW_PATH s3://e2-facturas-sebety/raw/extraidos/` y `--CURATED_PATH s3://e2-facturas-sebety/curated/comprobantes/`.
6. **Athena**: ubicación de resultados `s3://e2-facturas-sebety/athena-results/`; correr `athena/01_crear_tablas.sql` (una sentencia a la vez) y luego `athena/02_consultas.sql`.

## Problemas encontrados y cómo se resolvieron

- **Formato de imagen:** Docker Desktop genera por defecto un formato que Lambda rechaza; se construye con `--provenance=false`.
- **Credenciales en Windows:** el token de ECR excede el tamaño que acepta el Administrador de credenciales de Windows ("The stub received bad data"). Se configuró Docker para guardar esa credencial en su archivo `config.json` (`credHelpers`).
- **Carpetas creadas a mano en S3:** la consola crea cada carpeta como un objeto vacío que termina en `/`, y eso disparó la Lambda; la validación lo rechazó como `archivo_ilegible`. La versión de `src/lambda_function.py` en este repositorio ya ignora esas llaves (requiere reconstruir y volver a publicar la imagen); mientras tanto, los documentos se suben arrastrando carpetas completas.
- **Permisos:** la cuenta del curso pertenece a una organización con políticas de control de servicio (SCP) que impiden crear contraseñas de consola para usuarios IAM y el acceso entre cuentas. La Lambda usa el rol `PowerUserRole` provisto por la cuenta; en producción se usaría un rol dedicado de mínimo privilegio.

## Política de costos (resumen)

| Zona | Formato | Vida | Regla |
|---|---|---|---|
| `raw/documentos/` | PNG, JPG, PDF, XML | 5 años (obligación del SAT) | Standard → Standard-IA (30 d) → Glacier Instant Retrieval (90 d) → Deep Archive (365 d) → se borra (1,830 d). Los objetos menores a 128 KB (los XML) no se transicionan |
| `raw/extraidos/` | JSON | 1 año | Se borra a los 365 días (ya vive en curated) |
| `rechazados/` | JSON | 90 días | Se borra a los 90 días |
| `curated/comprobantes/` | Parquet (snappy), partición anio/mes | Mientras el cliente esté activo | Standard; pesa muy poco |
| `athena-results/` | CSV | 7 días | Se borra a los 7 días |
