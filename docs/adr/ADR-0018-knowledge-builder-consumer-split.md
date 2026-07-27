# ADR-0018 - Knowledge Builder / Knowledge Consumer split con Artifact Registry

- **Estado:** Aceptado
- **Fecha:** 2026-07-24
- **Related:** RES-001, RES-002, RES-003, ADR-0015, ADR-0009, BM-002, BM-003, BM-004

## Contexto

El monolito (`rag_hybrid.py`) mezcla index-time y query-time. Cada query reconstruye conocimiento de dominio que deberia compilarse una vez. BM-002/003/004 muestran que parches en el Consumer mejoran el consumo pero no resuelven la ausencia de conocimiento compilado de alta calidad.

El problema no son las heuristicas. Es **reconstruir conocimiento estable en query-time**.

## Decision

Se adopta la separacion arquitectonica **Knowledge Builder / Knowledge Consumer** mediada por un **Artifact Registry**:

1. **El centro del sistema es el contrato (Warm Artifacts)**, no el Builder ni el Consumer. Ambos son reemplazables mientras preserven el contrato.

2. **El Builder es un Knowledge Compiler** con fases: front-end (Knowledge Acquisition) → KIR (lossless) → IR Passes (middle-end) → Validation → Knowledge Model → back-end (Artifact Generation). No es un ETL lineal.

3. **Knowledge IR (KIR)** es la representacion intermedia lossless. Multiple extractores (LLM, NER, regex, OCR, vision, tables) producen el mismo KIR. Toda transformacion se puede trazar al origen.

4. **Knowledge Pass API**: toda transformacion de KIR es un plugin (`run(kir) -> kir`). Los passes son componibles, reordenables y extensibles.

5. **Confidence Policy**: la combinacion de confidence de multiples extractores es una estrategia configurable por build (max, mean, weighted, bayesian, LLM arbitration, rule-based), no un pass fijo.

6. **Artifact Registry** es la autoridad unica de publicacion de Warm Artifacts. No es un directorio. Es un componente con identidad propia (análogo a Docker Registry / OCI Registry):
   - **Publication Protocol**: Builder → Registry (staging → promote, swap atomico)
   - **Resolution Protocol**: Consumer → Registry (resolve build activo)
   - **Compatibility**: `contract_version` validado antes de promote
   - **Rollback**: swap atomico a build previo, sin recompilar
   - **Integrity**: SHA-256 por artifact, validado en carga
   - **Migrations**: transformaciones de schema sin recompilar
   - **Build lifecycle**: `staging → promoted → deprecated → archived → purged`

7. **Knowledge Layers** estructuran el Knowledge Model: Document, Entity, Concept, Relation, Retrieval. Los artifacts son proyecciones persistentes de estas layers.

8. **Entity Relations** son triples Subject-Predicate-Object con un catalogo controlado de predicados (versionado, cerrado). No predicados libres. Habilita evolucion a GraphRAG.

9. **Confidence** es una senal de decision para el Consumer, no metadata decorativa. Todo claim Warm incluye `confidence`, `validated`, `builder_version`, `generated_by`, `evidence`.

10. **Artifact taxonomy**: Cold (internos del build, nunca llegan al Consumer), Warm (contrato compartido, read-only), Hot (estado temporal por query, Consumer-owned).

11. **Frontera inviolable**: el Consumer nunca interpreta documentos crudos, nunca descubre dominio, nunca publica. El Builder nunca resuelve. Publicar ≠ Resolver.

12. **Modelo inicial**: Granite 4.1 8B como extractor del Builder. Reemplazable. El contrato no depende del modelo.

## Consecuencias

- Desacoplamiento total: Builder y Consumer evolucionan independientemente mientras el contrato Warm se preserve.
- El conocimiento de dominio del monolito (aliases, equivalencias, roles, conceptual map, technology filtering) se compila en index-time y se serializa como Warm Artifacts.
- Knowledge Pass API permite extension sin tocar el core del compiler.
- Artifact Registry habilita rollback instantaneo, A/B de builds, y evolucion del contrato via `contract_version`.
- Migracion incremental (Fase 7a-7d → Fase 8) con A/B obligatorio antes de deprecar el monolito.
- El esquema interno del Knowledge System (ADR-0015) se concreta: Knowledge Model + Layers + Warm Artifacts son la estructura diferida que ADR-0015 reservaba.

## Alternativas

- **Parches en el Consumer** — rechazado: BM-004 demuestra que mejoran el consumo pero no resuelven la ausencia de conocimiento compilado.
- **Builder como ETL lineal** — rechazado: no captura la necesidad de representacion intermedia, passes componibles, ni multiple extractores.
- **Artifact Repository como directorio versionado** — rechazado: no provee publication protocol, compatibility, rollback, ni integrity. Necesita identidad de componente.
- **Congelar el contrato Warm ahora** — rechazado: el contrato inicial es minimo (canonical entities, alias index, entity index, doc roles, entity relations, retrieval metadata). Evoluciona via `contract_version`.
- **Predicados libres** — rechazado: extractores (incluido LLM) inventarian relaciones. Catalogo controlado + structural validation.
