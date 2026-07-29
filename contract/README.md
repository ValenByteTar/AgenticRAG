# Contract — Warm Artifacts

El centro del sistema (ADR-0018.1). Builder y Consumer son reemplazables; el contrato no.

## Versiones

| Version | Estado | Artifacts declarados |
|---|---|---|
| `warm-v1/` | Activa | `canonical_entities`, `alias_index`, `entity_index`, `doc_roles`, `entity_relations`, `retrieval_metadata`, `predicate_catalog` |

Poblado escalonado por etapa (DEC-011): un artifact declarado y vacio es valido; un artifact no
declarado en el manifest rompe el build.

## Reglas del contrato

1. Todo claim lleva bloque de confianza: `confidence`, `validated`, `builder_version`,
   `generated_by` (ADR-0018.9).
2. `validated` debe ser `true` en todo claim Warm. Nada no validado se publica (I5, RES-002 §6).
3. `evidence` es obligatorio en claims de `entity_relations`; opcional en el resto (DEC-011).
4. Todo `predicate` publicado debe existir en `predicate_catalog` del mismo build (RES-001 §7.5).
5. El Consumer nunca lee estos archivos directamente: resuelve via Artifact Registry
   (Publication/Resolution Protocol, RES-001 §5).

## Validacion

El validador compartido vive en `src/contract/validator.py`. Lo consumen:

- el Builder (antes de publicar),
- el Registry (en `publish` y `promote`),
- los tests de contrato (`tests/unit/test_contract_warm_v1.py`).

## Evolucion

- Agregar un artifact nuevo a una version existente: compatible hacia atras (DEC-011.4).
- Cambiar o quitar campos: requiere `warm-v2` + migration en el Registry (RES-001 §5.7).
- Ampliar `predicate_catalog`: decision de arquitectura, no de extractores (RES-001 §7.5 regla 4).
