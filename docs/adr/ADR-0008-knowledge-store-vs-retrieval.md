# ADR-0008 - KnowledgeStore vs RetrievalPipeline

- **Estado:** Superseded-by-0015
- **Fecha:** 2026-07-21

## Contexto

El sistema equiparaba "conocimiento" con "chunks en Chroma".

## Decision (original)

Separar dos contratos: RetrievalPipeline (busqueda hibrida) y KnowledgeStore (acceso a conocimiento con identidad/relaciones/provenance).

## Motivo de supersesion

"Store" es insuficiente. El Knowledge Architect maneja entidades, relaciones, provenance, confianza, evidencia, derivaciones y versiones: es un **subsistema**, no un store. Ver ADR-0015.
