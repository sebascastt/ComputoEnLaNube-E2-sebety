# Bytes leídos por Athena

Fecha de la corrida: AAAA-MM-DD · Región: us-east-2 (Ohio) · Precio de Athena: 5 USD por TB leído (mínimo 10 MB por consulta)

| # | Consulta | Tabla / formato | Data scanned | Tiempo | Captura |
|---|---|---|---|---|---|
| 1 | Gasto mensual por usuario | comprobantes (Parquet) | | | `consulta1.png` |
| 2 | Gasto por categoría, oct-2026 | comprobantes (Parquet, 1 partición) | | | `consulta2.png` |
| 3 | Duplicados | comprobantes (Parquet) | | | `consulta3.png` |
| Extra | Consulta 2 sobre JSON | raw_extraidos (JSON) | | | `consulta2_json.png` |

**Conclusión:** <comparar 2 contra Extra: cuántas veces menos lee Parquet particionado>
