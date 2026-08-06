# Skill: Experiment Logging

**Cuando:** despues de un experimento, sweep, A/B o corrida de eval relevante.  
**Objetivo:** clasificar el resultado y, si aplica, materializarlo en el EKS con el template correcto.

## Entradas

- Que se probo (hipotesis, config, dataset).
- Resultados numericos u observaciones.
- Artefactos (paths a reports, logs).

## Pasos

1. **Clasificar** — responder una sola opcion primaria:

   | Opcion | Criterio | Destino |
   |--------|----------|---------|
   | Experiment | Aprendizaje puntual; puede repetirse | `knowledge/experiments/EXP-NNN-*.md` |
   | Benchmark | Congelar como referencia de no-regresion | `knowledge/benchmarks/BM-NNN-*.md` |
   | ADR | Cambia frontera / contrato / principio | `docs/adr/ADR-XXXX-*.md` (proponer, no auto-aceptar) |
   | Decision | Micro-decision local sin frontera | `knowledge/decisions/DEC-NNN-*.md` |
   | Nothing | Ruido o irreproducible; no registrar | — |

2. **Asignar ID**
   - Listar IDs existentes en la carpeta destino; tomar el siguiente monotónico.
   - Prefijos: EXP / BM / DEC (ADR usa numeracion de `docs/adr/`).

3. **Crear documento**
   - Copiar template de `knowledge/_templates/`.
   - Completar **todo** el frontmatter (`_schema/metadata.md`).
   - Completar secciones fijas; en EXP rellenar Recommendation con el check de clasificacion.
   - Enlazar `related` a ADRs/BM/EXP previos.

4. **Si la recomendacion es Benchmark o ADR**
   - No silenciar: proponer el siguiente paso (crear BM o invocar skill ADR Proposal).
   - No aceptar ADR automaticamente.

5. **Actualizar indices locales**
   - Si la carpeta tiene tabla en su README (ej. benchmarks), anadir la fila.

## Reglas

- Un experimento cerrado sin Recommendation incompleto no se considera logueado.
- No reescribir BM aceptados: superseder con BM nuevo.
- Cero cambios en `src/` por esta skill salvo que el experimento mismo los haya hecho antes.

## Salida

- Path del documento creado (o "Nothing").
- Clasificacion elegida y, si aplica, siguiente accion propuesta.
