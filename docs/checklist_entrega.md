# Checklist de la Entrega 2

✅ hecho · 🟡 código listo, falta correrlo en AWS y tomar evidencia · ⬜ pendiente de redactar

## Ruta 1 · Técnica
| # | Requisito | Dónde | Estado |
|---|---|---|---|
| 1 | Lago con 3 capas (raw/, curated/, athena-results/) y 3 consultas con bytes anotados | `infra/`, `athena/02_consultas.sql`, `evidencias/athena_bytes.md` | 🟡 |
| 2 | Tablas con datos estructurados | `athena/01_crear_tablas.sql` (raw_extraidos, comprobantes) | 🟡 |
| 3 | Job de Glue raw → Parquet particionado en curated | `glue/raw_a_curated.py` (probado en local con Spark) | 🟡 |
| 4 | Políticas de almacenamiento y procesamiento para optimizar costos | `infra/lifecycle.json`, tabla en `README.md` | 🟡 |

## Ruta 2 · Funcional
| # | Requisito | Dónde | Estado |
|---|---|---|---|
| 1 | Zonas y regiones: ¿replicar?, ¿por qué? | `docs/01_zonas_regiones.md` | ⬜ |
| 2 | Tres razones de nube frente a centro de datos propio | `docs/02_caso_nube.md` | ⬜ |
| 3 | ADR de entrada y almacenamiento (2+ alternativas) | `docs/adr/ADR-001-entrada-almacenamiento.md` | ⬜ |
| 4 | ADR de procesamiento con costo a 12 meses, x1 y x3 | `docs/adr/ADR-002-procesamiento.md` | ⬜ |
| 5 | Política de acceso y tabla RACI (4 filas) | `docs/05_roles_raci.md` | ⬜ |
| 6 | Costos de almacenamiento y procesamiento con las políticas técnicas | `docs/06_costos.md` | ⬜ |

## Eventos (triggers) de ingesta
| | Requisito | Respuesta base |
|---|---|---|
| A | Evento que dispara la llegada | Un archivo que cae en S3 (`raw/documentos/`) |
| B | Síncrono o asíncrono | Asíncrono: el usuario sube el archivo y no espera; S3 invoca la Lambda en segundo plano |
| C | Justificación con cifras | 1,000 docs/mes ≈ 33/día; ~0.8 s por documento; la consulta es semanal/mensual, así que no hace falta respuesta inmediata. Si falla: 2 reintentos automáticos y luego la cola de errores (DLQ); si el archivo es ilegible va a `rechazados/` y se avisa al usuario |
| D | Arquitectura de ingesta | Técnica: Lambda + trigger S3 (`docs/guia_despliegue.md` paso 2). Funcional: diagrama del README y ADR-001 |
⬜ Pasar a texto formal en `docs/03_ingesta.md`

## Roles y estructura de datos
| Requisito | Dónde | Estado |
|---|---|---|
| 3+ roles: qué pueden hacer, qué no, responsabilidad | `docs/05_roles_raci.md` | ⬜ |
| Lógica de la estructura: usabilidad, seguridad, costo y retención, trazabilidad (tabla de linaje) | `docs/04_estructura_datos.md` | ⬜ |

## Entrega
- [ ] Renombrar la carpeta con su número de equipo (`E2_EQ07`, por ejemplo)
- [ ] README.md completo
- [ ] Carpeta `evidencias/` con las capturas
