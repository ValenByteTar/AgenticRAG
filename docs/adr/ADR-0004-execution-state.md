# ADR-0004 - ExecutionState explicito y serializable

- **Estado:** Propuesto
- **Fecha:** 2026-07-21

## Contexto

El sistema actual esparce estado en `self._sticky_sources`, `last_entities`, `locals()`.

## Decision

Un `ExecutionState` (dataclass serializable) transporta pregunta, plan, resultados, senales de evaluacion, presupuesto y trazas.

Los Steps solo leen/escriben `ExecutionState`, nunca back-reference al orquestador.

## Consecuencias

Cumple P5; habilita replay, debugging y tests de contrato; desacopla los colaboradores actuales del `rag=self`.

## Alternativas

Estado en el orquestador (rechazado: estado oculto).
