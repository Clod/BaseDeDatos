# Journal - antigravity (Part 1)

> AI development session journal
> Started: 2026-04-21

---



## Session 1: Conduccion bridge + local Movilidad setup

**Date**: 2026-05-22
**Task**: Conduccion bridge + local Movilidad setup

### Summary

(Add summary)

### Main Changes

| Area | Cambio |
|------|--------|
| `etl/movilidad_bridge.py` | Agregado `_upsert_conduccion()` — MERGE sobre `(viaje, usuario)`, mapea `occupant_role → ocupante`. Llamado desde `_sync_one()`. Docstring corregido (Conduccion estaba incorrectamente marcada como "fuera de scope") |
| `tests/unit/test_movilidad_bridge.py` | 2 tests nuevos: `test_upsert_conduccion_merges_occupant_role` y `test_upsert_conduccion_accepts_none_occupant`. Happy-path test actualizado para verificar `MERGE Conduccion` |
| `development/hydrate_local_small.py` | Fix: default de `--file` ahora es relativo a `__file__` (no al CWD). Agrega `import os` faltante |
| `.env` | Agregadas variables `ENABLE_MOVILIDAD_BRIDGE`, `MOVILIDAD_HOST/PORT/DATABASE/USER/PASSWORD` apuntando al Docker local |
| `README.md` | Sección "Movilidad Bridge" expandida con tabla de mapeo de tablas, explicación de cuándo dispara el bridge, `.env` para prod y local. Nueva sección "Processing Everything Including Movilidad" con workflow completo y query de verificación. Nueva sección "Reprocessing and Backfill" con todos los flags de `sync_movilidad.py` y diagnóstico de 3 checks para Movilidad vacío |
| `etl/sentiance_etl.py` | `print()` → `logger.info()` en el bloque `__main__` |

**Total tests**: 122 passed (2 nuevos)

**Root cause documentado**: El bridge solo dispara cuando el ETL procesa eventos `DrivingInsights` nuevos en el batch actual. Si todos los eventos ya tienen `is_processed=1`, `_dirty_transport_ids` queda vacío y el bridge no corre — usar `sync_movilidad.py` para backfill en ese caso.


### Git Commits

| Hash | Message |
|------|---------|
| `eb5a361` | (see git log) |
| `755318c` | (see git log) |
| `2b0a1a8` | (see git log) |
| `c05bc3b` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 2: Reproceso julio + idempotencia DrivingInsights/UserMetadata + herramienta de purga

**Date**: 2026-07-04
**Task**: Reproceso julio + idempotencia DrivingInsights/UserMetadata + herramienta de purga

### Summary

(Add summary)

### Main Changes

Reproceso de la ventana de julio (1.171 registros) en RDS VictaTMTK_ETL con el bridge de Movilidad arreglado, apuntando a las tablas Movilidad DENTRO de VictaTMTK_ETL (el Movilidad real nunca se tocó, garantizado por triple assert). Se descubrió y cerró la no-idempotencia del ETL en reprocesos.

| Área | Qué se hizo |
|------|-------------|
| Reproceso julio | 1.171/1.171 registros reprocesados en RDS VictaTMTK_ETL con código arreglado + bridge; 286/286 trips proyectados |
| Dedup datos | DrivingInsightsTrip 164→88; eventos hijos ~mitad (Harsh 96→48, Phone 412→206, Call 4→2, Speeding 26→13) |
| Validación | Paridad local vs VictaTMTK_ETL 100% en formato/magnitud (incl. eventos_fuertes); residuos polyline/puntos = datos de origen/precisión, no bugs |
| Fix idempotencia DI | DrivingInsightsTrip INSERT→MERGE; 5 tablas hijas con guarda NOT EXISTS (clave natural exacta, sin floats) |
| Fix idempotencia UserMetadata | INSERT→NOT EXISTS por (user,label,value); preserva historial de valores distintos |
| Herramienta purga | scripts/purge_for_reprocess.py: clean-slate de una ventana (--ids/--uid/--since/--until/--dry-run) vía link SdkSourceEvent + subárbol UserContext |
| Tests | +3 regression (test_reprocess, test_purge_reprocess, metadata idempotencia). Total: 167 unit + 32 regression verdes |
| Docs | CLAUDE.md, README_ENG.md, tests/regression/README.md, .trellis/spec/backend/database-guidelines.md |

**Hallazgos clave**:
- Bare INSERT en path re-ejecutable duplica DrivingInsightsTrip + hijos al reprocesar (reset is_processed=0). Fix: MERGE (compartidas) + NOT EXISTS (hoja).
- Float numeric(6,3) en clave NOT EXISTS rompe el match por redondeo → usar solo columnas exactas (epoch+type).
- Tablas append-only (Timeline, UserContext, ...) requieren purga previa; no se guardan en el hot-path.

**Archivos modificados**:
- `etl/sentiance_etl.py`
- `scripts/purge_for_reprocess.py` (nuevo)
- `tests/regression/test_reprocess.py` (nuevo)
- `tests/regression/test_purge_reprocess.py` (nuevo)
- `CLAUDE.md`, `README_ENG.md`, `tests/regression/README.md`


### Git Commits

| Hash | Message |
|------|---------|
| `a246a3f` | (see git log) |
| `93c8ebf` | (see git log) |
| `74ef6fd` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete
