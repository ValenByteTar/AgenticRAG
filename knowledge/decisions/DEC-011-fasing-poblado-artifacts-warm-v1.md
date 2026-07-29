---
id: DEC-011
title: "Fasing de poblado de Warm Artifacts en warm-v1: declaracion completa, poblado escalonado"
date: 2026-07-28
status: accepted
category: decisions
tags: [contract, warm-v1, artifacts, fasing, evidence, taxonomy]
related: [ADR-0018, RES-001, RES-002, RES-003]
---

# DEC-011 — Fasing de poblado de Warm Artifacts en warm-v1

## Contexto

E1 del plan de orquestacion (`docs/plan-orquestacion-knowledge.md`) define el contrato `warm-v1`.
ADR-0018.8 exige Entity Relations y catalogo de predicados como parte del contrato. RES-001 §7.4
lista ademas Taxonomy como Warm Artifact.

Surge la pregunta: ¿el contrato v1 incluye todos los artifacts desde el inicio, o solo los que la
primera etapa de poblado (E3) produce?

## Decision

**Declaracion completa en v1, poblado escalonado por etapa.**

1. `warm-v1` declara 7 artifacts con schema propio: `canonical_entities`, `alias_index`,
   `entity_index`, `doc_roles`, `entity_relations`, `retrieval_metadata`, `predicate_catalog`.
2. Poblado por etapa del plan:
   - **E3**: `canonical_entities`, `alias_index`, `entity_index`, `doc_roles`, `predicate_catalog`
   - **E6**: `retrieval_metadata` (y enriquecimiento de `entity_index`)
   - **E7**: `entity_relations`
3. Un artifact **declarado y vacio es valido** (ej. `{"relations": []}`). Un artifact **no
   declarado en el manifest rompe el build**: `validate_build` rechaza manifests que listen
   artifacts desconocidos y valida cada artifact listado contra su schema.
4. `taxonomy` (Concept Layer) **no se declara en warm-v1**. Se agrega en E7 junto a su consumidor
   real. Agregar un artifact nuevo al contrato es compatible hacia atras (no rompe consumers que
   no lo conocen), por lo que no requiere `warm-v2`.
5. **Sobre `evidence`** (ADR-0018.9): se interpreta como obligatorio en claims de `entity_relations`
   (Evidence Validation estricta, RES-001 §7.5 regla 2) y **opcional** en el resto de claims
   (entities, aliases, roles), cuya evidencia es la extraccion misma trazada en `generated_by`.
   Los ejemplos literales de RES-001 §7.4 avalan esta lectura: solo el ejemplo de relations lleva
   `evidence`.
6. **Envelope**: cada artifact es un objeto raiz con una coleccion nombrada (`entities`, `aliases`,
   `docs`, `relations`). Los ejemplos literales de RES-001 §7.4 son claims individuales; viven
   dentro de la coleccion del envelope sin modificacion.

## Consecuencias

- El contrato es estable desde el inicio: ninguna etapa posterior modifica schemas de v1, solo
  puebla artifacts ya declarados.
- El Consumer (E4) puede resolver contra un build cuyos artifacts de retrieval/relations estan
  vacios sin romper compatibilidad: los thresholds de confidence simplemente no encuentran claims.
- `validate_build` es el unico punto que conoce la lista de artifacts declarados por version.

## Alternativas consideradas

1. Declarar en v1 solo lo que E3 puebla: rechazado — convertiria cada etapa de poblado en un cambio
   de contrato, contradiciendo I1 (el contrato es el centro estable).
2. Exigir `evidence` en todo claim: rechazado — contradice los ejemplos literales de RES-001 y
   agrega ruido a claims deterministicos cuya trazabilidad ya cubre `generated_by`.
3. Declarar `taxonomy` en v1 vacia: rechazado — sin consumidor hasta E7, seria declaracion
   especulativa; agregarla luego es compatible hacia atras.

## Criterios de aceptacion

- Los 7 schemas existen en `contract/warm-v1/` y validan los ejemplos literales de RES-001 §7.4.
- Artifacts declarados y vacios pasan validacion.
- Manifest con artifact desconocido es rechazado.
- Relations con predicado fuera de `predicate_catalog` son rechazadas por `validate_build`.

## Por que no es ADR

No cambia fronteras ni interfaces nuevas: interpreta y secuencia la aplicacion de ADR-0018.8/9
dentro del contrato ya aceptado. Es reversible (agregar taxonomy o endurecer evidence no rompe
consumers). Vive como DEC.
