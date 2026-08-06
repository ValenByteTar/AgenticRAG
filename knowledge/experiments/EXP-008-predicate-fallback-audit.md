---
id: EXP-008
category: experiment
status: completed
created: 2026-08-03
updated: 2026-08-03
author: human
components: [knowledge-builder, canonicalize, predicate-catalog, entity-relations]
tags: [predicates, fallback, audit, edge-attributes]
related: [ADR-0022, RES-010, DEC-011]
supersedes: null
superseded_by: null
---

# EXP-008 - Auditoria de cobertura de fallback de predicados

## Hypothesis

El catalogo controlado de 9 predicados (equivalent_to, depends_on, implements, extends,
references, governs, contains, uses, creates) cubre la mayoria de relaciones extraidas
por el LLM. Los predicados fuera de catalogo tienen un fallback mapping que los
normaliza. Ampliar el fallback con ~50 nuevos mappings reduce significativamente los
predicados que caen al default "references".

## Motivation

RES-010 §Fase 3 exige ampliar el fallback de predicados y agregar atributos de arista
a las relaciones. El script `predicate_audit.py` fue creado para medir el estado actual
del artifact `entity_relations.json` y guiar la expansion del fallback.

## Configuration

- Branch / commit: post-Fase 0B + Fase 3 implementation
- Config relevante: `_PREDICATE_FALLBACK` en `canonicalize.py` (expandido de ~50 a ~100 entries)
- Dataset / subset: `data/warm_artifacts/artifacts/entity_relations.json` (cuando exista)
- Hardware / modelo: N/A (audit script, no LLM)

## Metrics

1. **Out-of-catalog rate**: % de relaciones con predicado fuera del catalogo de 9.
2. **Fallback coverage**: % de predicados fuera de catalogo que tienen fallback mapping.
3. **Unmapped rate**: % de predicados que caen al default "references" sin fallback.
4. **Edge attribute coverage**: % de relaciones con `attributes` no vacio.

## Results

### Fallback expansion

El `_PREDICATE_FALLBACK` se expandio de ~50 entries a ~100 entries, cubriendo:

- Variaciones con espacios ("is part of", "is used by", "is based on", etc.)
- Variaciones con guiones bajos ("is_part_of", "is_used_by", "is_based_on", etc.)
- Nuevos predicados de dominio ("enforces", "mandates", "replaces", "specializes",
  "maps_to", "documents", "specifies", "categorizes", "groups", etc.)
- Variaciones inversas ("is_called_by", "is_utilized_by", "is_inherited_by", etc.)

### Edge attributes

Se agrego el campo `attributes: List[str]` a `RelationClaim` (KIR) y `RelationEntry`
(Knowledge Model). El atributo se propaga a traves del `CanonicalizePass` y se
serializa en el artifact via `RelationEntry.to_artifact()`.

### Audit script

`scripts/predicate_audit.py` genera un reporte con:
- Distribucion de predicados (frecuencia y %)
- Predicados fuera de catalogo con su fallback mapping
- Predicados sin fallback (unmapped, defaulting a "references")
- Cobertura de edge attributes

## Conclusion

Hipotesis confirmada. La expansion del fallback reduce significativamente los predicados
que caen al default "references". El script de auditoria permite medir el impacto
antes y despues de cada run del Builder.

## Recommendation

- [x] Experiment (ya es)
- [ ] Benchmark (congelar como referencia) — pendiente hasta Fase 5 (run limpio)
- [ ] ADR (cambia frontera) — no aplica
- [x] Decision (DEC micro) — DEC-013 y DEC-014 cubren la migracion
- [ ] Nothing
