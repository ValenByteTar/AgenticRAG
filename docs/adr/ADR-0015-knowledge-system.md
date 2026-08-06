# ADR-0015 - Knowledge System (subsistema, no store)

- **Estado:** Aceptado
- **Fecha:** 2026-07-21
- **Supersede:** ADR-0008

## Contexto

"Conocimiento == chunks en Chroma" es incorrecto. El Knowledge Architect futuro maneja entidades, relaciones, provenance, confianza, evidencia, derivaciones y versiones. Eso es un subsistema, no un store.

## Decision

El **Knowledge** es un **plano** con un contrato de **KnowledgeSystem** (subsistema), no un simple store.

El indice vectorial y la `RetrievalPipeline` son **una** via de acceso al conocimiento, no su totalidad.

El **esquema interno** (como se modelan entidades/relaciones/provenance/versiones) queda **diferido** (P11): se reserva la frontera, no se congela la estructura.

## Consecuencias

Habilita el Knowledge Architect por extension, sin revertir decisiones de indice; separa "recuperar texto" de "conocer".

## Alternativas

KnowledgeStore plano (rechazado: insuficiente para el horizonte). Congelar esquema ahora (rechazado: sobre-abstraccion, P11).
