# ADR-0005 - Observability como substrato transversal

- **Estado:** Propuesto
- **Fecha:** 2026-07-21

## Contexto

"Agentico" sin trazas es magia no medible.

## Decision

Cada eslabon de la cadena emite un evento de traza (decision, entradas relevantes, timing, costo). Las trazas son un artefacto de primera clase, exportable al benchmark y a inspeccion.

`timing_breakdown` actual es un subconjunto de esto. Observability atraviesa todos los planos; no es una capability.

## Consecuencias

Habilita P3/P4; base para evaluar capacidades no-RAG en el futuro.

## Alternativas

Logs ad-hoc (rechazado: no estructurado ni exportable).
